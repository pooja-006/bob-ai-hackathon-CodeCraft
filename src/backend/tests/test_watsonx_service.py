"""
test_watsonx_service.py
=======================
Tests for watsonx_service.py focusing on fallback behavior,
prompt construction, JSON extraction, and API contracts.

All tests run entirely in fallback/offline mode (no credentials required).

Run with:
    pytest src/backend/tests/test_watsonx_service.py -v
"""

from __future__ import annotations

import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import pytest

from src.backend.services.watsonx_service import (
    analyze_root_cause,
    generate_corrective_actions,
    answer_engineer_query,
    watsonx_status,
    _extract_json,
    _build_root_cause_prompt,
    _build_corrective_actions_prompt,
    _build_query_prompt,
    _fallback_root_cause,
    _fallback_corrective_actions,
    _fallback_answer,
    _is_watsonx_available,
)


# ---------------------------------------------------------------------------
# Sample evidence fixtures
# ---------------------------------------------------------------------------

SENSOR_EVIDENCE = [
    {
        "cause": "Abnormal etch_temp_c on ETCH-03",
        "category": "sensor_anomaly",
        "parameter": "etch_temp_c",
        "tool_id": "ETCH-03",
        "direction": "high",
        "confidence_pct": 38.0,
        "summary": "etch_temp_c is 4.2sigma above fleet mean on ETCH-03. Fleet correlation rho=-0.36.",
        "evidence": [
            {
                "parameter": "etch_temp_c",
                "lot_value": 190.5,
                "fleet_mean": 175.0,
                "deviation_sigma": 4.2,
                "yield_correlation_rho": -0.36,
            }
        ],
    }
]

DEFECT_EVIDENCE = [
    {
        "cause": "Elevated particle defect density on lot W2401-0083",
        "category": "defect_contamination",
        "parameter": "defect_density",
        "tool_id": "ETCH-03",
        "direction": "high",
        "confidence_pct": 29.0,
        "summary": "particle density 0.3210/cm2 is 3.1sigma above step average.",
        "evidence": [
            {
                "defect_type": "particle",
                "lot_density": 0.3210,
                "fleet_mean_density": 0.074,
                "deviation_sigma": 3.1,
            }
        ],
    }
]

TOOL_EVIDENCE = [
    {
        "cause": "Tool ETCH-03 shows sustained below-average yield",
        "category": "tool_performance",
        "parameter": None,
        "tool_id": "ETCH-03",
        "direction": "low",
        "confidence_pct": 37.2,
        "summary": "ETCH-03 mean yield 81.8%, z=-1.86 across 29 lots.",
        "evidence": [
            {
                "tool_id": "ETCH-03",
                "mean_yield": 81.8,
                "lot_count": 29,
                "yield_z_score": -1.86,
            }
        ],
    }
]

MIXED_EVIDENCE = SENSOR_EVIDENCE + DEFECT_EVIDENCE + TOOL_EVIDENCE


# ---------------------------------------------------------------------------
# Credential / mode detection
# ---------------------------------------------------------------------------

class TestWatsonxStatus:
    def test_returns_dict(self):
        status = watsonx_status()
        assert isinstance(status, dict)

    def test_required_keys(self):
        status = watsonx_status()
        for key in ["sdk_installed", "credentials_set", "model_id", "url", "mode"]:
            assert key in status, f"Missing key: {key}"

    def test_mode_is_fallback_without_credentials(self):
        """Without WATSONX_API_KEY set this machine runs in fallback mode."""
        status = watsonx_status()
        # Credentials are not set in the test environment
        if not _is_watsonx_available():
            assert status["mode"] == "fallback"

    def test_model_id_is_string(self):
        status = watsonx_status()
        assert isinstance(status["model_id"], str)
        assert len(status["model_id"]) > 0


# ---------------------------------------------------------------------------
# JSON extraction helper
# ---------------------------------------------------------------------------

class TestExtractJson:
    def test_clean_object(self):
        text = '{"key": "value", "num": 42}'
        result = _extract_json(text)
        assert result == {"key": "value", "num": 42}

    def test_object_with_surrounding_text(self):
        text = 'Here is the result: {"status": "ok"} end'
        result = _extract_json(text)
        assert result == {"status": "ok"}

    def test_array(self):
        text = '[{"a": 1}, {"b": 2}]'
        result = _extract_json(text)
        assert result == [{"a": 1}, {"b": 2}]

    def test_array_with_surrounding_text(self):
        text = "Here are the actions:\n[{\"action\": \"fix it\"}]\nDone."
        result = _extract_json(text)
        assert isinstance(result, list)
        assert result[0]["action"] == "fix it"

    def test_invalid_json_returns_none(self):
        result = _extract_json("this is plain text with no JSON")
        assert result is None

    def test_partial_json_returns_none(self):
        result = _extract_json('{"incomplete": ')
        assert result is None

    def test_nested_json(self):
        data = {"narrative": "test", "ranked_causes": [{"rank": 1, "cause": "X"}]}
        text = f"Result: {json.dumps(data)}"
        result = _extract_json(text)
        assert result["narrative"] == "test"
        assert len(result["ranked_causes"]) == 1


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

