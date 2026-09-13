"""
pattern_detector.py
===================
Statistical pattern detection engine.

Public API
----------
detect_yield_correlations(lots_df, sensors_df)
    -> dict[str, float]   (parameter -> Spearman correlation with yield_pct)

detect_defect_outliers(defects_df, lots_df)
    -> pd.DataFrame       (lot-level defect stats with outlier flags)

rank_root_cause_candidates(lot_id)
    -> list[dict]         ranked list of {cause, evidence, confidence_pct, direction}

All functions are pure (no side-effects) and work on the DataFrames they are
passed — no file I/O inside these functions so they are testable in isolation.
"""

from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
import pandas as pd
from scipy import stats


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LOW_YIELD_THRESHOLD = 82.0          # pp — must match generate_data.py
OUTLIER_Z_THRESHOLD = 2.0           # Z-score threshold for defect density outliers
MIN_SAMPLES_FOR_CORR = 10           # minimum group size to compute correlation
MAX_CANDIDATES = 10                 # maximum root-cause candidates to return


# ---------------------------------------------------------------------------
# 1. Yield-correlation analysis
# ---------------------------------------------------------------------------

def detect_yield_correlations(
    lots_df: pd.DataFrame,
    sensors_df: pd.DataFrame,
) -> Dict[str, float]:
    """
    Compute Spearman correlation between each sensor parameter's mean value
    (aggregated per lot) and the lot's yield_pct.

    Returns
    -------
    dict mapping parameter_name -> Spearman rho  (range [-1, +1]).
    Only parameters with abs(rho) >= 0.05 and p-value < 0.10 are included.
    """
    # Mean sensor value per lot per parameter
    pivot = (
        sensors_df
        .groupby(["lot_id", "parameter_name"])["parameter_value"]
        .mean()
        .unstack("parameter_name")
        .reset_index()
    )

    merged = pivot.merge(lots_df[["lot_id", "yield_pct"]], on="lot_id", how="inner")

    results: Dict[str, float] = {}
    param_cols = [c for c in merged.columns if c not in ("lot_id", "yield_pct")]

    for param in param_cols:
        col = merged[param].dropna()
        if len(col) < MIN_SAMPLES_FOR_CORR:
            continue
        aligned = merged.loc[col.index, "yield_pct"]
        rho, pval = stats.spearmanr(col, aligned)
        if np.isnan(rho):
            continue
        if abs(rho) >= 0.05 and pval < 0.10:
            results[param] = round(float(rho), 4)

    return dict(sorted(results.items(), key=lambda kv: abs(kv[1]), reverse=True))


# ---------------------------------------------------------------------------
# 2. Tool-level yield comparison
# ---------------------------------------------------------------------------

def detect_tool_yield_impact(lots_df: pd.DataFrame) -> pd.DataFrame:
    """
    For each (tool_id, process_step) pair compute mean yield and flag those
    whose mean yield is more than 1.5 standard deviations below the global mean.

    Returns a DataFrame with columns:
      tool_id, process_step, mean_yield, lot_count, yield_z_score, low_yield_flag
    """
    global_mean = lots_df["yield_pct"].mean()
    global_std = lots_df["yield_pct"].std()

    tool_stats = (
        lots_df
        .groupby(["tool_id", "process_step"])
        .agg(mean_yield=("yield_pct", "mean"), lot_count=("lot_id", "count"))
        .reset_index()
    )
    tool_stats["yield_z_score"] = (
        (tool_stats["mean_yield"] - global_mean) / global_std
    ).round(3)
    tool_stats["low_yield_flag"] = (tool_stats["yield_z_score"] < -1.5).astype(int)
    return tool_stats.sort_values("yield_z_score")


# ---------------------------------------------------------------------------
# 3. Defect outlier detection
# ---------------------------------------------------------------------------

