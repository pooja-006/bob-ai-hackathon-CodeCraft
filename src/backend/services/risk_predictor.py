"""
risk_predictor.py
=================
Trains a RandomForestClassifier on historical wafer lot data to predict
whether an upcoming lot will have low yield (yield_pct < 82%).

Public API
----------
predict_batch_risk(params: dict) -> dict
    Accept a dict of process parameters for an upcoming lot and return:
      {
        "risk_score":      float  0.0–1.0  (probability of low yield),
        "risk_flag":       bool            (True if risk_score >= 0.5),
        "risk_label":      str             ("HIGH" | "MEDIUM" | "LOW"),
        "top_risk_factors": list[dict]     each: {feature, importance, value}
      }

The model is trained once on first import and cached in memory.
An optional joblib cache file is written to src/backend/model_cache/
so re-starts are fast.  Training is deterministic (random_state=42).
"""

from __future__ import annotations

import os
import warnings
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder

from .data_loader import load_full_feature_matrix

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

RANDOM_STATE = 42
LOW_YIELD_THRESHOLD = 82.0          # must match generate_data.py / pattern_detector.py
HIGH_RISK_CUTOFF = 0.50             # probability >= this -> HIGH risk flag
MEDIUM_RISK_CUTOFF = 0.25           # probability >= this -> MEDIUM risk

_HERE = os.path.dirname(__file__)
CACHE_DIR = os.path.join(_HERE, "..", "model_cache")
MODEL_PATH = os.path.join(CACHE_DIR, "rf_yield_risk.joblib")
ENCODER_PATH = os.path.join(CACHE_DIR, "label_encoders.joblib")

# ---------------------------------------------------------------------------
# Feature columns used for training
# ---------------------------------------------------------------------------

# Categorical columns that will be label-encoded
CATEGORICAL_COLS = ["node", "process_step", "tool_id", "recipe_id", "operator"]

# Numeric sensor feature columns (all start with "sensor_")
# Defect features
DEFECT_FEATURE_COLS = [
    "defect_count",
    "defect_density_mean",
    "defect_density_max",
    "particle_density_mean",
    "particle_count",
    "alert_readings_count",
]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_sensor_cols(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if c.startswith("sensor_")]


def _build_feature_matrix(df: pd.DataFrame, encoders: dict) -> pd.DataFrame:
    """
    Apply label encoders to categorical columns and return a numeric DataFrame.
    Unknown categories are mapped to -1 (unseen at training time).
    """
    out = df.copy()
    for col, enc in encoders.items():
        if col in out.columns:
            known = set(enc.classes_)
            out[col] = out[col].apply(lambda v: v if v in known else "__unknown__")
            # Add __unknown__ to classes if not already present
            if "__unknown__" not in known:
                enc.classes_ = np.append(enc.classes_, "__unknown__")
            out[col] = enc.transform(out[col].astype(str))
        else:
            out[col] = -1
    return out


def _select_features(df: pd.DataFrame, sensor_cols: list[str]) -> list[str]:
    feature_cols = CATEGORICAL_COLS + sensor_cols + DEFECT_FEATURE_COLS
    return [c for c in feature_cols if c in df.columns]


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def train_model(
    df: Optional[pd.DataFrame] = None,
    force_retrain: bool = False,
) -> Tuple[RandomForestClassifier, dict, List[str]]:
    """
    Train (or load from cache) the yield-risk RandomForestClassifier.

    Returns
    -------
    (model, encoders, feature_cols)
    """
    os.makedirs(CACHE_DIR, exist_ok=True)

    if not force_retrain and os.path.exists(MODEL_PATH) and os.path.exists(ENCODER_PATH):
        model = joblib.load(MODEL_PATH)
        encoders = joblib.load(ENCODER_PATH)
        # Rebuild feature list from saved model
        feature_cols = list(model.feature_names_in_) if hasattr(model, "feature_names_in_") else []
        return model, encoders, feature_cols

    if df is None:
        df = load_full_feature_matrix()

    # ── Fit label encoders on training data ─────────────────────────────────
    encoders: dict[str, LabelEncoder] = {}
    for col in CATEGORICAL_COLS:
        if col in df.columns:
            le = LabelEncoder()
            le.fit(df[col].astype(str))
            encoders[col] = le

    df_enc = _build_feature_matrix(df, encoders)
    sensor_cols = _get_sensor_cols(df_enc)
    feature_cols = _select_features(df_enc, sensor_cols)
    feature_cols = [c for c in feature_cols if c in df_enc.columns]

    X = df_enc[feature_cols].fillna(0).values
    y = df_enc["low_yield_flag"].values

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = RandomForestClassifier(
            n_estimators=200,
            max_depth=8,
            min_samples_leaf=3,
            random_state=RANDOM_STATE,
            class_weight="balanced",
        )
        model.fit(X, y)

    # Attach feature names so we can reconstruct feature_cols after loading
    model.feature_names_in_ = np.array(feature_cols)

    joblib.dump(model, MODEL_PATH)
    joblib.dump(encoders, ENCODER_PATH)

    return model, encoders, feature_cols


