"""
Synthetic Wafer Yield Data Generator
=====================================
Generates three realistic fixture CSV files for the Wafer Yield Root Cause &
Defect Pattern Analyser:

  fixtures/wafer_lots.csv                ~500 rows
  fixtures/equipment_sensor_readings.csv ~5000 rows
  fixtures/defect_reports.csv            ~3000 rows

All randomness is seeded at 42 so outputs are fully deterministic.

Injected low-yield patterns (detectable by the ML / LLM stage):
  P1 - TOOL DEGRADATION  : tool_id "ETCH-03" after lot 200 runs ~12 C hotter
       (etch_temp > 185 C) -> yield drops 15-25 pp below baseline.
  P2 - RECIPE INTERACTION: recipe "R-NIT-07" on "DEP-02" causes RF power spikes
       (rf_power > 420 W) -> yield drops 10-20 pp.
  P3 - PARTICLE CONTAMINATION: lots with defect_density > 0.18 /cm2 of type
       "particle" -> yield drops proportionally (-40 pp at density 0.40).
  P4 - PROCESS DRIFT    : etch_pressure slowly drifts upward on "ETCH-01" after
       lot 350 -> mild yield degradation (~5-10 pp).

Usage:
    python src/data/generate_data.py
"""

from __future__ import annotations

import os
import math
import random
import csv
from datetime import datetime, timedelta

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SEED = 42
N_LOTS = 500
N_SENSORS_PER_LOT = 10          # ~5 000 total sensor readings
N_DEFECTS_TARGET = 3000
WAFERS_PER_LOT = 25
BASELINE_YIELD = 92.0           # % — healthy baseline
YIELD_SIGMA = 2.5               # natural process noise (pp)
LOW_YIELD_THRESHOLD = 82.0      # below this → flagged as low yield

OUT_DIR = os.path.join(os.path.dirname(__file__), "fixtures")

# ---------------------------------------------------------------------------
# Seed everything
# ---------------------------------------------------------------------------
random.seed(SEED)

# ---------------------------------------------------------------------------
# Reference tables
# ---------------------------------------------------------------------------

NODES = ["3nm", "5nm"]
PROCESS_STEPS = ["litho", "etch", "deposition", "cmp", "diffusion", "implant"]
TOOLS = {
    "litho":       ["LIT-01", "LIT-02", "LIT-03"],
    "etch":        ["ETCH-01", "ETCH-02", "ETCH-03"],
    "deposition":  ["DEP-01", "DEP-02", "DEP-03"],
    "cmp":         ["CMP-01", "CMP-02"],
    "diffusion":   ["DIFF-01", "DIFF-02"],
    "implant":     ["IMP-01", "IMP-02"],
}
RECIPES = {
    "litho":       ["R-LIT-01", "R-LIT-02", "R-LIT-03"],
    "etch":        ["R-ETH-04", "R-ETH-05", "R-ETH-06"],
    "deposition":  ["R-DEP-01", "R-NIT-07", "R-OXI-02"],
    "cmp":         ["R-CMP-01", "R-CMP-02"],
    "diffusion":   ["R-DIF-01", "R-DIF-02"],
    "implant":     ["R-IMP-01", "R-IMP-02"],
}
OPERATORS = ["op_alice", "op_bob", "op_carlos", "op_diana", "op_eve"]
DEFECT_TYPES = ["particle", "scratch", "void", "bridge", "etch_pit", "patterning_defect"]

SENSOR_PARAMS = {
    "etch":        ["etch_temp_c", "etch_pressure_mtorr", "rf_power_w", "gas_flow_sccm", "endpoint_time_s"],
    "deposition":  ["dep_temp_c", "dep_pressure_mtorr", "rf_power_w", "precursor_flow_sccm", "film_thickness_nm"],
    "litho":       ["exposure_energy_mj", "focus_offset_nm", "stage_temp_c", "humidity_pct", "dose_uniformity_pct"],
    "cmp":         ["polish_pressure_psi", "platen_speed_rpm", "slurry_flow_ml_min", "removal_rate_ang_min", "friction_coeff"],
    "diffusion":   ["furnace_temp_c", "ramp_rate_c_min", "ambient_pressure_torr", "gas_ratio", "anneal_time_min"],
    "implant":     ["beam_current_ma", "beam_energy_kev", "scan_speed_mm_s", "dose_uniformity_pct", "tilt_angle_deg"],
}

