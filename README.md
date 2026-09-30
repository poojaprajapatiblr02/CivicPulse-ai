# 🏛️ CivicPulse AI

### Turning Citizen Voices into Evidence-Backed Development Intelligence

**CivicPulse AI** is a multilingual, AI-powered civic intelligence platform designed to help governments transform citizen development requests into transparent, evidence-backed infrastructure priorities.

The platform combines citizen feedback with demographic, infrastructure, and public investment data to identify demand hotspots, detect infrastructure gaps, rank development priorities, and generate grounded recommendations for policymakers.

Built for the **BRICS Innovation Hackathon — AI for Digital Public Infrastructure & Governance**.

---

## 🌐 Live Application

**CivicPulse AI is deployed on Google Cloud Run.**

> Add your deployed Cloud Run URL here:
>
> `https://civicpulse-frontend-fzxngbj6ea-el.a.run.app/`

---

## 🎯 The Problem

Governments receive large volumes of development requests across regions, languages, departments, and communication channels.

However, these signals are often difficult to connect with:

- existing infrastructure capacity,
- demographic characteristics,
- government investments,
- geographic demand patterns, and
- competing development priorities.

This makes it difficult to determine **where infrastructure intervention is most needed and why**.

CivicPulse AI creates an auditable decision-intelligence layer between citizen demand and infrastructure planning.

---

## 💡 How CivicPulse AI Works

```text
Citizen Development Request
            │
            ▼
┌─────────────────────────────┐
│ Multilingual AI Analysis    │
│                             │
│ • Language                  │
│ • Category                  │
│ • Problem                   │
│ • Location                  │
│ • Urgency                   │
└─────────────┬───────────────┘
              │
              ▼
         BigQuery
              │
      ┌───────┴─────────┐
      │                 │
      ▼                 ▼
Citizen Demand      Public Data
                    • Demographics
                    • Infrastructure
                    • Investments
      │                 │
      └────────┬────────┘
               ▼
      Demand Hotspot Detection
               │
               ▼
     Infrastructure Gap Analysis
               │
               ▼
      Transparent Priority Score
               │
               ▼
     Evidence-Grounded Gemini AI
               │
               ▼
       Policy Recommendation
               │
               ▼
      Policymaker Dashboard
```

---

## ✨ Core Capabilities

### 🗣️ Multilingual Citizen Request Intelligence

Citizen development requests are processed through a **LangGraph-orchestrated multi-agent AI pipeline**.

Currently supported languages:

- English
- Hindi
- Kannada

The pipeline extracts:

- language,
- development category,
- problem description,
- named location,
- urgency, and
- confidence.

The five semantic agents operate independently before their outputs are structurally validated.

```text
START
  ↓
Language Detection
  ↓
Classification
  ↓
Entity Extraction
  ↓
Location Extraction
  ↓
Urgency Analysis
  ↓
Validation
  ↓
END
```

Supported development categories include:

`Healthcare` • `Education` • `Roads` • `Water` • `Electricity` • `Other`

---

### 📍 Demand Hotspot Detection

CivicPulse aggregates validated citizen requests to identify concentrated development demand.

Hotspots are derived using:

- district,
- location,
- development category,
- request volume,
- affected population,
- average urgency, and
- demand growth.

Hotspot detection is deterministic rather than LLM-generated, ensuring that demand signals remain reproducible and explainable.

---

### 🏗️ Infrastructure Gap Analysis

Citizen demand is connected with infrastructure and government investment evidence.

For every eligible hotspot, CivicPulse evaluates factors such as:

- available infrastructure capacity,
- required capacity,
- infrastructure deficit,
- population,
- vulnerability,
- government investment,
- estimated investment need, and
- investment deficit.

Missing or ambiguous evidence is explicitly marked rather than silently converted to zero.

---

### 📊 Transparent Priority Scoring

Infrastructure priorities are calculated using a deterministic weighted scoring model.

| Component | Weight |
|---|---:|
| Citizen Demand | 30% |
| Infrastructure Gap | 20% |
| Population Impact | 15% |
| Vulnerability | 15% |
| Urgency | 10% |
| Investment Gap | 10% |

```text
Priority Score =
    0.30 × Demand
  + 0.20 × Infrastructure Gap
  + 0.15 × Population Impact
  + 0.15 × Vulnerability
  + 0.10 × Urgency
  + 0.10 × Investment Gap
```

Each component is normalized to a `0–100` scale.

The scoring methodology is deliberately separated from generative AI so policymakers can inspect **why an area received its priority score**.

