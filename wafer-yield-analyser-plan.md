# Wafer Yield Root Cause & Defect Pattern Analyser — Implementation Plan

## Top-Level Overview

**Goal:** Build a working, demo-able AI tool that helps semiconductor engineers at advanced 3nm/5nm nodes
quickly identify yield-loss root causes, rank them by probability, recommend corrective actions, and flag
upcoming lots at risk — all powered by IBM watsonx.ai and IBM Bob integration.

**Scope:** A Python/FastAPI backend with a minimal React (or plain HTML+JS) frontend, synthetic but realistic
wafer data, watsonx.ai Granite LLM for natural-language root cause analysis, and a simple ML model (scikit-learn)
for batch risk prediction. All source code lives under `src/`. Documentation, submission metadata, and demo
artefacts are filled in alongside the code.

**Out of scope:**
- Real fab data ingestion pipelines or ERP integrations
- Production deployment, Kubernetes, or cloud infrastructure
- Advanced deep-learning models (CNNs on wafer maps)
- Authentication / multi-tenant security hardening

**Approach:**
```
Synthetic Data → Ingestion API → Pattern Detection Engine → watsonx.ai LLM Analysis
                                                              ↓
                               Risk Prediction (scikit-learn) → Dashboard UI → IBM Bob Chat
```

**IBM Technology used (load-bearing):**
- **watsonx.ai** — Granite model called for root cause narrative, evidence ranking, and corrective action generation
- **IBM Bob** — chat interface exposes queries ("What caused lot W2403-17 to drop below spec?")

---

## Sub-Tasks

---

### Sub-Task 1 — Synthetic Data Generation & Schema

**Intent:** Create realistic synthetic wafer lot data so the entire pipeline has something concrete to operate
on. This avoids any dependency on real fab data while still producing meaningful patterns for the analyser to find.

**Expected Outcomes:**
- `src/data/generate_data.py` script that produces CSV/JSON fixture files
- Three datasets: `wafer_lots.csv`, `equipment_sensor_readings.csv`, `defect_reports.csv`
- Embedded known patterns: lots processed on a specific tool at certain temperature ranges correlate with low yield; certain defect densities correlate with yield drop
- A `src/data/schema.md` document describing all fields

**Todo List:**
1. Define schema for `wafer_lots` (lot_id, node, process_step, tool_id, yield_pct, timestamp, operator, recipe_id)
2. Define schema for `equipment_sensor_readings` (reading_id, tool_id, timestamp, parameter_name, parameter_value, alert_flag)
3. Define schema for `defect_reports` (defect_id, lot_id, wafer_id, defect_type, defect_density, x_coord, y_coord, timestamp)
4. Write `generate_data.py` generating ~500 lots, ~5000 sensor rows, ~3000 defect rows with injected anomalies
5. Run the script and commit the generated CSVs as fixture files under `src/data/fixtures/`
6. Write `src/data/schema.md`

**Relevant Context:**
- All code goes in `src/` per template rules (`src/README.md`, `CONTRIBUTING.md`)
- Fixture files must be small enough to commit (< 5 MB total)
- Injected patterns must be detectable by both the ML model and the LLM

**Status:** `[x] done`

---

### Sub-Task 2 — Backend API (FastAPI)

**Intent:** Build the core Python backend that ingests the fixture data, exposes REST endpoints for the
frontend and IBM Bob chat, and orchestrates the pattern detection + LLM calls.

**Expected Outcomes:**
- `src/backend/main.py` — FastAPI app with all routes
- `/api/lots` — list wafer lots with yield summary
- `/api/lots/{lot_id}` — detail for a single lot
- `/api/analysis/root-cause` — POST endpoint that accepts `lot_id`, returns ranked root causes + evidence
- `/api/analysis/risk-prediction` — POST endpoint that accepts a list of upcoming lot parameters, returns risk score + flag
- `/api/analysis/corrective-actions` — POST endpoint that returns recommended actions for a given root cause
- `src/backend/requirements.txt` with pinned deps (fastapi, uvicorn, pandas, scikit-learn, ibm-watsonx-ai)

