"""
test_pattern_detector.py
========================
Unit and integration tests for pattern_detector.py and risk_predictor.py.

Run with:
    pytest src/backend/tests/test_pattern_detector.py -v
"""

from __future__ import annotations

import sys
import os

# Ensure src/backend is importable when running from the repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import pytest
import pandas as pd
import numpy as np

from src.backend.services.data_loader import (
    load_lots,
    load_sensors,
    load_defects,
    load_full_feature_matrix,
    get_lot,
    get_lot_sensors,
    get_lot_defects,
)
from src.backend.services.pattern_detector import (
    detect_yield_correlations,
    detect_tool_yield_impact,
    detect_defect_outliers,
    rank_root_cause_candidates,
    fleet_summary,
    LOW_YIELD_THRESHOLD,
)
from src.backend.services.risk_predictor import (
    predict_batch_risk,
    evaluate_model,
    train_model,
)


# ---------------------------------------------------------------------------
# Fixtures (pytest)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def lots():
    return load_lots()


@pytest.fixture(scope="module")
def sensors():
    return load_sensors()


@pytest.fixture(scope="module")
def defects():
    return load_defects()


@pytest.fixture(scope="module")
def features():
    return load_full_feature_matrix()


# ---------------------------------------------------------------------------
# Data loader tests
# ---------------------------------------------------------------------------

class TestDataLoader:
    def test_lots_row_count(self, lots):
        assert len(lots) == 500

    def test_sensors_row_count(self, sensors):
        assert len(sensors) == 5000

    def test_defects_row_count(self, defects):
        assert len(defects) >= 3000

    def test_lots_columns(self, lots):
        required = {"lot_id", "node", "process_step", "tool_id", "recipe_id",
                    "yield_pct", "low_yield_flag", "timestamp"}
        assert required.issubset(lots.columns)

    def test_sensors_columns(self, sensors):
        required = {"reading_id", "lot_id", "tool_id", "parameter_name",
                    "parameter_value", "alert_flag"}
        assert required.issubset(sensors.columns)

    def test_defects_columns(self, defects):
        required = {"defect_id", "lot_id", "wafer_id", "defect_type",
                    "defect_density"}
        assert required.issubset(defects.columns)

    def test_no_null_lot_ids(self, lots):
        assert lots["lot_id"].isna().sum() == 0

    def test_yield_pct_in_range(self, lots):
        assert (lots["yield_pct"] >= 0).all()
        assert (lots["yield_pct"] <= 100).all()

    def test_referential_integrity_sensors(self, lots, sensors):
        lot_ids = set(lots["lot_id"])
        sensor_lot_ids = set(sensors["lot_id"])
        assert sensor_lot_ids.issubset(lot_ids), (
            "Sensor records reference lot_ids not in wafer_lots"
        )

    def test_referential_integrity_defects(self, lots, defects):
        lot_ids = set(lots["lot_id"])
        defect_lot_ids = set(defects["lot_id"])
        assert defect_lot_ids.issubset(lot_ids), (
            "Defect records reference lot_ids not in wafer_lots"
        )

    def test_feature_matrix_row_count(self, features, lots):
        assert len(features) == len(lots)

    def test_get_lot_found(self, lots):
        first_id = lots.iloc[0]["lot_id"]
        row = get_lot(first_id)
        assert row["lot_id"] == first_id

    def test_get_lot_not_found(self):
        with pytest.raises(KeyError):
            get_lot("NONEXISTENT-LOT")


# ---------------------------------------------------------------------------
# Pattern detector tests
# ---------------------------------------------------------------------------

class TestDetectYieldCorrelations:
    def test_returns_dict(self, lots, sensors):
        result = detect_yield_correlations(lots, sensors)
        assert isinstance(result, dict)

    def test_all_values_in_range(self, lots, sensors):
        result = detect_yield_correlations(lots, sensors)
        for param, rho in result.items():
            assert -1.0 <= rho <= 1.0, f"{param} rho={rho} out of range"

    def test_etch_temp_has_negative_correlation(self, lots, sensors):
        """
        P1: ETCH-03 etch_temp_c is elevated on low-yield lots ->
        etch_temp_c should show a negative correlation with yield.
        """
        result = detect_yield_correlations(lots, sensors)
        assert "etch_temp_c" in result, (
            "etch_temp_c not found in correlations — injected pattern P1 not detected"
        )
        assert result["etch_temp_c"] < 0, (
            f"Expected negative correlation for etch_temp_c, got {result['etch_temp_c']}"
        )

    def test_rf_power_has_negative_correlation_on_dep02(self, lots, sensors):
        """
        P2: DEP-02 rf_power_w is elevated on low-yield lots.
        The fleet-wide signal is diluted (only 13 DEP-02+R-NIT-07 lots out of 500).
        Verify the per-tool Spearman correlation on DEP-02 alone is negative.
        """
        import scipy.stats as sp
        dep02_sensor = sensors[sensors["tool_id"] == "DEP-02"]
        dep02_lots = lots[lots["tool_id"] == "DEP-02"]

        pivot = (
            dep02_sensor
            .groupby(["lot_id", "parameter_name"])["parameter_value"]
            .mean()
            .unstack("parameter_name")
            .reset_index()
        )
        merged = pivot.merge(dep02_lots[["lot_id", "yield_pct"]], on="lot_id", how="inner")
        assert "rf_power_w" in merged.columns, "rf_power_w not recorded for DEP-02 lots"

        col = merged["rf_power_w"].dropna()
        yields = merged.loc[col.index, "yield_pct"]
        rho, pval = sp.spearmanr(col, yields)
        assert rho < 0, (
            f"Expected negative per-tool rho for DEP-02 rf_power_w, got rho={rho:.3f} p={pval:.3f}"
        )

    def test_sorted_by_abs_rho(self, lots, sensors):
        result = detect_yield_correlations(lots, sensors)
        rhos = list(result.values())
        abs_rhos = [abs(r) for r in rhos]
        assert abs_rhos == sorted(abs_rhos, reverse=True)

    def test_empty_sensors(self, lots):
        empty = pd.DataFrame(columns=["lot_id", "parameter_name", "parameter_value"])
        result = detect_yield_correlations(lots, empty)
        assert result == {}


