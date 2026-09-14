# Solution Overview

## What We Built

We built an AI-assisted wafer yield analysis platform that helps semiconductor engineers identify yield loss, detect process abnormalities, predict low-yield risk, and understand likely root causes. The dashboard brings lot yield, sensor data, defect patterns, risk prediction, and engineering recommendations into one place.

## How It Works


1. Manufacturing data containing wafer lots, process parameters, sensor readings, and defects is loaded into the system.

2. The FastAPI backend analyzes the data to detect anomalies, process drift, and defect patterns.

3. Root-cause analysis ranks the most likely factors contributing to yield loss.

4. A RandomForest model predicts low-yield risk for upcoming process conditions.

5. Relevant analysis results are provided to IBM watsonx.ai Granite to generate grounded engineering explanations when available.

6. If watsonx.ai is unavailable, the system uses a deterministic fallback to provide evidence-based responses.

7. Results are displayed through the React dashboard, including the Ask Bob engineering interface.


## Architecture Diagram

> See [`architecture.md`](architecture.md) for the detailed diagram.


## Key Design Decisions

| Decision | Rationale |
|---|---|
|Used FastAPI for the backend | Provides lightweight REST APIs and clear separation between frontend and analysis services |
| Used RandomForest for risk prediction |Provides a practical and interpretable approach for predicting low-yield conditions|
| Used statistical pattern detection | Helps identify process drift, sensor anomalies, and defect-related yield loss|
| Used watsonx.ai Granite for explanations| Converts structured manufacturing evidence into understandable engineering insights|
| Added a deterministic fallback| Keeps the application functional when live watsonx.ai inference is unavailable|


## IBM Technologies Used



- **[IBM watsonx.ai]:** Used with the Granite model to generate grounded engineering explanations from manufacturing analysis and relevant lot context.
- **[IBM Bob]:** Used as the engineering/development workflow environment for building and validating the application.