# Nominal (mean, std) for each sensor parameter
SENSOR_NOMINALS: dict[str, tuple[float, float]] = {
    "etch_temp_c":              (175.0, 3.0),
    "etch_pressure_mtorr":      (8.0,   0.5),
    "rf_power_w":               (380.0, 15.0),
    "gas_flow_sccm":            (50.0,  2.0),
    "endpoint_time_s":          (120.0, 5.0),
    "dep_temp_c":               (300.0, 5.0),
    "dep_pressure_mtorr":       (5.0,   0.3),
    "precursor_flow_sccm":      (30.0,  1.5),
    "film_thickness_nm":        (50.0,  1.0),
    "exposure_energy_mj":       (25.0,  0.5),
    "focus_offset_nm":          (0.0,   2.0),
    "stage_temp_c":             (22.0,  0.2),
    "humidity_pct":             (45.0,  3.0),
    "dose_uniformity_pct":      (98.5,  0.5),
    "polish_pressure_psi":      (3.5,   0.2),
    "platen_speed_rpm":         (90.0,  5.0),
    "slurry_flow_ml_min":       (200.0, 10.0),
    "removal_rate_ang_min":     (1500.0,50.0),
    "friction_coeff":           (0.35,  0.03),
    "furnace_temp_c":           (950.0, 5.0),
    "ramp_rate_c_min":          (10.0,  0.5),
    "ambient_pressure_torr":    (760.0, 2.0),
    "gas_ratio":                (2.0,   0.1),
    "anneal_time_min":          (30.0,  2.0),
    "beam_current_ma":          (10.0,  0.5),
    "beam_energy_kev":          (50.0,  2.0),
    "scan_speed_mm_s":          (100.0, 5.0),
    "tilt_angle_deg":           (7.0,   0.2),
}

# Alert thresholds (parameter -> (low_limit, high_limit))
ALERT_LIMITS: dict[str, tuple[float, float]] = {
    "etch_temp_c":          (165.0, 190.0),
    "etch_pressure_mtorr":  (6.5,   9.5),
    "rf_power_w":           (340.0, 430.0),
    "dep_temp_c":           (285.0, 315.0),
    "rf_power_w":           (340.0, 430.0),
    "furnace_temp_c":       (930.0, 970.0),
    "film_thickness_nm":    (47.0,  53.0),
    "dose_uniformity_pct":  (97.0,  100.0),
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def gauss(mu: float, sigma: float) -> float:
    return random.gauss(mu, sigma)

def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))