class TestDetectToolYieldImpact:
    def test_returns_dataframe(self, lots):
        result = detect_tool_yield_impact(lots)
        assert isinstance(result, pd.DataFrame)

    def test_etch03_flagged(self, lots):
        """ETCH-03 produces many low-yield lots (P1) -> should be flagged."""
        result = detect_tool_yield_impact(lots)
        etch03 = result[result["tool_id"] == "ETCH-03"]
        assert not etch03.empty, "ETCH-03 not in tool impact table"
        assert etch03.iloc[0]["low_yield_flag"] == 1, (
            f"ETCH-03 not flagged as low-yield tool. "
            f"mean_yield={etch03.iloc[0]['mean_yield']:.1f}, z={etch03.iloc[0]['yield_z_score']:.2f}"
        )

    def test_z_scores_computed(self, lots):
        result = detect_tool_yield_impact(lots)
        assert "yield_z_score" in result.columns
        assert result["yield_z_score"].isna().sum() == 0


class TestDetectDefectOutliers:
    def test_returns_dataframe(self, defects, lots):
        result = detect_defect_outliers(defects, lots)
        assert isinstance(result, pd.DataFrame)

    def test_required_columns(self, defects, lots):
        result = detect_defect_outliers(defects, lots)
        for col in ["lot_id", "defect_type", "mean_density", "z_score", "is_outlier"]:
            assert col in result.columns

    def test_low_yield_lots_have_outlier_defects(self, defects, lots):
        """
        P3: low-yield lots should have high particle density outliers.
        """
        result = detect_defect_outliers(defects, lots)
        low_yield_ids = set(lots[lots["low_yield_flag"] == 1]["lot_id"])
        outlier_rows = result[result["is_outlier"] == 1]
        outlier_lots_in_low_yield = set(outlier_rows["lot_id"]) & low_yield_ids
        assert len(outlier_lots_in_low_yield) > 0, (
            "No outlier defect records found in low-yield lots — P3 not detected"
        )

    def test_particle_type_present(self, defects, lots):
        result = detect_defect_outliers(defects, lots)
        assert "particle" in result["defect_type"].values


class TestRankRootCauseCandidates:
    def _find_a_low_yield_lot(self, lots):
        low = lots[lots["low_yield_flag"] == 1]
        assert not low.empty, "No low-yield lots found in fixture data"
        return low.iloc[0]["lot_id"]

    def test_returns_list(self, lots, sensors, defects):
        lot_id = self._find_a_low_yield_lot(lots)
        result = rank_root_cause_candidates(lot_id, lots, sensors, defects)
        assert isinstance(result, list)

    def test_each_candidate_has_required_keys(self, lots, sensors, defects):
        lot_id = self._find_a_low_yield_lot(lots)
        candidates = rank_root_cause_candidates(lot_id, lots, sensors, defects)
        required_keys = {"cause", "category", "evidence", "confidence_pct", "summary", "tool_id"}
        for c in candidates:
            assert required_keys.issubset(c.keys()), (
                f"Candidate missing keys: {required_keys - c.keys()}"
            )

    def test_confidence_in_range(self, lots, sensors, defects):
        lot_id = self._find_a_low_yield_lot(lots)
        candidates = rank_root_cause_candidates(lot_id, lots, sensors, defects)
        for c in candidates:
            assert 0 <= c["confidence_pct"] <= 100

    def test_sorted_by_confidence_desc(self, lots, sensors, defects):
        lot_id = self._find_a_low_yield_lot(lots)
        candidates = rank_root_cause_candidates(lot_id, lots, sensors, defects)
        confs = [c["confidence_pct"] for c in candidates]
        assert confs == sorted(confs, reverse=True)

    def test_unknown_lot_returns_empty(self, lots, sensors, defects):
        result = rank_root_cause_candidates("NONEXISTENT", lots, sensors, defects)
        assert result == []

    def test_at_least_one_candidate_for_low_yield_lot(self, lots, sensors, defects):
        lot_id = self._find_a_low_yield_lot(lots)
        candidates = rank_root_cause_candidates(lot_id, lots, sensors, defects)
        assert len(candidates) >= 1, (
            f"Expected at least 1 candidate for low-yield lot {lot_id}"
        )