**Todo List:**
1. Create `src/backend/` directory with `main.py`, `routers/`, `services/`, `models/`
2. Implement data loading layer (`services/data_loader.py`) that reads fixture CSVs into pandas DataFrames
3. Implement `routers/lots.py` with `/api/lots` and `/api/lots/{lot_id}` endpoints
4. Implement `routers/analysis.py` with the three analysis endpoints (stubs calling service layer)
5. Write `requirements.txt` with all dependencies
6. Add CORS middleware so the frontend can call the API
7. Test that `uvicorn src.backend.main:app --reload` starts cleanly

**Relevant Context:**
- `src/.env.example` already defines `WATSONX_API_KEY`, `WATSONX_PROJECT_ID`, `WATSONX_URL`, `APP_PORT`
- Use `python-dotenv` to load env vars
- Keep endpoints thin; business logic lives in `services/`

**Status:** `[x] done`

---

### Sub-Task 3 — Pattern Detection Engine

**Intent:** Implement the statistical/ML logic that scans lot + sensor + defect data to detect which process
parameters, tools, and defect patterns correlate with yield drops. This produces the structured evidence that
the LLM then turns into natural-language root cause narratives.

**Expected Outcomes:**
- `src/backend/services/pattern_detector.py`
  - `detect_yield_correlations(lot_df, sensor_df)` → dict of `{parameter: correlation_score}`
  - `detect_defect_clusters(defect_df, lot_id)` → defect type counts, density stats
  - `rank_root_cause_candidates(lot_id)` → list of `{cause, evidence, confidence_pct}` dicts
- `src/backend/services/risk_predictor.py`
  - scikit-learn `RandomForestClassifier` (or `IsolationForest`) trained on historical lots
  - `predict_batch_risk(upcoming_params)` → `{risk_score, risk_flag, top_risk_factors}`

**Todo List:**
1. Write `pattern_detector.py` with correlation analysis (Pearson/Spearman) between sensor params and yield
2. Add defect cluster detection: group by defect_type per lot, flag outlier densities (Z-score > 2)
3. Write `rank_root_cause_candidates()` that combines correlation + defect evidence into a ranked list
4. Write `risk_predictor.py`: train a `RandomForestClassifier` on synthetic history on first import (cached to disk with `joblib`)
5. `predict_batch_risk()` takes a dict of process params and returns probability of yield < threshold
6. Add unit tests in `src/backend/tests/test_pattern_detector.py`

**Relevant Context:**
- Uses pandas + scikit-learn already in requirements from Sub-Task 2
- The injected anomalies in Sub-Task 1 must produce non-trivial correlations here
- Keep model training deterministic (fixed `random_state=42`) so tests are reproducible

**Status:** `[x] done`

---

### Sub-Task 4 — watsonx.ai LLM Integration

**Intent:** Call IBM watsonx.ai (Granite model) to transform the structured evidence from the pattern detector
into human-readable root cause narratives, probability-ranked explanations, and concrete corrective action
recommendations. This is the core IBM technology integration.

**Expected Outcomes:**
- `src/backend/services/watsonx_service.py`
  - `analyze_root_cause(lot_id, evidence_list)` → LLM-generated narrative with ranked causes
  - `generate_corrective_actions(root_cause)` → list of recommended actions
  - `answer_engineer_query(query, context)` → free-text Q&A for the Bob chat interface
- Prompts are structured, include the evidence list as context, and request JSON-formatted output
- Graceful fallback if `WATSONX_API_KEY` is not set (returns mock response for demo/testing)

**Todo List:**
1. Install and configure `ibm-watsonx-ai` SDK; write `watsonx_service.py` with client initialisation
2. Write `analyze_root_cause()`: build prompt with lot metadata + evidence list, call Granite, parse response
3. Write `generate_corrective_actions()`: prompt requests 3-5 specific, actionable steps
4. Write `answer_engineer_query()`: RAG-lite — inject relevant lot data as context before the query
5. Add mock/fallback responses that activate when `APP_ENV=development` and no API key is present
6. Wire `watsonx_service` into `routers/analysis.py` endpoints

**Relevant Context:**
- `src/.env.example` already has `WATSONX_API_KEY`, `WATSONX_PROJECT_ID`, `WATSONX_URL`
- Use `ibm_watsonx_ai.foundation_models` → `ModelInference` with `ibm/granite-13b-chat-v2` (or latest available)
- Evaluation rubric awards 10 pts for IBM Bob integration — this service also backs the Bob chat endpoint

**Status:** `[x] done`

---

### Sub-Task 5 — Frontend Dashboard

