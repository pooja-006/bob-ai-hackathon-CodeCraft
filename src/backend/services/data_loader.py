"""
data_loader.py
==============
Loads the three fixture CSV files into pandas DataFrames and exposes a
pre-joined view used by both pattern_detector and risk_predictor.

All paths are resolved relative to the fixtures directory so the module
works regardless of the working directory the server is started from.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Tuple

import pandas as pd

# ---------------------------------------------------------------------------
# Fixture paths
# ---------------------------------------------------------------------------

_HERE = os.path.dirname(__file__)
FIXTURES_DIR = os.path.abspath(os.path.join(_HERE, "..", "..", "data", "fixtures"))


def _fixture(name: str) -> str:
    return os.path.join(FIXTURES_DIR, name)


# ---------------------------------------------------------------------------
# Individual loaders (cached so CSVs are read only once per process)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def load_lots() -> pd.DataFrame:
    """Return wafer_lots DataFrame with correct dtypes."""
    df = pd.read_csv(_fixture("wafer_lots.csv"), parse_dates=["timestamp"])
    df["yield_pct"] = df["yield_pct"].astype(float)
    df["low_yield_flag"] = df["low_yield_flag"].astype(int)
    df["wafer_count"] = df["wafer_count"].astype(int)
    return df


@lru_cache(maxsize=1)
def load_sensors() -> pd.DataFrame:
    """Return equipment_sensor_readings DataFrame with correct dtypes."""
    df = pd.read_csv(_fixture("equipment_sensor_readings.csv"), parse_dates=["timestamp"])
    df["parameter_value"] = df["parameter_value"].astype(float)
    df["alert_flag"] = df["alert_flag"].astype(int)
    return df


@lru_cache(maxsize=1)
def load_defects() -> pd.DataFrame:
    """Return defect_reports DataFrame with correct dtypes."""
    df = pd.read_csv(_fixture("defect_reports.csv"), parse_dates=["timestamp"])
    df["defect_density"] = df["defect_density"].astype(float)
    df["x_coord_mm"] = df["x_coord_mm"].astype(float)
    df["y_coord_mm"] = df["y_coord_mm"].astype(float)
    return df


# ---------------------------------------------------------------------------
# Pivot sensor readings into a wide feature matrix (one row per lot)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def load_sensor_features() -> pd.DataFrame:
    """
    Pivot sensor readings into a wide DataFrame indexed by lot_id.

    For each (lot_id, parameter_name) we take the mean of the two samples.
    Returns a DataFrame with one row per lot and one column per sensor parameter.
    Column names are prefixed with 'sensor_' to avoid collisions.
    """
    sensors = load_sensors()
    pivot = (
        sensors
        .groupby(["lot_id", "parameter_name"])["parameter_value"]
        .mean()
        .unstack("parameter_name")
    )
    pivot.columns = [f"sensor_{c}" for c in pivot.columns]
    pivot = pivot.reset_index()
    return pivot


@lru_cache(maxsize=1)
def load_defect_features() -> pd.DataFrame:
    """
    Aggregate defect data into a per-lot feature DataFrame.

    Columns produced:
      defect_count          – total defect records for the lot
      defect_density_mean   – mean defect_density across all defects
      defect_density_max    – maximum defect_density
      particle_density_mean – mean density of 'particle' defects only
      particle_count        – count of particle defects
      alert_readings_count  – number of sensor alert readings for the lot
    """
    defects = load_defects()
    sensors = load_sensors()

    agg = defects.groupby("lot_id").agg(
        defect_count=("defect_id", "count"),
        defect_density_mean=("defect_density", "mean"),
        defect_density_max=("defect_density", "max"),
    ).reset_index()

    particle = (
        defects[defects["defect_type"] == "particle"]
        .groupby("lot_id")
        .agg(
            particle_density_mean=("defect_density", "mean"),
            particle_count=("defect_id", "count"),
        )
        .reset_index()
    )

    alert_counts = (
        sensors[sensors["alert_flag"] == 1]
        .groupby("lot_id")
        .size()
        .reset_index(name="alert_readings_count")
    )

    df = (
        agg
        .merge(particle, on="lot_id", how="left")
        .merge(alert_counts, on="lot_id", how="left")
        .fillna(0)
    )
    df["particle_count"] = df["particle_count"].astype(int)
    df["alert_readings_count"] = df["alert_readings_count"].astype(int)
    return df


@lru_cache(maxsize=1)
def load_full_feature_matrix() -> pd.DataFrame:
    """
    Join lots + sensor features + defect features into a single flat DataFrame
    ready for the ML model.

    Returns one row per lot (500 rows) with all engineered features.
    """
    lots = load_lots()
    sensor_feats = load_sensor_features()
    defect_feats = load_defect_features()

    df = (
        lots
        .merge(sensor_feats, on="lot_id", how="left")
        .merge(defect_feats, on="lot_id", how="left")
        .fillna(0)
    )
    return df


# ---------------------------------------------------------------------------
# Per-lot helpers used by the pattern detector
# ---------------------------------------------------------------------------

def get_lot(lot_id: str) -> pd.Series:
    """Return the wafer_lots row for *lot_id*. Raises KeyError if not found."""
    lots = load_lots()
    rows = lots[lots["lot_id"] == lot_id]
    if rows.empty:
        raise KeyError(f"lot_id '{lot_id}' not found")
    return rows.iloc[0]


def get_lot_sensors(lot_id: str) -> pd.DataFrame:
    """Return sensor readings for a specific lot."""
    return load_sensors()[load_sensors()["lot_id"] == lot_id].copy()


def get_lot_defects(lot_id: str) -> pd.DataFrame:
    """Return defect records for a specific lot."""
    return load_defects()[load_defects()["lot_id"] == lot_id].copy()
