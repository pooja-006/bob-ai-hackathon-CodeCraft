# Wafer Yield Root Cause & Defect Pattern Analyser

> An AI-assisted semiconductor manufacturing analytics platform for detecting yield-loss patterns, identifying likely root causes, predicting lot risk, and recommending corrective actions.

---

## 👥 Team

| **Field**     | **Value**                 |
| ------------- | ------------------------- |
| **Team Name** | CodeCraft                 |
| **Track**     | AI                        |
| **Team Lead** | Twisha Patel             |
| **Members**   | Pooja Patel, Pranjal Patel, Datri Vasani |

---

## 🎯 Problem Statement

At 3nm/5nm chip nodes, a 1% yield drop costs tens of millions per month. Root causes
hide across thousands of equipment sensors, process parameters, and defect images.
Engineers spend weeks finding the cause manually — every day of delay is lost
revenue. Process engineers also need to predict which upcoming batches are at risk
before they run, not after they fail.

---

## 💡 Solution

**Wafer Yield Root Cause & Defect Pattern Analyser** is an AI-assisted analytics application that combines semiconductor lot, equipment-sensor, and defect data to identify patterns associated with yield loss.

The system uses statistical pattern detection and a Random Forest risk model to analyse manufacturing conditions. An engineer-facing interface provides fleet-level insights, lot-specific root-cause analysis, risk predictions, corrective actions, and a conversational **Ask Bob** interface that can use IBM watsonx.ai Granite when configured, with a deterministic local fallback when the external AI service is unavailable.

---

## ✨ Key Features

* **Root-Cause Analysis:** Detects important process and defect patterns associated with low-yield lots, including thermal drift, RF spikes, particle contamination, and pressure drift.

* **Yield Risk Prediction:** Uses a Random Forest model to estimate the risk of yield degradation for manufacturing conditions.

* **Defect Pattern Detection:** Analyses defect density and process measurements to identify statistically significant relationships with yield loss.

* **Lot-Level Investigation:** Engineers can select individual wafer lots and inspect their yield, process conditions, defects, and detected anomalies.

* **Fleet-Level Analysis:** Provides an overview of manufacturing performance and identifies broader process trends across the available lot population.

* **Corrective-Action Recommendations:** Converts detected process patterns into practical engineering actions such as inspecting affected equipment or investigating abnormal process parameters.

* **Ask Bob:** Provides a conversational interface for yield-engineering questions using available lot and process context.

* **IBM watsonx.ai Integration:** When valid watsonx.ai credentials and the supported SDK are available, the system can use IBM Granite for AI-generated engineering responses.

* **Grounded Fallback Mode:** If watsonx.ai is unavailable, the application falls back to locally computed, data-grounded analysis rather than failing completely.

* **Evidence-Based Insights:** Analysis responses are grounded in the project's lot, sensor, defect, and detected-pattern data to reduce unsupported conclusions.

---

## 🛠️ Tech Stack

| **Category**           | **Technologies**                                                     |
| ---------------------- | -------------------------------------------------------------------- |
| **Languages**          | Python, JavaScript, React js|
| **Frameworks**         | FastAPI, pandas, NumPy, scikit-learn |
| **AI / ML**            | Random Forest, statistical pattern detection, IBM watsonx.ai Granite |
| **IBM Technologies**   | IBM watsonx.ai, IBM Granite |
| **Database / Storage** | CSV-based analytical datasets, Joblib model cache                    |
| **Frontend**           | Vanilla HTML, CSS, JavaScript                                        |
| **Backend**            | FastAPI REST API    |
| **Other**              | Git, dotenv, Joblib  |

---

## 📁 Repository Structure

```text
BOB-AI-HACKATHON-CODECRAFT/
│
├── .github/
│   ├── ISSUE_TEMPLATE/
│   └── workflows/
│
├── demo/
│   ├── screenshots/
│   │   └── README.md
│   ├── demo-video-link.txt
│   └── live-demo-url.txt
│
├── docs/
│   ├── architecture.md
│   ├── problem-statement.md
│   ├── setup-guide.md
│   ├── solution-overview.md
│   └── template-guide.md
│
├── presentation/
│   └── README.md
│
├── src/
│   │
│   ├── backend/
│   │   ├── __pycache__/
│   │   ├── model_cache/
│   │   ├── routers/
│   │   ├── services/
│   │   ├── tests/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   └── requirements.txt
│   │
│   ├── data/
│   │   ├── fixtures/
│   │   ├── generate_data.py
│   │   └── schema.md
│   │
│   └── frontend/
│       ├── node_modules/
│       ├── public/
│       │   ├── favicon.svg
│       │   └── icons.svg
│       │
│       ├── src/
│       │   ├── assets/
│       │   │   ├── hero.png
│       │   │   ├── react.svg
│       │   │   └── vite.svg
│       │   ├── tabs/
│       │   │   ├── AskBob.jsx
│       │   │   ├── LotOverview.jsx
│       │   │   ├── RiskPredict.jsx
│       │   │   └── RootCause.jsx
│       │   ├── api.js
│       │   ├── App.css
│       │   ├── App.jsx
│       │   ├── index.css
│       │   └── main.jsx
│       │
│       ├── .gitignore
│       ├── .oxlintrc.json
│       ├── index.html
│       ├── package-lock.json
│       ├── package.json
│       ├── README.md
│       └── vite.config.js
│
├── .env.example
├── .gitignore
├── CONTRIBUTING.md
├── README.md
├── submission.yaml
└── wafer-yield-analyser-plan.md  
```