**Intent:** Build a minimal, visually coherent single-page dashboard that lets a judge/engineer see lot yield
trends, drill into a specific lot to get root cause analysis, view risk predictions for upcoming batches, and
chat with the system via an IBM Bob-style interface.

**Expected Outcomes:**
- `src/frontend/index.html` + `src/frontend/app.js` + `src/frontend/style.css` (vanilla JS, no build step needed)
- **Tab 1 — Lot Overview:** table of recent wafer lots, yield % with colour coding (green/amber/red)
- **Tab 2 — Root Cause Analysis:** select a lot → click Analyse → shows ranked root causes + evidence + corrective actions (all from the API)
- **Tab 3 — Risk Prediction:** form with upcoming lot parameters → click Predict → shows risk score + flag + top risk factors
- **Tab 4 — Ask Bob:** free-text query box → calls `/api/analysis/chat` → shows LLM response
- Frontend served statically by FastAPI (`StaticFiles` mount)

**Todo List:**
1. Create `src/frontend/` with `index.html`, `app.js`, `style.css`
2. Implement Tab 1: fetch `/api/lots`, render table with yield colour coding
3. Implement Tab 2: lot selector, "Analyse" button, render root cause cards with confidence bars
4. Implement Tab 3: parameter input form, "Predict Risk" button, risk badge display
5. Implement Tab 4: chat input + response display styled after IBM Carbon Design (minimal)
6. Mount `src/frontend/` as static files in `main.py`: `app.mount("/", StaticFiles(directory=...))`
7. Verify full flow works end-to-end with the mock watsonx fallback

