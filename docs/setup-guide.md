# Setup Guide

> **This file is read by the automated evaluation pipeline. Be precise and complete.**

## Prerequisites

Before you begin, ensure you have the following installed:

- [ ] Python 3.11+
- [ ] Node.js 18+
- [ ] npm
- [ ] Git
- [ ] IBM Cloud account with watsonx.ai access (optional; fallback mode works without it)


## Environment Variables

Copy `.env.example` to `.env` and fill in the values:

```bash
cp .env.example .env
```

| Variable | Description | Required |
|---|---|---|
| `WATSONX_API_KEY` | IBM watsonx.ai API key | Yes |
| `WATSONX_PROJECT_ID` | watsonx.ai project ID | Yes |
| `WATSONX_URL` | watsonx.ai service URL | No |
| `SLACK_WEBHOOK_URL` | Granite model ID | No |

## Installation

```bash
# 1. Clone the repository
git clone https://github.com/pooja-006/bob-ai-hackathon-CodeCraft.git
cd bob-ai-hackathon-CodeCraft

# 2. Install backend dependencies
cd src/backend
pip install -r requirements.txt

# 3. Install frontend dependencies (if applicable)
cd ../frontend
npm install


```

## Running the Application

```bash
# Start the backend
cd src/backend
python -m uvicorn main:app --reload --port 8000

# Start the frontend (in a separate terminal, if applicable)
cd src/frontend
npm run dev
```

The application will be available at: `http://localhost:5173`

## Running Tests

```bash
[ pytest q]
```

## Quick Demo (Optional)

If you have a demo script or sample data to showcase the project quickly:

```bash
[e.g.: python demo/seed_demo_data.py]
[e.g.: open http://localhost:8000/demo]
```

## Troubleshooting

| Issue | Solution |
|---|---|
| ModuleNotFoundError | Run pip install -r requirements.txt again and ensure you are using Python 3.11+. |
| npm install fails | Delete node_modules and package-lock.json, then run npm install again. |
| watsonx.ai 401 error | Check WATSONX_API_KEY, WATSONX_PROJECT_ID, and WATSONX_URL in your .env file. |