def detect_defect_outliers(
    defects_df: pd.DataFrame,
    lots_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Aggregate defect_density per lot per defect_type.  Flag lots whose
    density Z-score exceeds OUTLIER_Z_THRESHOLD for that defect type.

    Returns a DataFrame with columns:
      lot_id, defect_type, mean_density, z_score, is_outlier, yield_pct
    """
    # Per-lot, per-defect-type mean density
    agg = (
        defects_df
        .groupby(["lot_id", "defect_type"])["defect_density"]
        .mean()
        .reset_index(name="mean_density")
    )

    # Z-score within each defect_type group
    def add_z(grp: pd.DataFrame) -> pd.DataFrame:
        mu = grp["mean_density"].mean()
        sd = grp["mean_density"].std()
        grp = grp.copy()
        grp["z_score"] = ((grp["mean_density"] - mu) / sd).round(3) if sd > 0 else 0.0
        return grp

    agg = agg.groupby("defect_type", group_keys=False).apply(add_z)
    agg["is_outlier"] = (agg["z_score"].abs() > OUTLIER_Z_THRESHOLD).astype(int)

    # Join yield for context
    agg = agg.merge(lots_df[["lot_id", "yield_pct"]], on="lot_id", how="left")
    return agg.sort_values("z_score", ascending=False)


# ---------------------------------------------------------------------------
# 4. Root-cause candidate ranking
# ---------------------------------------------------------------------------

def _sensor_evidence_for_lot(
    lot: pd.Series,
    all_lots: pd.DataFrame,
    all_sensors: pd.DataFrame,
) -> List[Dict[str, Any]]:
    """
    Return a list of sensor-based evidence items for a specific lot.
    Each item contains the parameter name, measured value, fleet mean,
    deviation in sigmas, and the correlation between that parameter and yield.
    """
    lot_sensors = all_sensors[all_sensors["lot_id"] == lot["lot_id"]]
    if lot_sensors.empty:
        return []

    # Fleet-wide stats per parameter (all lots on the same tool)
    same_tool = all_sensors[all_sensors["tool_id"] == lot["tool_id"]]
    fleet_stats = (
        same_tool
        .groupby("parameter_name")["parameter_value"]
        .agg(["mean", "std"])
        .rename(columns={"mean": "fleet_mean", "std": "fleet_std"})
    )

    # Lot-level mean per parameter
    lot_means = lot_sensors.groupby("parameter_name")["parameter_value"].mean()

    # Fleet-wide correlation: parameter mean per lot vs yield_pct
    corr_map = detect_yield_correlations(all_lots, all_sensors)

    evidence = []
    for param, lot_val in lot_means.items():
        if param not in fleet_stats.index:
            continue
        fleet_mean = fleet_stats.loc[param, "fleet_mean"]
        fleet_std = fleet_stats.loc[param, "fleet_std"]
        if fleet_std == 0 or np.isnan(fleet_std):
            continue
        z = (lot_val - fleet_mean) / fleet_std
        if abs(z) < 1.0:          # only flag meaningful deviations
            continue
        rho = corr_map.get(param, 0.0)
        evidence.append({
            "parameter": param,
            "lot_value": round(float(lot_val), 4),
            "fleet_mean": round(float(fleet_mean), 4),
            "deviation_sigma": round(float(z), 2),
            "yield_correlation_rho": rho,
        })

    # Sort by |rho| * |z| composite score
    evidence.sort(key=lambda e: abs(e["yield_correlation_rho"]) * abs(e["deviation_sigma"]), reverse=True)
    return evidence


def _defect_evidence_for_lot(
    lot: pd.Series,
    all_lots: pd.DataFrame,
    all_defects: pd.DataFrame,
) -> List[Dict[str, Any]]:
    """
    Return defect-type evidence for a specific lot: types that are statistically
    elevated compared to the fleet average for that process step.
    """
    lot_defects = all_defects[all_defects["lot_id"] == lot["lot_id"]]
    if lot_defects.empty:
        return []

    step_defects = all_defects[all_defects["process_step"] == lot["process_step"]]

    step_stats = (
        step_defects
        .groupby(["lot_id", "defect_type"])["defect_density"]
        .mean()
        .reset_index(name="density")
        .groupby("defect_type")["density"]
        .agg(["mean", "std"])
        .rename(columns={"mean": "fleet_mean", "std": "fleet_std"})
    )

    lot_type_means = lot_defects.groupby("defect_type")["defect_density"].mean()

    evidence = []
    for dtype, lot_density in lot_type_means.items():
        if dtype not in step_stats.index:
            continue
        fleet_mean = step_stats.loc[dtype, "fleet_mean"]
        fleet_std = step_stats.loc[dtype, "fleet_std"]
        if fleet_std == 0 or np.isnan(fleet_std):
            continue
        z = (lot_density - fleet_mean) / fleet_std
        if z > 1.5:
            evidence.append({
                "defect_type": dtype,
                "lot_density": round(float(lot_density), 4),
                "fleet_mean_density": round(float(fleet_mean), 4),
                "deviation_sigma": round(float(z), 2),
            })

    evidence.sort(key=lambda e: e["deviation_sigma"], reverse=True)
    return evidence


def _confidence_from_signals(sensor_ev: list, defect_ev: list, yield_pct: float) -> float:
    """
    Heuristic confidence score [0–100] for a root-cause candidate.

    Contributions:
      - Each sensor evidence item with |rho| > 0.15:  +15 pts
      - Each sensor evidence item with |rho| > 0.05:  +8 pts
      - Each defect evidence item with z > 2:         +12 pts
      - Each defect evidence item:                    +5 pts
      - Yield below threshold:                        +10 pts baseline
    """
    score = 0.0
    for e in sensor_ev:
        rho = abs(e["yield_correlation_rho"])
        score += 15 if rho > 0.15 else (8 if rho > 0.05 else 3)
    for e in defect_ev:
        score += 12 if e["deviation_sigma"] > 2 else 5
    if yield_pct < LOW_YIELD_THRESHOLD:
        score += 10
    return round(min(score, 99.0), 1)


def rank_root_cause_candidates(
    lot_id: str,
    lots_df: pd.DataFrame,
    sensors_df: pd.DataFrame,
    defects_df: pd.DataFrame,
) -> List[Dict[str, Any]]:
    """
    Analyse a specific lot and return a ranked list of root-cause candidates.

    Each candidate dict contains:
      cause           – human-readable label
      category        – 'sensor_anomaly' | 'defect_contamination' | 'tool_performance'
      evidence        – list of supporting evidence dicts
      confidence_pct  – estimated confidence 0–100
      direction       – 'high' | 'low' (whether the signal is above or below nominal)
      tool_id         – implicated tool
      parameter       – implicated parameter (sensor candidates only)

    Parameters are DataFrames from data_loader so the function is testable
    without touching the filesystem.
    """
    try:
        lot_rows = lots_df[lots_df["lot_id"] == lot_id]
        if lot_rows.empty:
            return []
        lot = lot_rows.iloc[0]
    except Exception:
        return []

    sensor_ev = _sensor_evidence_for_lot(lot, lots_df, sensors_df)
    defect_ev = _defect_evidence_for_lot(lot, lots_df, defects_df)
    tool_stats = detect_tool_yield_impact(lots_df)

    candidates: List[Dict[str, Any]] = []

    # -- Sensor-based candidates -------------------------------------------
    for ev in sensor_ev[:5]:
        param = ev["parameter"]
        rho = ev["yield_correlation_rho"]
        z = ev["deviation_sigma"]
        direction = "high" if z > 0 else "low"
        confidence = _confidence_from_signals([ev], [], lot["yield_pct"])

        candidates.append({
            "cause": f"Abnormal {param} on {lot['tool_id']}",
            "category": "sensor_anomaly",
            "parameter": param,
            "tool_id": lot["tool_id"],
            "direction": direction,
            "evidence": [ev],
            "confidence_pct": confidence,
            "summary": (
                f"{param} is {abs(z):.1f}σ {'above' if direction == 'high' else 'below'} "
                f"fleet mean on {lot['tool_id']}. "
                f"Fleet-wide correlation with yield: ρ={rho:+.3f}."
            ),
        })

    # -- Defect-based candidates -------------------------------------------
    for ev in defect_ev[:3]:
        dtype = ev["defect_type"]
        z = ev["deviation_sigma"]
        confidence = _confidence_from_signals([], [ev], lot["yield_pct"])

        candidates.append({
            "cause": f"Elevated {dtype} defect density on lot {lot_id}",
            "category": "defect_contamination",
            "parameter": "defect_density",
            "tool_id": lot["tool_id"],
            "direction": "high",
            "evidence": [ev],
            "confidence_pct": confidence,
            "summary": (
                f"{dtype} density {ev['lot_density']:.4f}/cm² is "
                f"{z:.1f}σ above the fleet mean for {lot['process_step']} step. "
                f"Typical {dtype} density: {ev['fleet_mean_density']:.4f}/cm²."
            ),
        })

    # -- Tool-performance candidate (if tool is flagged fleet-wide) --------
    tool_row = tool_stats[
        (tool_stats["tool_id"] == lot["tool_id"]) &
        (tool_stats["low_yield_flag"] == 1)
    ]
    if not tool_row.empty:
        t = tool_row.iloc[0]
        candidates.append({
            "cause": f"Tool {lot['tool_id']} shows sustained below-average yield",
            "category": "tool_performance",
            "parameter": None,
            "tool_id": lot["tool_id"],
            "direction": "low",
            "evidence": [{
                "tool_id": lot["tool_id"],
                "mean_yield": round(float(t["mean_yield"]), 2),
                "lot_count": int(t["lot_count"]),
                "yield_z_score": float(t["yield_z_score"]),
            }],
            "confidence_pct": round(
                min(abs(float(t["yield_z_score"])) * 20, 95), 1
            ),
            "summary": (
                f"Tool {lot['tool_id']} has a fleet-wide mean yield of "
                f"{t['mean_yield']:.1f}% ({t['yield_z_score']:.2f}σ below global mean) "
                f"across {int(t['lot_count'])} lots."
            ),
        })

    # -- Sort by confidence and cap ------------------------------------------
    candidates.sort(key=lambda c: c["confidence_pct"], reverse=True)
    return candidates[:MAX_CANDIDATES]


# ---------------------------------------------------------------------------
# 5. Fleet-wide summary (used by dashboard overview)
# ---------------------------------------------------------------------------

def fleet_summary(
    lots_df: pd.DataFrame,
    sensors_df: pd.DataFrame,
    defects_df: pd.DataFrame,
) -> Dict[str, Any]:
    """
    Return a high-level fleet summary dict for the dashboard header.
    """
    correlations = detect_yield_correlations(lots_df, sensors_df)
    tool_impact = detect_tool_yield_impact(lots_df)
    outliers = detect_defect_outliers(defects_df, lots_df)

    top_corr = list(correlations.items())[:5]
    bad_tools = tool_impact[tool_impact["low_yield_flag"] == 1][
        ["tool_id", "process_step", "mean_yield", "lot_count", "yield_z_score"]
    ].to_dict("records")
    top_outlier_lots = (
        outliers[outliers["is_outlier"] == 1]
        .sort_values("z_score", ascending=False)
        .head(10)[["lot_id", "defect_type", "mean_density", "z_score", "yield_pct"]]
        .to_dict("records")
    )

    return {
        "total_lots": len(lots_df),
        "low_yield_lots": int(lots_df["low_yield_flag"].sum()),
        "mean_yield_pct": round(float(lots_df["yield_pct"].mean()), 2),
        "top_yield_correlated_params": [
            {"parameter": k, "spearman_rho": v} for k, v in top_corr
        ],
        "underperforming_tools": bad_tools,
        "defect_outlier_lots": top_outlier_lots,
    }