**Relevant Context:**
- Vanilla JS avoids a Node.js build step, making the setup guide simpler for judges
- IBM Carbon colour palette (#0f62fe blue, #da1e28 red, #198038 green) gives it an IBM feel
- Screenshots for `demo/screenshots/` will be taken from this UI

**Status:** `[x] done`

---

### Sub-Task 6 — IBM Bob Chat Endpoint & Integration

**Intent:** Expose a dedicated `/api/analysis/chat` endpoint that the frontend "Ask Bob" tab calls, backed by
`watsonx_service.answer_engineer_query()`. Document this as the IBM Bob integration point.

**Expected Outcomes:**
- POST `/api/analysis/chat` accepting `{"query": "...", "lot_id": "optional"}` → `{"response": "..."}`
- Context injection: if `lot_id` is provided, relevant lot + sensor + defect data is prepended to the prompt
- Example queries that demo judges can try are documented in `docs/setup-guide.md`

**Todo List:**
1. Add `POST /api/analysis/chat` route to `routers/analysis.py`
2. Implement context builder: fetch lot data if `lot_id` provided, format as structured text for the LLM prompt
3. Call `watsonx_service.answer_engineer_query(query, context)`
4. Test with 3 canned example queries covering root cause, risk, and corrective action questions
5. Document the 3 example queries in `docs/setup-guide.md`

**Relevant Context:**
- This endpoint is what earns the IBM Bob integration score (10 pts on the rubric)
- Reuses `watsonx_service` from Sub-Task 4 — no new LLM setup needed

**Status:** `[ ] pending`

---

### Sub-Task 7 — Documentation & Submission Artefacts

**Intent:** Fill in all required hackathon submission files so the GitHub Action validation passes and judges
have everything they need to evaluate and run the project.

**Expected Outcomes:**
- `submission.yaml` — all required fields filled (team, track=AI, title, problem, solution, tech stack)
- `README.md` — all placeholders replaced with real content
- `docs/problem-statement.md` — semiconductor yield problem, personas, scale of losses
- `docs/solution-overview.md` — what was built, how it works, architecture diagram, IBM tech used
- `docs/architecture.md` — component table, data flow, Mermaid system diagram
- `docs/setup-guide.md` — prerequisites, env vars table, step-by-step run instructions, 3 example Bob queries
- `demo/live-demo-url.txt` — set to `NOT DEPLOYED` or actual URL
- GitHub Action validation passes (green ✅)

**Todo List:**
1. Fill `submission.yaml` with team/submission metadata
2. Rewrite `README.md` replacing all `[placeholder]` sections
3. Write `docs/problem-statement.md` with real semiconductor yield context
4. Write `docs/solution-overview.md` with architecture description and IBM tech explanation
5. Write `docs/architecture.md` with component table and data flow
6. Write `docs/setup-guide.md` with prerequisites, env setup, `uvicorn` run command, and 3 example queries
7. Update `demo/live-demo-url.txt`
8. Update `src/.env.example` with any new env vars added during coding
9. Verify GitHub Action passes locally by checking all file existence and field requirements

**Relevant Context:**
- Validation checks are in `.github/workflows/validate.yml` — must NOT have placeholder strings in README
- Required `submission.yaml` fields: `team.name`, `team.track`, `team.lead.name`, `team.lead.email`,
  `submission.title`, `submission.problem_statement`, `submission.solution_summary`, `submission.key_features`
- Track must be exactly `AI`

**Status:** `[ ] pending`

---

### Sub-Task 8 — End-to-End Smoke Test & Screenshots

**Intent:** Run the full application, verify all features work with the mock fallback and (if API key is
available) with real watsonx.ai, take the required screenshots, and do a final checklist pass.

**Expected Outcomes:**
- Application starts with `uvicorn src.backend.main:app` from the `src/` directory
- All 4 UI tabs function without errors in a browser
- At least 3 screenshots saved to `demo/screenshots/` with correct naming
- All 15 items on the CONTRIBUTING.md pre-submission checklist are green

**Todo List:**
1. Start the app and open the browser; walk through all 4 tabs
2. Verify mock fallback produces sensible output when no watsonx key is set
3. If API key available: test real LLM responses for root cause + corrective actions
4. Take and save screenshots: `01-lot-overview.png`, `02-root-cause-analysis.png`, `03-risk-prediction.png`, `04-ask-bob-chat.png`
5. Run `pytest src/backend/tests/` and confirm all tests pass
6. Walk through CONTRIBUTING.md 15-item checklist; fix anything incomplete

**Relevant Context:**
- Screenshots go in `demo/screenshots/` per naming convention in `demo/screenshots/README.md`
- At least 3 screenshots required; 4 recommended to cover all features
- Final repo state must pass the GitHub Action (`validate.yml`)

**Status:** `[ ] pending`

---

## Architecture Overview

```
src/
├── data/
│   ├── generate_data.py          # Synthetic data generator
│   ├── fixtures/                 # Generated CSV files (committed)
│   │   ├── wafer_lots.csv
│   │   ├── equipment_sensor_readings.csv
│   │   └── defect_reports.csv
│   └── schema.md
├── backend/
│   ├── main.py                   # FastAPI app entry point
│   ├── routers/
│   │   ├── lots.py               # /api/lots endpoints
│   │   └── analysis.py           # /api/analysis/* endpoints + /api/analysis/chat
│   ├── services/
│   │   ├── data_loader.py        # CSV → DataFrame loader
│   │   ├── pattern_detector.py   # Correlation + defect analysis
│   │   ├── risk_predictor.py     # ML yield risk model
│   │   └── watsonx_service.py    # IBM watsonx.ai LLM calls
│   ├── tests/
│   │   └── test_pattern_detector.py
│   └── requirements.txt
├── frontend/
│   ├── index.html                # Single-page app
│   ├── app.js                    # Fetch calls + DOM rendering
│   └── style.css                 # IBM Carbon-inspired styling
└── .env.example                  # Updated with all env vars
```

---

## Key Dependencies

| Package | Purpose |
|---|---|
| `fastapi` + `uvicorn` | Backend web framework |
| `pandas` | Data loading and correlation analysis |
| `scikit-learn` | RandomForestClassifier for risk prediction |
| `joblib` | Model persistence |
| `ibm-watsonx-ai` | watsonx.ai Granite LLM calls |
| `python-dotenv` | Load `.env` file |
| `pytest` | Unit tests |

---

## Scoring Alignment

| Rubric Criterion | Points | How We Address It |
|---|---|---|
| Technical Implementation Quality | 25 | Pattern detector + ML risk model + structured LLM pipeline |
| Innovation & Differentiation | 25 | End-to-end yield root cause → prediction → action loop; Ask Bob NL interface |
| Problem Depth & Vision | 15 | Real semiconductor domain context; 3nm/5nm yield economics |
| Working Demo & Functionality | 15 | Mock fallback ensures demo works without live API key |
| IBM Bob Integration | 10 | `/api/analysis/chat` backed by Granite LLM; Ask Bob UI tab |
| Documentation & Reproducibility | 10 | Full setup guide; one-command start; passing GitHub Action |