def fmt_ts(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S")

# ---------------------------------------------------------------------------
# Start time
# ---------------------------------------------------------------------------
START_TS = datetime(2024, 1, 1, 6, 0, 0)
LOT_INTERVAL_HOURS = 4   # new lot every ~4 hours → 500 lots ≈ 83 days

# ---------------------------------------------------------------------------
# Generate wafer lots
# ---------------------------------------------------------------------------

def make_lots() -> list[dict]:
    lots = []
    ts = START_TS
    for i in range(1, N_LOTS + 1):
        lot_id = f"W{ts.strftime('%y%m')}-{i:04d}"
        node = random.choice(NODES)
        step = random.choice(PROCESS_STEPS)
        tool = random.choice(TOOLS[step])
        recipe = random.choice(RECIPES[step])
        operator = random.choice(OPERATORS)

        # ── Base yield ──────────────────────────────────────────────────────
        yield_pct = gauss(BASELINE_YIELD, YIELD_SIGMA)

        # ── P1: ETCH-03 temperature degradation after lot 200 ───────────────
        p1_active = (tool == "ETCH-03" and i > 200)

        # ── P2: DEP-02 + R-NIT-07 RF interaction ────────────────────────────
        p2_active = (tool == "DEP-02" and recipe == "R-NIT-07")

        # ── P4: ETCH-01 pressure drift after lot 350 ────────────────────────
        p4_active = (tool == "ETCH-01" and i > 350)

        if p1_active:
            yield_pct -= gauss(20.0, 3.0)
        if p2_active:
            yield_pct -= gauss(15.0, 3.0)
        if p4_active:
            yield_pct -= gauss(7.0, 2.0)

        yield_pct = round(clamp(yield_pct, 30.0, 99.9), 2)
        low_yield_flag = yield_pct < LOW_YIELD_THRESHOLD

        lots.append({
            "lot_id":           lot_id,
            "node":             node,
            "process_step":     step,
            "tool_id":          tool,
            "recipe_id":        recipe,
            "operator":         operator,
            "wafer_count":      WAFERS_PER_LOT,
            "yield_pct":        yield_pct,
            "low_yield_flag":   int(low_yield_flag),
            "timestamp":        fmt_ts(ts),
            # store pattern flags for use by sensor/defect generators
            "_p1": p1_active,
            "_p2": p2_active,
            "_p4": p4_active,
            "_i":  i,
        })

        ts += timedelta(hours=LOT_INTERVAL_HOURS + random.uniform(-0.5, 0.5))

    return lots

# ---------------------------------------------------------------------------
# Generate equipment sensor readings
# ---------------------------------------------------------------------------

# Number of timed samples per parameter per lot (gives ~5000 total: 500 lots * 5 params * 2 samples)
SAMPLES_PER_PARAM = 2


def make_sensors(lots: list[dict]) -> list[dict]:
    rows = []
    reading_id = 1
    for lot in lots:
        tool_id = lot["tool_id"]
        step = lot["process_step"]
        params = SENSOR_PARAMS.get(step, list(SENSOR_PARAMS["etch"]))
        lot_ts = datetime.fromisoformat(lot["timestamp"])

        for j, param in enumerate(params):
            mu, sigma = SENSOR_NOMINALS.get(param, (100.0, 5.0))

            for sample in range(SAMPLES_PER_PARAM):
                value = gauss(mu, sigma)

                # ── P1: ETCH-03 runs too hot ─────────────────────────────────
                if lot["_p1"] and param == "etch_temp_c":
                    value = gauss(188.0, 2.5)   # 12 C above nominal

                # ── P2: DEP-02 + R-NIT-07 RF spike ──────────────────────────
                if lot["_p2"] and param == "rf_power_w":
                    value = gauss(425.0, 8.0)   # 45 W above nominal

                # ── P4: ETCH-01 pressure drift ────────────────────────────────
                if lot["_p4"] and param == "etch_pressure_mtorr":
                    drift = (lot["_i"] - 350) * 0.012   # ~1.8 mTorr by lot 500
                    value = gauss(mu + drift, sigma)

                value = round(value, 4)
                lo, hi = ALERT_LIMITS.get(param, (-1e9, 1e9))
                alert_flag = int(value < lo or value > hi)

                # Each sample is spaced ~8 min apart within the lot run
                reading_ts = lot_ts + timedelta(
                    minutes=j * 16 + sample * 8 + random.randint(0, 3)
                )

                rows.append({
                    "reading_id":     f"SR-{reading_id:07d}",
                    "lot_id":         lot["lot_id"],
                    "tool_id":        tool_id,
                    "process_step":   step,
                    "parameter_name": param,
                    "parameter_value":value,
                    "alert_flag":     alert_flag,
                    "timestamp":      fmt_ts(reading_ts),
                })
                reading_id += 1

    return rows

# ---------------------------------------------------------------------------
# Generate defect reports
# ---------------------------------------------------------------------------

def make_defects(lots: list[dict]) -> list[dict]:
    rows = []
    defect_id = 1
    # Distribute N_DEFECTS_TARGET roughly proportionally; more on low-yield lots
    for lot in lots:
        low = lot["low_yield_flag"]
        p1_or_p2 = lot["_p1"] or lot["_p2"]

        # Base defects per lot; normal lots 4-8, low-yield lots get more
        # Tuned so total approaches ~3000 across 500 lots
        if p1_or_p2:
            n_defects = random.randint(12, 22)
        elif low:
            n_defects = random.randint(8, 14)
        else:
            n_defects = random.randint(4, 8)

        lot_ts = datetime.fromisoformat(lot["timestamp"])

        for _ in range(n_defects):
            wafer_id = f"{lot['lot_id']}-W{random.randint(1, WAFERS_PER_LOT):02d}"

            # ── P3: particle contamination on low-yield lots ─────────────────
            if p1_or_p2:
                defect_type = random.choices(
                    DEFECT_TYPES,
                    weights=[50, 10, 15, 10, 10, 5],
                    k=1,
                )[0]
                density = round(random.uniform(0.18, 0.45), 4)
            elif low:
                defect_type = random.choices(
                    DEFECT_TYPES,
                    weights=[30, 15, 20, 15, 10, 10],
                    k=1,
                )[0]
                density = round(random.uniform(0.10, 0.22), 4)
            else:
                defect_type = random.choices(
                    DEFECT_TYPES,
                    weights=[15, 20, 20, 15, 20, 10],
                    k=1,
                )[0]
                density = round(random.uniform(0.01, 0.09), 4)

            x = round(random.uniform(-149.0, 149.0), 2)
            y = round(random.uniform(-149.0, 149.0), 2)
            defect_ts = lot_ts + timedelta(minutes=random.randint(30, 240))

            rows.append({
                "defect_id":      f"D-{defect_id:07d}",
                "lot_id":         lot["lot_id"],
                "wafer_id":       wafer_id,
                "tool_id":        lot["tool_id"],
                "process_step":   lot["process_step"],
                "defect_type":    defect_type,
                "defect_density": density,
                "x_coord_mm":     x,
                "y_coord_mm":     y,
                "timestamp":      fmt_ts(defect_ts),
            })
            defect_id += 1

    return rows

# ---------------------------------------------------------------------------
# Write CSV helpers
# ---------------------------------------------------------------------------

def write_csv(path: str, rows: list[dict], exclude_keys: list[str] | None = None) -> int:
    if not rows:
        return 0
    exclude = set(exclude_keys or [])
    fieldnames = [k for k in rows[0].keys() if k not in exclude]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row[k] for k in fieldnames})
    return len(rows)

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("Generating synthetic wafer data (seed=42) …")

    lots = make_lots()
    sensors = make_sensors(lots)
    defects = make_defects(lots)

    # Summary stats
    low_yield_count = sum(1 for l in lots if l["low_yield_flag"])
    alert_count = sum(1 for s in sensors if s["alert_flag"])

    # Write fixtures (strip internal _* keys from lots)
    internal_keys = ["_p1", "_p2", "_p4", "_i"]
    n_lots    = write_csv(os.path.join(OUT_DIR, "wafer_lots.csv"),                  lots,    internal_keys)
    n_sensors = write_csv(os.path.join(OUT_DIR, "equipment_sensor_readings.csv"),   sensors)
    n_defects = write_csv(os.path.join(OUT_DIR, "defect_reports.csv"),              defects)

    print(f"\nOK Fixture files written to {OUT_DIR}/")
    print(f"   wafer_lots.csv                : {n_lots:>5} rows  ({low_yield_count} low-yield lots)")
    print(f"   equipment_sensor_readings.csv : {n_sensors:>5} rows  ({alert_count} alert readings)")
    print(f"   defect_reports.csv            : {n_defects:>5} rows")
    print("\nInjected patterns:")
    print("  P1 - ETCH-03 etch_temp_c spike    (lots 201-500, tool=ETCH-03)")
    print("  P2 - DEP-02 + R-NIT-07 RF spike   (tool=DEP-02, recipe=R-NIT-07)")
    print("  P3 - High particle density on low-yield lots")
    print("  P4 - ETCH-01 etch_pressure drift   (lots 351-500, tool=ETCH-01)")


if __name__ == "__main__":
    main()
