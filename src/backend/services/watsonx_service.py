"""
watsonx_service.py
==================
IBM watsonx.ai integration for the Wafer Yield Root Cause Analyser.

Provides three public functions backed by a Granite model via ModelInference:

  analyze_root_cause(lot_id, evidence_list)
      -> dict with narrative, ranked causes, and confidence scores

  generate_corrective_actions(root_cause)
      -> list of action dicts {action, rationale, urgency, owner}

  answer_engineer_query(query, context)
      -> dict with answer string and source_mode

When WATSONX_API_KEY is not set (or the SDK is unavailable), every function
returns a deterministic fallback response so the demo works fully offline.

SDK reference:
  from ibm_watsonx_ai import APIClient, Credentials
  from ibm_watsonx_ai.foundation_models import ModelInference
  model = ModelInference(
      model_id="ibm/granite-3-3-8b-instruct",
      credentials={"apikey": API_KEY, "url": URL},
      project_id=PROJECT_ID,
      params={"max_new_tokens": 800, "temperature": 0.1}
  )
  text = model.generate_text(prompt)

Environment variables (load from src/.env):
  WATSONX_API_KEY      IBM Cloud API key
  WATSONX_PROJECT_ID   watsonx.ai project ID
  WATSONX_URL          Region URL, e.g. https://us-south.ml.cloud.ibm.com
  WATSONX_MODEL_ID     (optional) override the default model
"""

from __future__ import annotations

import json
import logging
import os
import re
import textwrap
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SDK import — graceful fallback if not installed
# ---------------------------------------------------------------------------

_SDK_AVAILABLE = False
try:
    from ibm_watsonx_ai import APIClient, Credentials          # type: ignore
    from ibm_watsonx_ai.foundation_models import ModelInference # type: ignore
    _SDK_AVAILABLE = True
except ImportError:
    logger.warning(
        "ibm-watsonx-ai SDK not installed. "
        "Install with: pip install ibm-watsonx-ai  "
        "Falling back to offline mock responses."
    )

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_API_KEY    = os.getenv("WATSONX_API_KEY", "")
_PROJECT_ID = os.getenv("WATSONX_PROJECT_ID", "")
_URL        = os.getenv("WATSONX_URL", "https://us-south.ml.cloud.ibm.com")
_MODEL_ID   = os.getenv("WATSONX_MODEL_ID", "ibm/granite-3-3-8b-instruct")

# Fallback to the older instruct model if explicitly configured
_LEGACY_MODEL_ID = "ibm/granite-13b-instruct-v2"

# Generation parameters — conservative for structured engineering output
_GEN_PARAMS = {
    "max_new_tokens": 900,
    "temperature":    0.1,   # low temperature → factual, consistent output
    "top_p":          0.9,
    "repetition_penalty": 1.05,
}

# Module-level singleton (initialised lazily)
_model: Optional[Any] = None


def _is_watsonx_available() -> bool:
    """True if the SDK is installed and credentials are configured."""
    return _SDK_AVAILABLE and bool(_API_KEY) and bool(_PROJECT_ID)


def _get_model() -> Optional[Any]:
    """Return (or create) the ModelInference singleton. Returns None on failure."""
    global _model
    if _model is not None:
        return _model
    if not _is_watsonx_available():
        return None
    try:
        _model = ModelInference(
            model_id=_MODEL_ID,
            credentials={"apikey": _API_KEY, "url": _URL},
            project_id=_PROJECT_ID,
            params=_GEN_PARAMS,
        )
        logger.info("watsonx.ai ModelInference initialised: %s", _MODEL_ID)
        return _model
    except Exception as exc:
        logger.error("Failed to initialise watsonx.ai model: %s", exc)
        return None


