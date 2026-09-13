"""
lots.py — /api/lots routes
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import math

from fastapi import APIRouter, HTTPException, Query

from ..services.data_loader import load_lots, get_lot, get_lot_sensors, get_lot_defects

router = APIRouter(prefix="/api/lots", tags=["lots"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _lot_row_to_dict(row) -> Dict[str, Any]:
    """Convert a wafer_lots DataFrame row to a JSON-serialisable dict."""
    return {
        "lot_id":        row["lot_id"],
        "node":          row["node"],
        "process_step":  row["process_step"],
        "tool_id":       row["tool_id"],
        "recipe_id":     row["recipe_id"],
        "operator":      row["operator"],
        "wafer_count":   int(row["wafer_count"]),
        "yield_pct":     float(row["yield_pct"]),
        "low_yield_flag":bool(row["low_yield_flag"]),
        "timestamp":     str(row["timestamp"]),
    }


# ---------------------------------------------------------------------------
# GET /api/lots
# ---------------------------------------------------------------------------

@router.get("")
def list_lots(
    limit:          int             = Query(100, ge=1,  le=500),
    offset:         int             = Query(0,   ge=0),
    process_step:   Optional[str]   = Query(None),
    tool_id:        Optional[str]   = Query(None),
    low_yield_only: bool            = Query(False),
    sort_by:        str             = Query("timestamp"),
    sort_dir:       str             = Query("desc"),
) -> Dict[str, Any]:
    """
    Return a paginated list of wafer lots with yield summary.

    Query params:
      limit          Max rows to return (default 100, max 500).
      offset         Pagination offset.
      process_step   Filter by process step (e.g. 'etch').
      tool_id        Filter by tool (e.g. 'ETCH-03').
      low_yield_only If true, return only lots with low_yield_flag=1.
      sort_by        Column to sort on (timestamp, yield_pct, lot_id).
      sort_dir       'asc' or 'desc'.
    """
    df = load_lots().copy()

    # Filters
    if process_step:
        df = df[df["process_step"] == process_step]
    if tool_id:
        df = df[df["tool_id"] == tool_id]
    if low_yield_only:
        df = df[df["low_yield_flag"] == 1]

    # Sort
    valid_sort_cols = {"timestamp", "yield_pct", "lot_id", "tool_id", "process_step"}
    if sort_by not in valid_sort_cols:
        sort_by = "timestamp"
    ascending = sort_dir.lower() != "desc"
    df = df.sort_values(sort_by, ascending=ascending)

    total = len(df)
    page  = df.iloc[offset : offset + limit]

    return {
        "total":  total,
        "offset": offset,
        "limit":  limit,
        "items":  [_lot_row_to_dict(row) for _, row in page.iterrows()],
        "summary": {
            "mean_yield_pct":   round(float(load_lots()["yield_pct"].mean()), 2),
            "low_yield_count":  int(load_lots()["low_yield_flag"].sum()),
            "total_lots":       len(load_lots()),
        },
    }


# ---------------------------------------------------------------------------
# GET /api/lots/{lot_id}
# ---------------------------------------------------------------------------

@router.get("/{lot_id}")
def get_lot_detail(lot_id: str) -> Dict[str, Any]:
    """
    Return full detail for one lot including sensor readings and defect summary.
    """
    try:
        lot = get_lot(lot_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Lot '{lot_id}' not found")

    sensors_df = get_lot_sensors(lot_id)
    defects_df = get_lot_defects(lot_id)

    # Sensor summary: mean value per parameter
    sensor_summary = (
        sensors_df
        .groupby("parameter_name")["parameter_value"]
        .agg(mean="mean", min="min", max="max", alert_count=lambda s: (
            sensors_df.loc[s.index, "alert_flag"].sum()
        ))
        .round(4)
        .reset_index()
        .to_dict("records")
    )

    # Defect summary: count + mean density per type
    if defects_df.empty:
        defect_summary: list[dict] = []
    else:
        defect_summary = (
            defects_df
            .groupby("defect_type")
            .agg(
                count=("defect_id", "count"),
                mean_density=("defect_density", "mean"),
                max_density=("defect_density", "max"),
            )
            .round(4)
            .reset_index()
            .to_dict("records")
        )

    return {
        "lot":            _lot_row_to_dict(lot),
        "sensor_summary": sensor_summary,
        "defect_summary": defect_summary,
        "sensor_count":   len(sensors_df),
        "defect_count":   len(defects_df),
    }