class TestPromptBuilders:
    def test_root_cause_prompt_contains_lot_id(self):
        prompt = _build_root_cause_prompt("W2401-TEST", SENSOR_EVIDENCE)
        assert "W2401-TEST" in prompt

    def test_root_cause_prompt_contains_evidence(self):
        prompt = _build_root_cause_prompt("W2401-TEST", SENSOR_EVIDENCE)
        assert "etch_temp_c" in prompt
        assert "ETCH-03" in prompt

    def test_root_cause_prompt_requests_json(self):
        prompt = _build_root_cause_prompt("W2401-TEST", SENSOR_EVIDENCE)
        assert "JSON" in prompt
        assert "ranked_causes" in prompt

    def test_corrective_actions_prompt_contains_cause(self):
        prompt = _build_corrective_actions_prompt(SENSOR_EVIDENCE[0])
        assert "etch_temp_c" in prompt or "ETCH-03" in prompt

    def test_corrective_actions_prompt_requests_json_array(self):
        prompt = _build_corrective_actions_prompt(SENSOR_EVIDENCE[0])
        assert "JSON array" in prompt or '["' in prompt or "[" in prompt

    def test_query_prompt_contains_question(self):
        prompt = _build_query_prompt("What caused yield loss?", "context here")
        assert "What caused yield loss?" in prompt

    def test_query_prompt_contains_context(self):
        prompt = _build_query_prompt("Any question?", "lot=W2401-0001 yield=71%")
        assert "lot=W2401-0001" in prompt
        assert "yield=71%" in prompt


# ---------------------------------------------------------------------------
# Fallback: analyze_root_cause
# ---------------------------------------------------------------------------

class TestFallbackRootCause:
    def test_empty_evidence(self):
        result = _fallback_root_cause("W2401-TEST", [])
        assert isinstance(result, dict)
        assert "narrative" in result
        assert result["ranked_causes"] == []
        assert result["source_mode"] == "fallback"

    def test_sensor_evidence_produces_ranked_causes(self):
        result = _fallback_root_cause("W2401-TEST", SENSOR_EVIDENCE)
        assert len(result["ranked_causes"]) >= 1
        assert result["ranked_causes"][0]["rank"] == 1

    def test_narrative_contains_lot_id(self):
        result = _fallback_root_cause("W2401-TEST", SENSOR_EVIDENCE)
        assert "W2401-TEST" in result["narrative"]

    def test_ranked_cause_has_required_keys(self):
        result = _fallback_root_cause("W2401-TEST", MIXED_EVIDENCE)
        for cause in result["ranked_causes"]:
            for key in ["rank", "cause", "confidence_pct", "explanation",
                        "implicated_parameter", "implicated_tool"]:
                assert key in cause, f"Missing key: {key}"

    def test_recommended_next_step_is_string(self):
        result = _fallback_root_cause("W2401-TEST", SENSOR_EVIDENCE)
        assert isinstance(result["recommended_next_step"], str)
        assert len(result["recommended_next_step"]) > 0

    def test_mixed_evidence_multiple_causes(self):
        result = _fallback_root_cause("W2401-TEST", MIXED_EVIDENCE)
        assert len(result["ranked_causes"]) >= 2


# ---------------------------------------------------------------------------
# Fallback: generate_corrective_actions
# ---------------------------------------------------------------------------