# ---------------------------------------------------------------------------
# JSON extraction helper
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> Any:
    """
    Try to extract a JSON object or array from raw LLM output.
    Returns None if extraction fails.

    Tries the outermost structure first: if '[' appears before '{' in the
    text we treat it as an array; otherwise as an object.  This ensures
    corrective-action arrays (which start with '[') are parsed correctly
    even when the array contains object elements (which start with '{').
    """
    obj_start = text.find('{')
    arr_start = text.find('[')

    # Choose the order based on which opener appears first
    if arr_start != -1 and (obj_start == -1 or arr_start < obj_start):
        pairs = [('[', ']'), ('{', '}')]
    else:
        pairs = [('{', '}'), ('[', ']')]

    for start_char, end_char in pairs:
        start = text.find(start_char)
        end   = text.rfind(end_char)
        if start != -1 and end != -1 and end > start:
            candidate = text[start:end + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass
    return None


def _call_model(prompt: str) -> Optional[str]:
    """
    Call the model and return generated text. Returns None on any error.
    """
    model = _get_model()
    if model is None:
        return None
    try:
        return model.generate_text(prompt)
    except Exception as exc:
        logger.error("watsonx.ai generate_text failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def _build_root_cause_prompt(lot_id: str, evidence_list: List[Dict[str, Any]]) -> str:
    evidence_text = json.dumps(evidence_list, indent=2)
    return textwrap.dedent(f"""
    You are a semiconductor process engineer specialising in wafer yield analysis at advanced 3nm/5nm nodes.

    A lot with ID {lot_id!r} has been flagged with low yield. The statistical pattern detection engine
    has identified the following evidence from sensor readings and defect reports:

    EVIDENCE:
    {evidence_text}

    Based ONLY on the evidence above, produce a structured engineering root-cause analysis.
    Do NOT invent sensor readings, defect counts, or causes that are not in the evidence.

    Respond with a JSON object in this exact format:
    {{
      "narrative": "<2-3 sentence plain-English summary of the most likely root cause>",
      "ranked_causes": [
        {{
          "rank": 1,
          "cause": "<concise cause label>",
          "confidence_pct": <0-100>,
          "explanation": "<1-2 sentences grounded in the evidence>",
          "implicated_parameter": "<parameter name or defect type>",
          "implicated_tool": "<tool_id>"
        }}
      ],
      "recommended_next_step": "<single most important immediate action>"
    }}

    Return only the JSON, no extra text.
    """).strip()


def _build_corrective_actions_prompt(root_cause: Dict[str, Any]) -> str:
    cause_text = json.dumps(root_cause, indent=2)
    return textwrap.dedent(f"""
    You are a semiconductor manufacturing process engineer.

    The following root-cause has been identified for a wafer yield excursion:

    ROOT CAUSE:
    {cause_text}

    Generate 3 to 5 specific, practical corrective actions to address this root cause.
    Each action must be grounded in semiconductor fab engineering practice.
    Avoid generic advice. Each action must name the specific parameter, tool, or process step involved.

    Respond with a JSON array in this exact format:
    [
      {{
        "action": "<specific action to take>",
        "rationale": "<why this action addresses the root cause>",
        "urgency": "HIGH" | "MEDIUM" | "LOW",
        "owner": "<Engineering team responsible: Equipment Engineering | Process Engineering | Yield Engineering | Process Control | Fab Operations>"
      }}
    ]

    Return only the JSON array, no extra text.
    """).strip()


def _build_query_prompt(query: str, context: str) -> str:
    return textwrap.dedent(f"""
    You are an expert semiconductor yield engineer assistant.
    Answer the engineer's question using only the process data context provided.
    Be specific and cite relevant numbers from the context.
    If the answer cannot be determined from the context, say so clearly.

    PROCESS DATA CONTEXT:
    {context}

    ENGINEER QUESTION:
    {query}

    Provide a concise, technically accurate answer (2-4 sentences).
    """).strip()


# ---------------------------------------------------------------------------
# Fallback responses (used when credentials unavailable or API call fails)
# ---------------------------------------------------------------------------

def _fallback_root_cause(lot_id: str, evidence_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Build a deterministic fallback root-cause response from the evidence list
    without calling the LLM. Used in offline/demo mode.
    """
    if not evidence_list:
        return {
            "narrative": (
                f"Lot {lot_id} has been flagged for review. "
                "No specific sensor or defect anomalies were detected by the pattern engine. "
                "Manual inspection of process parameters is recommended."
            ),
            "ranked_causes": [],
            "recommended_next_step": "Review lot history and compare against similar lots.",
            "source_mode": "fallback",
        }

    # Build ranked causes directly from the structured evidence
    ranked: List[Dict[str, Any]] = []
    for i, ev in enumerate(evidence_list[:5], start=1):
        category = ev.get("category", "unknown")
        cause    = ev.get("cause", "Unknown anomaly")
        conf     = ev.get("confidence_pct", 50)
        summary  = ev.get("summary", "")
        param    = ev.get("parameter", "")
        tool     = ev.get("tool_id", "")

        if category == "sensor_anomaly":
            ev_detail = ev.get("evidence", [{}])[0] if ev.get("evidence") else {}
            z     = ev_detail.get("deviation_sigma", 0)
            rho   = ev_detail.get("yield_correlation_rho", 0)
            expl  = (
                f"{param} deviated {abs(z):.1f}σ from fleet mean on {tool}. "
                f"Fleet-wide Spearman correlation with yield: ρ={rho:+.3f}. "
                f"{summary}"
            )
        elif category == "defect_contamination":
            ev_detail = ev.get("evidence", [{}])[0] if ev.get("evidence") else {}
            z     = ev_detail.get("deviation_sigma", 0)
            expl  = (
                f"Elevated {param} defect density detected ({abs(z):.1f}σ above step average). "
                f"{summary}"
            )
        else:
            expl = summary

        ranked.append({
            "rank": i,
            "cause": cause,
            "confidence_pct": conf,
            "explanation": expl,
            "implicated_parameter": param,
            "implicated_tool": tool,
        })

    top = evidence_list[0]
    narrative = (
        f"Statistical analysis of lot {lot_id} identified {len(evidence_list)} anomalous signal(s). "
        f"The highest-confidence finding is: {top.get('cause', 'an uncharacterised anomaly')} "
        f"(confidence {top.get('confidence_pct', 0):.0f}%). "
        f"{top.get('summary', '')}"
    )

    return {
        "narrative":             narrative,
        "ranked_causes":         ranked,
        "recommended_next_step": (
            f"Prioritise investigation of {top.get('parameter', 'the flagged parameter')} "
            f"on {top.get('tool_id', 'the implicated tool')}."
        ),
        "source_mode": "fallback",
    }


def _fallback_corrective_actions(root_cause: Dict[str, Any]) -> List[Dict[str, str]]:
    """
    Build fallback corrective actions from the root cause dict without calling the LLM.
    """
    category  = root_cause.get("category", "")
    parameter = root_cause.get("parameter", "") or root_cause.get("implicated_parameter", "")
    tool_id   = root_cause.get("tool_id", "") or root_cause.get("implicated_tool", "")
    cause     = root_cause.get("cause", "the identified anomaly")

    # Sensor anomaly specific actions
    if category == "sensor_anomaly" or "sensor" in category:
        return [
            {
                "action": f"Schedule immediate preventive maintenance on {tool_id or 'the implicated tool'} targeting the {parameter or 'anomalous parameter'} subsystem",
                "rationale": f"The {parameter} excursion of {abs(root_cause.get('evidence', [{}])[0].get('deviation_sigma', 0) if root_cause.get('evidence') else 0):.1f}σ indicates hardware degradation.",
                "urgency": "HIGH",
                "owner": "Equipment Engineering",
            },
            {
                "action": f"Run a qualification wafer on {tool_id or 'the implicated tool'} to confirm {parameter or 'parameter'} is back within spec before releasing lots",
                "rationale": "Qualification wafers verify corrective action effectiveness before production resumption.",
                "urgency": "HIGH",
                "owner": "Process Engineering",
            },
            {
                "action": f"Tighten SPC control limit for {parameter or 'the anomalous parameter'} by 20% and add auto-hold on exceedance",
                "rationale": "Tighter limits catch drift earlier and prevent yield loss accumulation.",
                "urgency": "MEDIUM",
                "owner": "Process Control",
            },
            {
                "action": f"Review last 30 lots processed on {tool_id or 'the implicated tool'} for temporal yield correlation with {parameter}",
                "rationale": "Confirms onset time and extent of yield impact before the excursion was detected.",
                "urgency": "MEDIUM",
                "owner": "Yield Engineering",
            },
        ]

    # Defect contamination
    if category == "defect_contamination" or "defect" in category:
        defect_type = parameter or "particle"
        return [
            {
                "action": f"Perform a full chamber clean on {tool_id or 'the implicated tool'} followed by a particle qualification run",
                "rationale": f"Elevated {defect_type} density indicates chamber contamination requiring cleaning.",
                "urgency": "HIGH",
                "owner": "Equipment Engineering",
            },
            {
                "action": "Inspect and replace the electrostatic chuck (ESC) if particle source is confirmed at wafer backside",
                "rationale": "Degraded ESC ceramic is a known particle source at advanced nodes.",
                "urgency": "HIGH",
                "owner": "Equipment Engineering",
            },
            {
                "action": "Increase in-line defect monitoring frequency to every 5 lots until counts normalise",
                "rationale": "Higher monitoring cadence enables early detection of contamination recurrence.",
                "urgency": "MEDIUM",
                "owner": "Yield Engineering",
            },
        ]

    # Tool performance / generic
    return [
        {
            "action": f"Initiate a full tool qualification (TQ) run on {tool_id or 'the implicated tool'} with process control wafers",
            "rationale": f"Systematic TQ is required to characterise the scope of '{cause}'.",
            "urgency": "HIGH",
            "owner": "Equipment Engineering",
        },
        {
            "action": "Compare tool PM history against the yield trend; escalate if no recent PM was performed",
            "rationale": "Accumulated wear between preventive maintenance events is a leading cause of tool performance decline.",
            "urgency": "HIGH",
            "owner": "Yield Engineering",
        },
        {
            "action": "Temporarily route lots away from the implicated tool while investigation is ongoing",
            "rationale": "Prevents additional yield loss while root cause is being confirmed.",
            "urgency": "MEDIUM",
            "owner": "Fab Operations",
        },
    ]


def _fallback_answer(query: str, context: str) -> Dict[str, Any]:
    """
    Build a grounded fallback answer from the structured context string
    produced by the /api/analysis/chat router.

    The context lines use key=value format, e.g.:
        Lot: W2401-0083  node=3nm  step=etch  tool=ETCH-03  recipe=R-ETH-04
             yield=71.99%  low_yield=True
        Sensor readings (mean): etch_temp_c=188.42, rf_power_w=379.1
        Defects: {'particle': 8, 'void': 3}  mean_density=0.2810/cm2
        Top root-cause candidates: Abnormal etch_temp_c on ETCH-03 (38.0% confidence); ...

    For the fleet-level (no lot) case, context is "No specific lot context provided."
    """
    query_lower = query.lower()

    # ── Extract structured fields from the context string ──────────────────
    # Lot line: "Lot: W2401-0083  node=3nm  step=etch  tool=ETCH-03 ..."
    lot_match    = re.search(r"Lot:\s*(\S+)", context)
    yield_match  = re.search(r"yield=([0-9.]+)%", context)
    low_match    = re.search(r"low_yield=(True|False)", context)
    tool_match   = re.search(r"tool=([A-Z]+-\d+)", context)
    step_match   = re.search(r"step=(\w+)", context)
    recipe_match = re.search(r"recipe=(\S+)", context)
    node_match   = re.search(r"node=(\w+)", context)

    lot_id    = lot_match.group(1)   if lot_match    else None
    yield_pct = yield_match.group(1) if yield_match  else None
    low_yield = low_match.group(1)   if low_match    else None
    tool_id   = tool_match.group(1)  if tool_match   else None
    step      = step_match.group(1)  if step_match   else None
    recipe    = recipe_match.group(1) if recipe_match else None
    node      = node_match.group(1)  if node_match   else None

    # Sensor readings: "Sensor readings (mean): param=val, param=val"
    sensor_match = re.search(r"Sensor readings \(mean\):\s*(.+)", context)
    sensors_str  = sensor_match.group(1).strip() if sensor_match else None

    # Defect info: "Defects: {'particle': 8, 'void': 3}  mean_density=0.2810/cm2"
    defect_line  = re.search(r"Defects:\s*(\{[^}]+\})\s*mean_density=([0-9.]+)", context)
    defect_types = defect_line.group(1) if defect_line else None
    mean_density = defect_line.group(2) if defect_line else None

    # Top candidates: "Top root-cause candidates: X (N% confidence); Y (M% confidence)"
    cand_match = re.search(r"Top root-cause candidates:\s*(.+)", context)
    candidates_str = cand_match.group(1).strip() if cand_match else None

    # ── No-context path (fleet-level query) ────────────────────────────────
    if not lot_id:
        answer = (
            "No specific lot was selected. "
            "To get a detailed yield analysis, select a lot in the context dropdown. "
            "Fleet-level statistics show the pattern detector has identified "
            "etch temperature on ETCH-03 and RF power on DEP-02 as the top "
            "parameters correlated with yield loss in the current dataset. "
            "Use the Root Cause Analysis tab to investigate a specific lot."
        )
        return {"answer": answer, "source_mode": "fallback", "query": query}

    # ── Build a grounded, query-aware answer ───────────────────────────────
    parts = []

    # Opening: lot ID + yield
    yield_flag_str = ""
    if yield_pct:
        is_low = low_yield == "True" or (yield_pct and float(yield_pct) < 82)
        yield_flag_str = " (below the 82% low-yield threshold)" if is_low else " (within acceptable range)"
    lot_line = f"Lot {lot_id}"
    if node:       lot_line += f" is a {node} lot"
    if step:       lot_line += f" processed on the {step} step"
    if tool_id:    lot_line += f" using tool {tool_id}"
    if recipe:     lot_line += f" with recipe {recipe}"
    if yield_pct:  lot_line += f", achieving {yield_pct}% yield{yield_flag_str}."
    else:          lot_line += "."
    parts.append(lot_line)

    # Root cause candidates — most relevant to query intent
    if candidates_str:
        if any(kw in query_lower for kw in ("cause", "root", "why", "reason", "issue", "problem")):
            parts.append(
                f"The top root-cause candidates are: {candidates_str}. "
                "Expand each candidate in the Root Cause Analysis tab to see the supporting sensor evidence."
            )
        elif any(kw in query_lower for kw in ("tool", "inspect", "check", "equipment")):
            parts.append(
                f"Based on the pattern detection results, prioritise inspection of tool {tool_id or 'the process tool'}. "
                f"The top signal is: {candidates_str.split(';')[0].strip()}."
            )
        elif any(kw in query_lower for kw in ("corrective", "action", "fix", "recommend", "step")):
            parts.append(
                f"The most relevant root-cause finding is: {candidates_str.split(';')[0].strip()}. "
                "Use the Corrective Actions section in the Root Cause Analysis tab for "
                f"specific actions targeting {tool_id or 'the implicated tool'}."
            )
        else:
            parts.append(f"Root-cause signals: {candidates_str}.")

    # Sensor data — include if relevant or no candidates
    if sensors_str and any(kw in query_lower for kw in ("sensor", "temp", "pressure", "power", "rf", "parameter", "drift")):
        parts.append(f"Sensor readings for this lot: {sensors_str}.")
    elif sensors_str and not candidates_str:
        parts.append(f"Sensor readings: {sensors_str}.")

    # Defect data — include if defect-related query or high density
    if defect_types and mean_density:
        if any(kw in query_lower for kw in ("defect", "particle", "contamination", "density", "scratch", "void")):
            parts.append(
                f"Defect profile: {defect_types}, mean density {mean_density}/cm\u00b2. "
                "Elevated particle density is a strong indicator of chamber contamination."
            )
        elif float(mean_density) > 0.15:
            parts.append(
                f"Note: elevated defect density detected ({mean_density}/cm\u00b2) — "
                "this level typically correlates with yield loss at advanced nodes."
            )

    # Closing guidance if answer is short
    if len(parts) < 2:
        parts.append(
            f"Use the Root Cause Analysis tab to view the full ranked evidence for lot {lot_id}."
        )

    return {
        "answer":      " ".join(parts),
        "source_mode": "fallback",
        "query":       query,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_root_cause(
    lot_id: str,
    evidence_list: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Call watsonx.ai to generate a root-cause narrative from structured evidence.

    Parameters
    ----------
    lot_id        : Lot identifier (used for context in the prompt).
    evidence_list : List of candidate dicts from rank_root_cause_candidates().

    Returns
    -------
    dict with keys: narrative, ranked_causes, recommended_next_step, source_mode
    """
    if not _is_watsonx_available():
        logger.debug("watsonx unavailable — using fallback for analyze_root_cause")
        return _fallback_root_cause(lot_id, evidence_list)

    prompt = _build_root_cause_prompt(lot_id, evidence_list)
    raw    = _call_model(prompt)

    if raw is None:
        return _fallback_root_cause(lot_id, evidence_list)

    parsed = _extract_json(raw)
    if isinstance(parsed, dict) and "ranked_causes" in parsed:
        parsed["source_mode"] = "watsonx"
        return parsed

    # Malformed JSON — build from raw text + fallback structure
    logger.warning("analyze_root_cause: could not parse LLM JSON, using hybrid response")
    result = _fallback_root_cause(lot_id, evidence_list)
    result["narrative"]   = raw.strip()[:1200]  # use LLM text as narrative
    result["source_mode"] = "watsonx_raw"
    return result


def generate_corrective_actions(
    root_cause: Dict[str, Any],
) -> List[Dict[str, str]]:
    """
    Call watsonx.ai to generate specific corrective actions for a root cause.

    Parameters
    ----------
    root_cause : A candidate dict from rank_root_cause_candidates() or
                 a ranked_cause entry from analyze_root_cause().

    Returns
    -------
    list of action dicts with keys: action, rationale, urgency, owner
    """
    if not _is_watsonx_available():
        logger.debug("watsonx unavailable — using fallback for generate_corrective_actions")
        return _fallback_corrective_actions(root_cause)

    prompt = _build_corrective_actions_prompt(root_cause)
    raw    = _call_model(prompt)

    if raw is None:
        return _fallback_corrective_actions(root_cause)

    parsed = _extract_json(raw)
    if isinstance(parsed, list) and len(parsed) > 0:
        # Validate each action has required fields
        required = {"action", "rationale", "urgency", "owner"}
        valid = [a for a in parsed if isinstance(a, dict) and required.issubset(a.keys())]
        if valid:
            return valid

    logger.warning("generate_corrective_actions: could not parse LLM JSON, using fallback")
    return _fallback_corrective_actions(root_cause)


def answer_engineer_query(
    query: str,
    context: str,
) -> Dict[str, Any]:
    """
    Answer a free-text engineering question grounded in the supplied context.

    Parameters
    ----------
    query   : Engineer's natural-language question.
    context : Relevant lot/sensor/defect data as a formatted string.

    Returns
    -------
    dict with keys: answer, source_mode, query
    """
    if not _is_watsonx_available():
        logger.debug("watsonx unavailable — using fallback for answer_engineer_query")
        return _fallback_answer(query, context)

    prompt = _build_query_prompt(query, context)
    raw    = _call_model(prompt)

    if raw is None:
        return _fallback_answer(query, context)

    return {
        "answer":      raw.strip(),
        "source_mode": "watsonx",
        "query":       query,
    }


# ---------------------------------------------------------------------------
# Status helper (used by health check / docs)
# ---------------------------------------------------------------------------

def watsonx_status() -> Dict[str, Any]:
    """Return current watsonx integration status for display in the API."""
    return {
        "sdk_installed":   _SDK_AVAILABLE,
        "credentials_set": bool(_API_KEY) and bool(_PROJECT_ID),
        "model_id":        _MODEL_ID,
        "url":             _URL,
        "mode":            "live" if _is_watsonx_available() else "fallback",
    }