# ---------------------------------------------------------------------------
# Module-level singleton (lazy-loaded on first predict call)
# ---------------------------------------------------------------------------

_MODEL: Optional[RandomForestClassifier] = None
_ENCODERS: Optional[dict] = None
_FEATURE_COLS: List[str] = []


def _ensure_model_loaded() -> None:
    global _MODEL, _ENCODERS, _FEATURE_COLS
    if _MODEL is None:
        _MODEL, _ENCODERS, _FEATURE_COLS = train_model()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def predict_batch_risk(params: dict[str, Any]) -> dict[str, Any]:
    """
    Predict yield risk for an upcoming lot.

    Parameters
    ----------
    params : dict
        Keys should match the lot/sensor/defect feature names.  At minimum:
          node, process_step, tool_id, recipe_id, operator
        Optional numeric overrides for any sensor_ or defect feature.

    Returns
    -------
    dict with keys:
      risk_score        float [0, 1]
      risk_flag         bool
      risk_label        "HIGH" | "MEDIUM" | "LOW"
      top_risk_factors  list of {feature, value, importance, direction}
    """
    _ensure_model_loaded()

    # Build a single-row DataFrame from params
    row = {col: params.get(col, "__unknown__") for col in CATEGORICAL_COLS}

    # Fill sensor features with fleet mean if not provided
    full_df = load_full_feature_matrix()
    sensor_cols = _get_sensor_cols(full_df)
    fleet_means = full_df[sensor_cols + DEFECT_FEATURE_COLS].mean()

    for col in sensor_cols + DEFECT_FEATURE_COLS:
        row[col] = float(params.get(col, fleet_means.get(col, 0.0)))

    input_df = pd.DataFrame([row])
    input_enc = _build_feature_matrix(input_df, _ENCODERS)

    # Align to trained feature columns
    for col in _FEATURE_COLS:
        if col not in input_enc.columns:
            input_enc[col] = 0
    input_enc = input_enc[_FEATURE_COLS].fillna(0)

    risk_score = float(_MODEL.predict_proba(input_enc)[0][1])
    risk_flag = risk_score >= HIGH_RISK_CUTOFF

    if risk_score >= HIGH_RISK_CUTOFF:
        risk_label = "HIGH"
    elif risk_score >= MEDIUM_RISK_CUTOFF:
        risk_label = "MEDIUM"
    else:
        risk_label = "LOW"

    # ── Top contributing features ────────────────────────────────────────────
    importances = _MODEL.feature_importances_
    factor_list = []
    for feat, imp in zip(_FEATURE_COLS, importances):
        val = input_enc.iloc[0][feat]
        fleet_mean = float(fleet_means.get(feat, np.nan))
        if feat in CATEGORICAL_COLS:
            direction = "categorical"
        else:
            direction = "high" if val > fleet_mean else "low"
        factor_list.append({
            "feature": feat,
            "value": round(float(val), 4),
            "fleet_mean": round(fleet_mean, 4) if not np.isnan(fleet_mean) else None,
            "importance": round(float(imp), 4),
            "direction": direction,
        })

    factor_list.sort(key=lambda x: x["importance"], reverse=True)

    return {
        "risk_score": round(risk_score, 4),
        "risk_flag": risk_flag,
        "risk_label": risk_label,
        "top_risk_factors": factor_list[:8],
    }


def evaluate_model() -> dict[str, Any]:
    """
    Return basic in-sample evaluation metrics for the trained model.
    Used in tests and the setup guide to verify the model trained correctly.
    """
    _ensure_model_loaded()
    df = load_full_feature_matrix()
    df_enc = _build_feature_matrix(df.copy(), _ENCODERS)

    for col in _FEATURE_COLS:
        if col not in df_enc.columns:
            df_enc[col] = 0

    X = df_enc[_FEATURE_COLS].fillna(0)
    y_true = df_enc["low_yield_flag"].values
    y_pred = _MODEL.predict(X)
    y_prob = _MODEL.predict_proba(X)[:, 1]

    from sklearn.metrics import (
        accuracy_score, precision_score, recall_score, f1_score, roc_auc_score
    )

    return {
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "precision": round(float(precision_score(y_true, y_pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_true, y_pred, zero_division=0)), 4),
        "f1": round(float(f1_score(y_true, y_pred, zero_division=0)), 4),
        "roc_auc": round(float(roc_auc_score(y_true, y_prob)), 4),
        "n_samples": int(len(y_true)),
        "n_positive": int(y_true.sum()),
    }