---

## ⚡ How to Run

### 1. Clone the repository

```bash
git clone https://github.com/[your-repository].git
cd [your-repository]
```

### 2. Create a Python environment

Python 3.11+ is recommended when using the current IBM watsonx.ai SDK.

```bash
py -3.11 -m venv .venv
```

Activate it on Windows:

```bash
.venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r src/backend/requirements.txt
```

If you want to enable the live IBM watsonx.ai path and the SDK is compatible with your Python environment:

```bash
pip install ibm-watsonx-ai
```

### 4. Configure environment variables

Copy the example environment file:

```bash
copy .env.example .env
```

Configure the watsonx.ai variables if live Granite responses are available:

```env
WATSONX_API_KEY=your_api_key
WATSONX_PROJECT_ID=your_project_id
WATSONX_URL=https://us-south.ml.cloud.ibm.com
WATSONX_MODEL_ID=ibm/granite-3-3-8b-instruct
```

> watsonx.ai credentials are optional. Without valid credentials, the application uses its local grounded fallback mode.

### 5. Start the backend

From the project root:

```bash
uvicorn src.backend.main:app --reload
```

The API will be available at:

```text
http://127.0.0.1:8000
```

### 6. Open the frontend

Open:

```text
src/frontend/index.html
```

or serve the frontend using a local development server.

> The backend must be running before using API-dependent dashboard features such as lot analysis, risk prediction, and Ask Bob.

---

## 🖥️ Demo

| **Artifact**    | **Link**                   |
| --------------- | -------------------------- |
| 📹 Demo Video   | `demo/demo-video-link.txt` |
| 🌐 Live Demo    | `demo/live-demo-url.txt`   |
| 🖼️ Screenshots | `demo/screenshots/`        |
| 📊 Presentation | `presentation/`            |

---

## 📊 Example Detected Patterns

The project dataset contains controlled manufacturing patterns designed to demonstrate how the analysis pipeline identifies potential yield-loss causes.

### ETCH-03 Thermal Degradation

The system detects elevated etch temperature associated with reduced yield and flags ETCH-03 as a significant process contributor.

### DEP-02 RF Spike

An abnormal RF-power condition on DEP-02 is detected as another potential contributor to yield degradation.

### Particle Contamination

The analysis identifies substantially higher particle density in low-yield lots, providing evidence for contamination-related yield loss.

### ETCH-01 Pressure Drift

The system detects a pressure-drift pattern associated with declining yield over the relevant lots.

---

## 🤖 AI & Analytics Pipeline

```text
                 Manufacturing Data
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
      Lot Data       Sensor Data     Defect Data
          │              │              │
          └──────────────┼──────────────┘
                         ▼
                Data Loading & Analysis
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
     Pattern          Risk Model      Defect
     Detection        Prediction      Analysis
          │              │              │
          └──────────────┼──────────────┘
                         ▼
                 Root-Cause Evidence
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
       Corrective Actions       Ask Bob
                                    │
                         ┌──────────┴──────────┐
                         ▼                     ▼
                    watsonx.ai             Local
                     Granite             Fallback
```

---

## ⚠️ Known Limitations

* **Synthetic Dataset:** The current demonstration uses a controlled synthetic semiconductor manufacturing dataset rather than production fab data.

* **Model Generalization:** Reported ML metrics are based on the project's current dataset and should not be interpreted as evidence of real-world production generalization.

* **watsonx.ai Availability:** Live Granite responses require compatible IBM watsonx.ai credentials and SDK configuration. When unavailable, the application uses its local deterministic fallback.

* **Production Integration:** The current implementation does not directly connect to live semiconductor manufacturing equipment, MES, SCADA, or fab data systems.

* **Authentication:** The demonstration application does not implement production-grade user authentication and authorization.

* **IBM Bob Integration:** The current conversational interface should not be interpreted as proof of a native IBM Bob runtime integration unless the corresponding Bob integration mechanism is explicitly configured and demonstrated.

---

## 🏅 What We're Most Proud Of

We are most proud of turning a complex semiconductor yield-analysis problem into a single engineer-focused workflow.

Instead of presenting isolated charts or ML predictions, the system connects **yield → sensor conditions → defect patterns → root-cause evidence → risk → corrective actions** in one interface.

The strongest part of the project is its combination of **data-grounded analytics and AI-assisted engineering interaction**. The application can continue providing useful analysis even when the external watsonx.ai service is unavailable, while keeping the fallback grounded in the project's actual manufacturing data rather than fabricating evidence.