class TestFallbackCorrectiveActions:
    def test_sensor_anomaly_returns_actions(self):
        actions = _fallback_corrective_actions(SENSOR_EVIDENCE[0])
        assert isinstance(actions, list)
        assert len(actions) >= 3

    def test_defect_contamination_returns_actions(self):
        actions = _fallback_corrective_actions(DEFECT_EVIDENCE[0])
        assert isinstance(actions, list)
        assert len(actions) >= 3

    def test_tool_performance_returns_actions(self):
        actions = _fallback_corrective_actions(TOOL_EVIDENCE[0])
        assert isinstance(actions, list)
        assert len(actions) >= 3

    def test_each_action_has_required_keys(self):
        for evidence in [SENSOR_EVIDENCE[0], DEFECT_EVIDENCE[0], TOOL_EVIDENCE[0]]:
            actions = _fallback_corrective_actions(evidence)
            for action in actions:
                for key in ["action", "rationale", "urgency", "owner"]:
                    assert key in action, f"Missing key '{key}' in action: {action}"

    def test_urgency_values_are_valid(self):
        for evidence in [SENSOR_EVIDENCE[0], DEFECT_EVIDENCE[0], TOOL_EVIDENCE[0]]:
            actions = _fallback_corrective_actions(evidence)
            valid_urgencies = {"HIGH", "MEDIUM", "LOW"}
            for action in actions:
                assert action["urgency"] in valid_urgencies, (
                    f"Invalid urgency: {action['urgency']}"
                )

    def test_tool_id_appears_in_sensor_actions(self):
        actions = _fallback_corrective_actions(SENSOR_EVIDENCE[0])
        combined = " ".join(a["action"] for a in actions)
        assert "ETCH-03" in combined

    def test_generic_category_returns_fallback(self):
        actions = _fallback_corrective_actions({"category": "unknown", "tool_id": "CMP-01"})
        assert len(actions) >= 2


# ---------------------------------------------------------------------------
# Fallback: answer_engineer_query
# ---------------------------------------------------------------------------

class TestFallbackAnswer:
    def test_returns_dict(self):
        result = _fallback_answer("What caused this?", "lot yield: 71% tool: ETCH-03")
        assert isinstance(result, dict)

    def test_required_keys(self):
        result = _fallback_answer("test query", "some context")
        for key in ["answer", "source_mode", "query"]:
            assert key in result

    def test_source_mode_is_fallback(self):
        result = _fallback_answer("test query", "some context")
        assert result["source_mode"] == "fallback"

    def test_query_is_echoed(self):
        result = _fallback_answer("my question", "context")
        assert result["query"] == "my question"

    def test_yield_extracted_from_context(self):
        result = _fallback_answer("What is yield?", "yield: 73.5% something")
        assert "73.5%" in result["answer"]

    def test_answer_is_non_empty(self):
        result = _fallback_answer("Any question?", "no specific data")
        assert len(result["answer"]) > 20


# ---------------------------------------------------------------------------
# Public API — offline fallback behavior
# ---------------------------------------------------------------------------

class TestPublicApiOffline:
    """
    These tests exercise the public functions in fallback mode.
    They must pass regardless of whether watsonx credentials are configured.
    """

    def test_analyze_root_cause_returns_dict(self):
        result = analyze_root_cause("W2401-TEST", SENSOR_EVIDENCE)
        assert isinstance(result, dict)

    def test_analyze_root_cause_required_keys(self):
        result = analyze_root_cause("W2401-TEST", MIXED_EVIDENCE)
        for key in ["narrative", "ranked_causes", "recommended_next_step", "source_mode"]:
            assert key in result, f"Missing key: {key}"

    def test_analyze_root_cause_narrative_non_empty(self):
        result = analyze_root_cause("W2401-TEST", SENSOR_EVIDENCE)
        assert len(result["narrative"]) > 0

    def test_analyze_root_cause_empty_evidence(self):
        result = analyze_root_cause("W2401-EMPTY", [])
        assert isinstance(result, dict)
        assert result["ranked_causes"] == []

    def test_generate_corrective_actions_returns_list(self):
        result = generate_corrective_actions(SENSOR_EVIDENCE[0])
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_generate_corrective_actions_action_keys(self):
        result = generate_corrective_actions(DEFECT_EVIDENCE[0])
        for action in result:
            for key in ["action", "rationale", "urgency", "owner"]:
                assert key in action

    def test_answer_engineer_query_returns_dict(self):
        result = answer_engineer_query("What caused yield loss?", "yield: 72% tool: ETCH-03")
        assert isinstance(result, dict)

    def test_answer_engineer_query_required_keys(self):
        result = answer_engineer_query("Any question?", "context data")
        for key in ["answer", "source_mode", "query"]:
            assert key in result

    def test_answer_engineer_query_echoes_query(self):
        result = answer_engineer_query("specific question", "context")
        assert result["query"] == "specific question"

    def test_source_mode_is_set(self):
        result = analyze_root_cause("W2401-TEST", SENSOR_EVIDENCE)
        assert result["source_mode"] in ("watsonx", "watsonx_raw", "fallback")