class TestFleetSummary:
    def test_returns_dict(self, lots, sensors, defects):
        result = fleet_summary(lots, sensors, defects)
        assert isinstance(result, dict)

    def test_required_keys(self, lots, sensors, defects):
        result = fleet_summary(lots, sensors, defects)
        for key in ["total_lots", "low_yield_lots", "mean_yield_pct",
                    "top_yield_correlated_params", "underperforming_tools"]:
            assert key in result

    def test_low_yield_lots_positive(self, lots, sensors, defects):
        result = fleet_summary(lots, sensors, defects)
        assert result["low_yield_lots"] > 0

    def test_mean_yield_reasonable(self, lots, sensors, defects):
        result = fleet_summary(lots, sensors, defects)
        assert 50 < result["mean_yield_pct"] < 100


# ---------------------------------------------------------------------------
# Risk predictor tests
# ---------------------------------------------------------------------------

class TestRiskPredictor:
    def test_healthy_lot_low_risk(self):
        """
        A lot with nominal parameters on a healthy tool should predict low risk.
        """
        params = {
            "node": "5nm",
            "process_step": "litho",
            "tool_id": "LIT-01",
            "recipe_id": "R-LIT-01",
            "operator": "op_alice",
        }
        result = predict_batch_risk(params)
        assert result["risk_score"] <= 0.5, (
            f"Expected low risk for healthy params, got {result['risk_score']}"
        )
        assert result["risk_label"] in ("LOW", "MEDIUM")

    def test_high_risk_etch03_hot(self):
        """
        A lot on ETCH-03 with elevated etch_temp should score higher risk.
        """
        params_normal = {
            "node": "3nm",
            "process_step": "etch",
            "tool_id": "ETCH-01",
            "recipe_id": "R-ETH-04",
            "operator": "op_alice",
            "sensor_etch_temp_c": 175.0,
        }
        params_hot = {
            **params_normal,
            "tool_id": "ETCH-03",
            "sensor_etch_temp_c": 190.0,
        }
        result_normal = predict_batch_risk(params_normal)
        result_hot = predict_batch_risk(params_hot)
        assert result_hot["risk_score"] >= result_normal["risk_score"], (
            f"Hot ETCH-03 should have >= risk than nominal ETCH-01: "
            f"{result_hot['risk_score']} vs {result_normal['risk_score']}"
        )

    def test_result_has_required_keys(self):
        result = predict_batch_risk({"process_step": "etch", "tool_id": "ETCH-01"})
        for key in ["risk_score", "risk_flag", "risk_label", "top_risk_factors"]:
            assert key in result

    def test_risk_score_in_range(self):
        result = predict_batch_risk({"process_step": "etch", "tool_id": "ETCH-01"})
        assert 0.0 <= result["risk_score"] <= 1.0

    def test_risk_flag_consistent_with_score(self):
        result = predict_batch_risk({"process_step": "etch", "tool_id": "ETCH-01"})
        expected_flag = result["risk_score"] >= 0.5
        assert result["risk_flag"] == expected_flag

    def test_top_risk_factors_list(self):
        result = predict_batch_risk({"process_step": "etch", "tool_id": "ETCH-01"})
        factors = result["top_risk_factors"]
        assert isinstance(factors, list)
        assert len(factors) > 0
        for f in factors:
            assert "feature" in f and "importance" in f

    def test_risk_factors_sorted_by_importance(self):
        result = predict_batch_risk({"process_step": "etch", "tool_id": "ETCH-01"})
        imps = [f["importance"] for f in result["top_risk_factors"]]
        assert imps == sorted(imps, reverse=True)


class TestModelEvaluation:
    def test_evaluate_returns_metrics(self):
        metrics = evaluate_model()
        for key in ["accuracy", "precision", "recall", "f1", "roc_auc"]:
            assert key in metrics

    def test_accuracy_above_threshold(self):
        """In-sample accuracy should be well above random (>= 0.85 on training data)."""
        metrics = evaluate_model()
        assert metrics["accuracy"] >= 0.85, (
            f"Model accuracy {metrics['accuracy']} too low"
        )

    def test_roc_auc_above_threshold(self):
        """ROC AUC should show the model has discriminative power."""
        metrics = evaluate_model()
        assert metrics["roc_auc"] >= 0.80, (
            f"ROC AUC {metrics['roc_auc']} too low — model may not have learned patterns"
        )

    def test_positive_class_present(self):
        metrics = evaluate_model()
        assert metrics["n_positive"] > 0