---

## 🤖 Evidence-Grounded Policy Recommendations

CivicPulse uses **Gemini on Vertex AI** to generate policy recommendations for prioritized hotspots.

Unlike unrestricted generation, the recommendation agent receives a controlled evidence snapshot assembled by the backend.

The model cannot provide its own numerical evidence.

Instead:

```text
BigQuery Evidence
       ↓
Validated Evidence Snapshot
       ↓
Gemini Recommendation Agent
       ↓
Numerical Grounding Validation
       ↓
Stored Recommendation
```

Recommendations contain:

- recommended intervention,
- reasoning,
- supporting evidence,
- expected impact,
- confidence,
- limitations, and
- immutable evidence snapshot.

Recommendations are advisory and remain subject to human assessment.

---

## 🖥️ Policymaker Dashboard

The CivicPulse dashboard provides a unified view of development intelligence.

### Overview

Monitor:

- citizen requests,
- active demand hotspots,
- infrastructure gaps, and
- generated recommendations.

### 🗺️ Hotspot Map

Interactive Leaflet maps visualize geographic demand hotspots using backend-derived coordinates.

Map popups provide:

- location,
- development category,
- request count,
- population proxy,
- infrastructure gap, and
- priority score.

### 📈 Priority Areas

Infrastructure gaps are ranked using the transparent priority model, allowing policymakers to compare areas using the underlying evidence.

### 🧠 AI Recommendations

Policymakers can select eligible priority areas and explicitly generate evidence-grounded recommendations.

### 💬 Citizen Request Analyzer

Citizen development requests can be submitted directly through the dashboard and processed by the multilingual LangGraph pipeline.

---

## 🏗️ System Architecture

```text
                    ┌──────────────────────┐
                    │      React + Vite    │
                    │ Policymaker Dashboard│
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │       FastAPI        │
                    │      /api/v1/*       │
                    └──────────┬───────────┘
                               │
               ┌───────────────┼───────────────┐
               │               │               │
               ▼               ▼               ▼
          LangGraph        BigQuery       Analytics Engine
               │               │               │
               ▼               │        ┌──────┴──────┐
          Vertex AI            │        │             │
           Gemini              │     Hotspots     Gap Analysis
               │               │        │             │
               └───────────────┴────────┴──────┬──────┘
                                               │
                                               ▼
                                      Priority Scoring
                                               │
                                               ▼
                                      Recommendations
```

---

## 🧰 Technology Stack

### Frontend

- React 19
- TypeScript
- Vite
- Tailwind CSS
- Leaflet
- React Leaflet

### Backend

- Python 3.12
- FastAPI
- Pydantic
- Uvicorn

### AI

- Google Vertex AI
- Gemini
- LangGraph

### Data

- Google BigQuery
- Explicit-schema datasets
- Parameterized queries
- Controlled query billing

### Cloud

- Google Cloud Platform
- Cloud Run
- Application Default Credentials
- IAM-based service identity

---

## ☁️ Cloud Deployment

CivicPulse AI is containerized and deployed using **Google Cloud Run**.

```text
Internet
   │
   ▼
Google Cloud Run
   │
   ├── CivicPulse Frontend
   │
   └── FastAPI Backend
           │
           ├────────► BigQuery
           │
           └────────► Vertex AI / Gemini
```

Cloud Run uses a dedicated service identity to access Google Cloud services.

No service-account JSON keys or Gemini API keys are embedded in the application.

---

## 📦 Data Model

CivicPulse uses seven primary BigQuery tables:

```text
citizen_requests
demographics
infrastructure
government_investments
hotspots
infrastructure_gaps
recommendations
```

Citizen requests are preserved independently from derived analytical snapshots.

Hotspots and infrastructure priorities can therefore be recalculated without modifying the original requests.

---

## 🔌 Core API

### System

```http
GET /api/v1/health
```

### Citizen Requests

```http
POST /api/v1/requests/analyze
GET  /api/v1/requests
```

### Dashboard

```http
GET /api/v1/dashboard/summary
```

### Hotspots

```http
POST /api/v1/hotspots/detect
GET  /api/v1/hotspots
GET  /api/v1/hotspots/{id}
```

### Infrastructure Intelligence

```http
GET /api/v1/gaps
GET /api/v1/priorities
```

### Recommendations

```http
POST /api/v1/recommendations/generate
GET  /api/v1/recommendations
GET  /api/v1/recommendations/{id}
```

FastAPI also provides interactive API documentation at:

```text
/docs
```

---

## 🚀 Running Locally

### Prerequisites

- Python 3.12
- Node.js 20.19+ or 22.12+
- npm
- Google Cloud CLI
- BigQuery access
- Vertex AI access

### 1. Clone the repository

```bash
git clone <YOUR_REPOSITORY_URL>
cd civicpulse-ai
```

### 2. Configure the environment

Copy:

```bash
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Configure:

```env
VITE_API_BASE_URL=http://127.0.0.1:8000

CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173

GCP_PROJECT_ID=
GCP_REGION=
GEMINI_MODEL=

BIGQUERY_DATASET=civicpulse
BIGQUERY_LOCATION=asia-south1
BIGQUERY_MAX_BYTES_BILLED=100000000

HOTSPOT_REQUEST_THRESHOLD=20
```

Never commit `.env`.

### 3. Start the backend

```powershell
cd backend

py -3.12 -m venv .venv

.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt

.\.venv\Scripts\python.exe -m uvicorn app.main:app `
  --reload `
  --host 127.0.0.1 `
  --port 8000
```

### 4. Start the frontend

Open another terminal:

```powershell
cd frontend

npm.cmd ci
npm.cmd run dev
```

Open:

```text
http://127.0.0.1:5173
```

Backend health:

```text
http://127.0.0.1:8000/api/v1/health
```

API documentation:

```text
http://127.0.0.1:8000/docs
```

---

## 🔐 Security & Responsible AI

CivicPulse is designed around several safeguards:

**No hardcoded credentials**

Google Cloud authentication uses Application Default Credentials and IAM service identities.

**Structured model outputs**

Gemini responses are validated using strict Pydantic schemas.

**Grounded locations**

Coordinates are resolved only against known demographic records rather than being invented by the model.

**Deterministic prioritization**

Generative AI does not calculate infrastructure priority scores.

**Numerically grounded recommendations**

Recommendation evidence originates from backend-controlled data snapshots.

**Safe logging**

Logs avoid citizen request text, credentials, raw model output, and sensitive cloud exception details.

**Human decision authority**

AI recommendations provide decision support and do not authorize spending, procurement, construction, or government action.

---

## 🧪 Testing

### Backend

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest
```

### Frontend

```powershell
cd frontend

npm.cmd test
npm.cmd run lint
npm.cmd run build
```

The project includes unit and integration coverage for:

- multilingual request analysis,
- structured Gemini output,
- BigQuery operations,
- location resolution,
- hotspot detection,
- infrastructure gap analysis,
- priority calculations,
- evidence-grounded recommendations,
- dashboard API integration,
- map behavior,
- error handling, and
- snapshot consistency.

---

## 📂 Repository Structure

```text
civicpulse-ai/
│
├── backend/
│   ├── app/
│   │   ├── agents/
│   │   ├── api/
│   │   ├── core/
│   │   ├── schemas/
│   │   ├── services/
│   │   └── main.py
│   └── tests/
│
├── frontend/
│   └── src/
│
├── data/
│   ├── synthetic/
│   ├── schemas/
│   └── scripts/
│
├── docs/
├── scripts/
│
├── .env.example
└── README.md
```

---

## 🔭 Future Scope

CivicPulse AI is designed to expand into a broader Digital Public Infrastructure ecosystem.

Future capabilities include:

- voice-based citizen request intake,
- WhatsApp and messaging-channel integration,
- additional BRICS languages,
- integration with real government and open-data systems,
- advanced geospatial and semantic clustering,
- country-specific policy and infrastructure adapters,
- longitudinal infrastructure impact measurement, and
- citizen feedback loops after project implementation.

---

## 🌍 Vision

CivicPulse AI aims to create a reusable civic intelligence layer where development decisions can be traced from:

```text
Citizen Voice
     ↓
Public Evidence
     ↓
Infrastructure Need
     ↓
Transparent Priority
     ↓
Policy Recommendation
     ↓
Human Decision
```

**Turning millions of citizen voices into transparent, explainable and evidence-backed development intelligence.**

---

## ⚠️ Data Disclaimer

The current demonstration datasets are **synthetic and generated for development and evaluation purposes**.

Population, infrastructure, investment, citizen-request, hotspot, priority, and recommendation data shown in the demonstration must not be interpreted as real government statistics or official policy recommendations.

---

## 📄 License

Add the project's open-source license here.

For a Digital Public Good deployment, consider selecting an appropriate OSI-approved open-source license and documenting reuse requirements.
