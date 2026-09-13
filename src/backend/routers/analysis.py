"""
analysis.py — /api/analysis routes
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..services.data_loader import load_lots, load_sensors, load_defects, get_lot
from ..services.pattern_detector import rank_root_cause_candidates, fleet_summary
from ..services.risk_predictor import predict_batch_risk
from ..services.watsonx_service import (
    analyze_root_cause as wx_analyze_root_cause,
    generate_corrective_actions as wx_corrective_actions,
    answer_engineer_query as wx_answer_query,
    watsonx_status,
)

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class RootCauseRequest(BaseModel):
    lot_id: str = Field(..., description="Lot ID to analyse, e.g. W2401-0083")


class RiskPredictionRequest(BaseModel):
    node:         Optional[str]   = Field(None, description="Technology node: '3nm' or '5nm'")
    process_step: Optional[str]   = Field(None, description="Process step: etch, litho, deposition, …")
    tool_id:      Optional[str]   = Field(None, description="Tool to run the lot on, e.g. ETCH-03")
    recipe_id:    Optional[str]   = Field(None, description="Recipe ID, e.g. R-NIT-07")
    operator:     Optional[str]   = Field(None, description="Operator, e.g. op_alice")
    # Optional sensor overrides
    sensor_etch_temp_c:         Optional[float] = Field(None)
    sensor_etch_pressure_mtorr: Optional[float] = Field(None)
    sensor_rf_power_w:          Optional[float] = Field(None)
    sensor_dep_temp_c:          Optional[float] = Field(None)
    sensor_film_thickness_nm:   Optional[float] = Field(None)
    sensor_furnace_temp_c:      Optional[float] = Field(None)
    # Defect feature overrides
    defect_density_mean:        Optional[float] = Field(None)
    particle_density_mean:      Optional[float] = Field(None)
    defect_count:               Optional[int]   = Field(None)


class CorrectiveActionsRequest(BaseModel):
    lot_id:   Optional[str] = Field(None, description="Lot ID (to fetch root causes automatically)")
    category: Optional[str] = Field(
        None,
        description="Root cause category: sensor_anomaly | defect_contamination | tool_performance"
    )
    parameter: Optional[str] = Field(
        None,
        description="Specific sensor parameter implicated, e.g. etch_temp_c"
    )
    tool_id:  Optional[str] = Field(None, description="Implicated tool, e.g. ETCH-03")


class ChatRequest(BaseModel):
    query:  str           = Field(..., description="Engineer question in natural language")
    lot_id: Optional[str] = Field(None, description="Optional lot ID for context injection")


# ---------------------------------------------------------------------------
# Corrective action knowledge base (stub — replaced by watsonx in Sub-Task 4)
# ---------------------------------------------------------------------------

_CORRECTIVE_ACTIONS: dict[str, list[dict[str, str]]] = {
    # sensor_anomaly actions keyed by parameter name
    "etch_temp_c": [
        {
            "action": "Schedule preventive maintenance on the chamber heating element",
            "rationale": "Elevated etch_temp_c (>185 °C) indicates heater degradation causing thermal drift.",
            "urgency": "HIGH",
            "owner": "Equipment Engineering",
        },
        {
            "action": "Run a thermal uniformity qualification wafer on the affected tool before next production lot",
            "rationale": "Verify temperature profile is within spec across the full wafer diameter.",
            "urgency": "HIGH",
            "owner": "Process Engineering",
        },
        {
            "action": "Tighten the etch_temp_c SPC control limit to ±5 °C and add auto-hold on exceedance",
            "rationale": "Current 165–190 °C window is too wide; tighter limits catch drift earlier.",
            "urgency": "MEDIUM",
            "owner": "Process Control",
        },
        {
            "action": "Review the last 30 lots on ETCH-03 for temporal yield trend",
            "rationale": "Confirm whether the yield drop correlates with the temperature excursion onset.",
            "urgency": "MEDIUM",
            "owner": "Yield Engineering",
        },
    ],
    "etch_pressure_mtorr": [
        {
            "action": "Inspect and replace vacuum seals on the affected etch chamber",
            "rationale": "Upward pressure drift is a classic symptom of a degrading seal or O-ring.",
            "urgency": "HIGH",
            "owner": "Equipment Engineering",
        },
        {
            "action": "Run a chamber leak-up rate test to quantify the seal degradation",
            "rationale": "Quantifies the rate of pressure rise with pump isolated to locate the leak.",
            "urgency": "HIGH",
            "owner": "Equipment Engineering",
        },
        {
            "action": "Add a pressure trend chart to the daily equipment review dashboard",
            "rationale": "Gradual drift is only visible over time; daily trending enables early intervention.",
            "urgency": "LOW",
            "owner": "Process Control",
        },
    ],
    "rf_power_w": [
        {
            "action": "Review the recipe RF power setpoint for R-NIT-07 on DEP-02 and reduce by 20 W",
            "rationale": "RF power spikes on this tool-recipe combination correlate directly with yield loss.",
            "urgency": "HIGH",
            "owner": "Process Engineering",
        },
        {
            "action": "Run a DOE to identify the optimal RF power window for R-NIT-07",
            "rationale": "Determines whether the current nominal setpoint is too close to the upper process limit.",
            "urgency": "MEDIUM",
            "owner": "Process Engineering",
        },
        {
            "action": "Check the RF matching network impedance — excessive spikes can indicate a matching fault",
            "rationale": "A degraded matching network causes reflected power and unstable plasma.",
            "urgency": "MEDIUM",
            "owner": "Equipment Engineering",
        },
    ],
    "film_thickness_nm": [
        {
            "action": "Perform a deposition rate calibration on the affected tool",
            "rationale": "Thickness variation beyond ±3 nm typically signals drift in deposition rate.",
            "urgency": "MEDIUM",
            "owner": "Process Engineering",
        },
        {
            "action": "Verify precursor flow controller (MFC) calibration",
            "rationale": "A miscalibrated MFC is the most common root cause of deposition thickness variation.",
            "urgency": "MEDIUM",
            "owner": "Equipment Engineering",
        },
    ],
    # defect_contamination actions keyed by defect_type
    "particle": [
        {
            "action": "Perform a full chamber clean and particle qualification run on the affected tool",
            "rationale": "Particle counts above 0.18/cm² indicate chamber contamination requiring cleaning.",
            "urgency": "HIGH",
            "owner": "Equipment Engineering",
        },
        {
            "action": "Inspect and replace the electrostatic chuck (ESC) if particle source is the wafer backside",
            "rationale": "Degraded ESC ceramic releases particles onto wafer backside during processing.",
            "urgency": "HIGH",
            "owner": "Equipment Engineering",
        },
        {
            "action": "Audit the wafer-handling robot end-effector for wear or contamination",
            "rationale": "Worn end-effectors are a significant particle source, often overlooked.",
            "urgency": "MEDIUM",
            "owner": "Equipment Engineering",
        },
        {
            "action": "Increase particle monitoring frequency to every 5 lots until counts normalise",
            "rationale": "Tighter monitoring cadence enables faster detection of recurrence.",
            "urgency": "MEDIUM",
            "owner": "Yield Engineering",
        },
    ],
    "void": [
        {
            "action": "Review deposition precursor flow and temperature uniformity profiles",
            "rationale": "Voids in deposited films are typically caused by poor step coverage or low-uniformity deposition.",
            "urgency": "HIGH",
            "owner": "Process Engineering",
        },
        {
            "action": "Check for gaps in the gap-fill process window; run a fill-DoE",
            "rationale": "High-AR gaps may require a different gap-fill recipe to eliminate voiding.",
            "urgency": "MEDIUM",
            "owner": "Process Engineering",
        },
    ],
    "etch_pit": [
        {
            "action": "Reduce etch over-etch time or lower etch temperature to prevent micro-masking damage",
            "rationale": "Etch pits form when localised over-etching attacks the underlying layer.",
            "urgency": "HIGH",
            "owner": "Process Engineering",
        },
        {
            "action": "Inspect etch endpoint detection system for false triggering",
            "rationale": "Premature endpoint miss leads to extended etch time and pit formation.",
            "urgency": "MEDIUM",
            "owner": "Equipment Engineering",
        },
    ],
    # tool_performance fallback
    "tool_performance": [
        {
            "action": "Initiate a full tool qualification (TQ) run with control wafers",
            "rationale": "Sustained below-average yield from a single tool requires systematic qualification.",
            "urgency": "HIGH",
            "owner": "Equipment Engineering",
        },
        {
            "action": "Compare tool PM history against yield trend; escalate if no recent PM was performed",
            "rationale": "Accumulated wear between PMs is the most common cause of gradual tool performance decline.",
            "urgency": "HIGH",
            "owner": "Yield Engineering",
        },
        {
            "action": "Temporarily route lots away from the flagged tool while investigation is ongoing",
            "rationale": "Prevents additional yield loss while root cause is confirmed.",
            "urgency": "MEDIUM",
            "owner": "Fab Operations",
        },
    ],
    # generic fallback
    "_default": [
        {
            "action": "Collect additional data: review SPC charts for the affected parameter over the past 14 days",
            "rationale": "Broader historical context often reveals whether the anomaly is isolated or trending.",
            "urgency": "MEDIUM",
            "owner": "Yield Engineering",
        },
        {
            "action": "Cross-reference the lot against known field alerts or engineering change notices (ECNs)",
            "rationale": "A recent process or hardware change may be the root cause.",
            "urgency": "LOW",
            "owner": "Process Engineering",
        },
        {
            "action": "Schedule a cross-functional review (Yield, Process, Equipment) within 24 hours",
            "rationale": "Complex yield excursions require multi-discipline input for fast resolution.",
            "urgency": "LOW",
            "owner": "Yield Engineering",
        },
    ],
}


def _lookup_corrective_actions(
    category: Optional[str],
    parameter: Optional[str],
    tool_id: Optional[str],
) -> List[Dict[str, str]]:
    """
    Return a list of corrective action dicts for the given root-cause signal.
    Looks up by parameter name first, then by defect type within
    defect_contamination, then by category, then falls back to _default.
    Note: this stub will be replaced by watsonx.ai in Sub-Task 4.
    """
    # Sensor anomaly: key is the parameter name
    if category == "sensor_anomaly" and parameter:
        actions = _CORRECTIVE_ACTIONS.get(parameter)
        if actions:
            return actions

    # Defect contamination: key is the defect type (stored in parameter field)
    if category == "defect_contamination" and parameter:
        # parameter field holds "defect_density"; defect_type is in the evidence —
        # but for the corrective-actions endpoint the caller can pass the defect type
        # directly as parameter (e.g. "particle", "void", "etch_pit")
        actions = _CORRECTIVE_ACTIONS.get(parameter)
        if actions:
            return actions

    # Tool-performance catch-all
    if category == "tool_performance":
        return _CORRECTIVE_ACTIONS["tool_performance"]

    return _CORRECTIVE_ACTIONS["_default"]


# ---------------------------------------------------------------------------
# GET /api/analysis/fleet-summary
# ---------------------------------------------------------------------------

@router.get("/fleet-summary")
def get_fleet_summary() -> Dict[str, Any]:
    """Return a high-level fleet health summary."""
    return fleet_summary(load_lots(), load_sensors(), load_defects())


# ---------------------------------------------------------------------------
# POST /api/analysis/root-cause
# ---------------------------------------------------------------------------

@router.post("/root-cause")
def analyse_root_cause(req: RootCauseRequest) -> Dict[str, Any]:
    """
    Analyse a specific lot and return ranked root-cause candidates plus an
    IBM watsonx.ai Granite narrative (fallback included for offline use).

    Each candidate includes:
      cause          – human-readable label
      category       – sensor_anomaly | defect_contamination | tool_performance
      confidence_pct – estimated confidence 0–100
      summary        – one-sentence evidence narrative
      evidence       – list of supporting data points
      tool_id        – implicated tool
      parameter      – implicated parameter (sensor candidates)
    """
    lots    = load_lots()
    sensors = load_sensors()
    defects = load_defects()

    # Validate lot exists
    if lots[lots["lot_id"] == req.lot_id].empty:
        raise HTTPException(
            status_code=404,
            detail=f"Lot '{req.lot_id}' not found. "
                   f"Use GET /api/lots to browse available lot IDs."
        )

    candidates = rank_root_cause_candidates(req.lot_id, lots, sensors, defects)
    lot_row    = lots[lots["lot_id"] == req.lot_id].iloc[0]

    # Call watsonx.ai to generate a narrative (uses fallback when offline)
    wx_result = wx_analyze_root_cause(req.lot_id, candidates)

    return {
        "lot_id":                req.lot_id,
        "yield_pct":             float(lot_row["yield_pct"]),
        "low_yield_flag":        bool(lot_row["low_yield_flag"]),
        "candidate_count":       len(candidates),
        "candidates":            candidates,
        # watsonx enrichment
        "narrative":             wx_result.get("narrative", ""),
        "recommended_next_step": wx_result.get("recommended_next_step", ""),
        "watsonx_ranked_causes": wx_result.get("ranked_causes", []),
        "source_mode":           wx_result.get("source_mode", "fallback"),
    }


# ---------------------------------------------------------------------------
# POST /api/analysis/risk-prediction
# ---------------------------------------------------------------------------

@router.post("/risk-prediction")
def predict_risk(req: RiskPredictionRequest) -> Dict[str, Any]:
    """
    Predict low-yield risk for an upcoming lot given its planned parameters.

    Returns risk_score (0–1), risk_flag, risk_label (HIGH/MEDIUM/LOW),
    and the top contributing features.
    """
    # Build params dict from request, stripping None values
    params: dict[str, Any] = {}
    for field, val in req.dict().items():
        if val is not None:
            # Rename sensor_ fields back to the feature matrix naming
            params[field] = val

    result = predict_batch_risk(params)
    return result


# ---------------------------------------------------------------------------
# POST /api/analysis/corrective-actions
# ---------------------------------------------------------------------------

@router.post("/corrective-actions")
def get_corrective_actions(req: CorrectiveActionsRequest) -> Dict[str, Any]:
    """
    Return recommended corrective actions backed by IBM watsonx.ai Granite.

    If lot_id is provided the top root-cause candidate is fetched automatically.
    Alternatively pass category + parameter directly.
    Falls back to rule-based actions when watsonx credentials are unavailable.
    """
    root_cause: Dict[str, Any] = {}
    category   = req.category
    parameter  = req.parameter
    tool_id    = req.tool_id

    if req.lot_id:
        lots    = load_lots()
        sensors = load_sensors()
        defects = load_defects()

        if lots[lots["lot_id"] == req.lot_id].empty:
            raise HTTPException(
                status_code=404,
                detail=f"Lot '{req.lot_id}' not found."
            )

        candidates = rank_root_cause_candidates(req.lot_id, lots, sensors, defects)
        if candidates:
            top        = candidates[0]
            root_cause = top
            category   = top["category"]
            parameter  = top.get("parameter")
            tool_id    = top.get("tool_id")
        else:
            category = "_default"

    if not category:
        raise HTTPException(
            status_code=422,
            detail="Provide either lot_id or at least a category."
        )

    if not root_cause:
        root_cause = {"category": category, "parameter": parameter, "tool_id": tool_id}

    actions = wx_corrective_actions(root_cause)

    return {
        "lot_id":    req.lot_id,
        "category":  category,
        "parameter": parameter,
        "tool_id":   tool_id,
        "source":    "watsonx" if not req.lot_id else root_cause.get("source_mode", "fallback"),
        "actions":   actions,
    }


# ---------------------------------------------------------------------------
# POST /api/analysis/chat  (IBM Bob integration endpoint)
# ---------------------------------------------------------------------------

@router.post("/chat")
def chat(req: ChatRequest) -> Dict[str, Any]:
    """
    Answer a free-text engineering question using IBM watsonx.ai Granite.

    If lot_id is supplied, relevant lot + sensor + defect data is injected
    as context so the LLM can give grounded, lot-specific answers.

    Example questions:
      "What caused lot W2401-0083 to drop below spec?"
      "Which tool should I inspect first for lot W2402-0250?"
      "What corrective actions are recommended for elevated etch temperature?"
    """
    context_parts = []

    if req.lot_id:
        lots    = load_lots()
        sensors = load_sensors()
        defects = load_defects()

        lot_rows = lots[lots["lot_id"] == req.lot_id]
        if not lot_rows.empty:
            lot = lot_rows.iloc[0]
            context_parts.append(
                f"Lot: {req.lot_id}  node={lot['node']}  step={lot['process_step']}  "
                f"tool={lot['tool_id']}  recipe={lot['recipe_id']}  "
                f"yield={lot['yield_pct']}%  low_yield={bool(lot['low_yield_flag'])}"
            )
            # Add sensor summary
            lot_sensors = sensors[sensors["lot_id"] == req.lot_id]
            if not lot_sensors.empty:
                sensor_means = (
                    lot_sensors.groupby("parameter_name")["parameter_value"]
                    .mean().round(4)
                )
                context_parts.append("Sensor readings (mean): " + ", ".join(
                    f"{k}={v}" for k, v in sensor_means.items()
                ))
            # Add defect summary
            lot_defects = defects[defects["lot_id"] == req.lot_id]
            if not lot_defects.empty:
                defect_counts = lot_defects["defect_type"].value_counts().to_dict()
                mean_density  = round(float(lot_defects["defect_density"].mean()), 4)
                context_parts.append(
                    f"Defects: {defect_counts}  mean_density={mean_density}/cm2"
                )
            # Add top candidates
            candidates = rank_root_cause_candidates(req.lot_id, lots, sensors, defects)
            if candidates:
                context_parts.append("Top root-cause candidates: " + "; ".join(
                    f"{c['cause']} ({c['confidence_pct']}% confidence)"
                    for c in candidates[:3]
                ))

    context = "\n".join(context_parts) if context_parts else "No specific lot context provided."

    result = wx_answer_query(req.query, context)
    return result


# ---------------------------------------------------------------------------
# GET /api/analysis/watsonx-status
# ---------------------------------------------------------------------------

@router.get("/watsonx-status")
def get_watsonx_status() -> Dict[str, Any]:
    """Return the current watsonx.ai integration status."""
    return watsonx_status()
