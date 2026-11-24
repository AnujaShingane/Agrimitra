# AgriMitra

AgriMitra is a full-stack agricultural assistant for Indian farmers. The app combines a FastAPI backend, a LangGraph corrective-RAG workflow, a local FAISS knowledge base, and live API integrations for market, weather, and scheme data.

## Actual architecture

- Frontend: React + Vite + React Router
- Backend: FastAPI + LangGraph + runtime SQLite checkpointing
- Retrieval: FAISS + all-MiniLM-L6-v2 embeddings
- Optional reranking: sentence-transformers CrossEncoder
- LLM synthesis: Groq via `langchain-groq`
- Live data: data.gov.in / AGMARKNET, OpenWeatherMap, and official scheme links
- Scanner: currently a guarded image pipeline; real trained leaf-disease weights are not shipped in this repo

`React/Vite → FastAPI → LangGraph route → FAISS retrieval → optional rerank → live-data checks → Groq synthesis → SSE response`

## Directory structure

- `backend/` — FastAPI app, RAG pipeline, market/weather logic, tests, vector store
- `backend/data/docs/` — maintained agriculture reference documents used for retrieval
- `backend/faiss_index/` — persisted FAISS index
- `backend/scripts/` — dataset/training helpers
- `frontend/src/` — app UI and feature pages

## Tech stack

- Python 3.11+ (project uses a virtual environment)
- FastAPI / Uvicorn
- LangChain / LangGraph
- FAISS + sentence-transformers
- React 19 + Vite + Framer Motion
- Lucide icons

## Quick start

1. Copy `backend/.env.example` to `backend/.env` and configure the keys you need. The auth database is created automatically under `backend/runtime/`.
2. Backend:

```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

3. Frontend:

```powershell
cd frontend
npm install
npm run dev
```

Open http://localhost:5173.

The root page is the public landing page. Create an account or log in to enter the farming dashboard; dashboard pages require a signed-in account. For HTTPS deployments, set `AUTH_COOKIE_SECURE=true`.

## Required environment variables

These are the real variables used by the implementation:

- `GROQ_API_KEY` — required for chat synthesis and optional vision usage
- `GROQ_MODEL` — default Groq chat model
- `GROQ_VISION_MODEL` — optional Groq vision model
- `GROQ_VISION_MAX_COMPLETION_TOKENS` — scanner output budget; default `800` to stay within low-tier Groq limits
- `DATAGOV_API_KEY` — required for live market data
- `DATAGOV_MARKET_RESOURCE_ID` — optional AGMARKNET resource override
- `OPENWEATHER_API_KEY` — required for live weather data
- `PLANT_DISEASE_MODEL_PATH` — optional path to a trained plant disease model
- `REDIS_URL` — optional caching backend
- `CHECKPOINT_DB_PATH` — runtime SQLite path for session conversation state
- `AUTH_DATABASE_PATH` — runtime SQLite path for user accounts (defaults to `backend/runtime/auth.sqlite3`)
- `AUTH_COOKIE_SECURE` — set to `true` when the app is served over HTTPS
- `FRONTEND_URL` — backend CORS origin

## Feature status

### 1) AI Chat

Implemented and routed through the LangGraph CRAG workflow. It uses local FAISS retrieval and optionally live web search for time-sensitive questions. The app does not fabricate a response when Groq is unavailable; it returns a clear backend error instead.

### 2) Leaf Scanner

The code validates uploaded images and sends them to Groq vision if a Groq key is configured. There is no trained weights file shipped with the repo, so the app explicitly returns a clear "model not configured" error instead of faking a diagnosis when the model is missing.

### 3) Market prices

The market page calls `/api/market` and uses live AGMARKNET records from data.gov.in. It fails with a clear 503 if the API key or provider is unavailable; it does not fall back to bundled or mock prices.

### 4) Weather

The weather page calls `/api/weather/{state}/{city}` and uses live OpenWeatherMap data. It fails explicitly when the API key is missing or the provider is unavailable; it does not fall back to bundled or mock forecasts.

### 5) Government schemes

The backend maintains a small structured catalog of scheme names, descriptions, and official destination links in `backend/schemes_data.py`. It does not claim to be a live scheme API; benefit values and eligibility should be checked on the linked official portal.

## RAG pipeline

The retrieval stack is:

1. Route query to relevant agent(s)
2. Retrieve FAISS candidates
3. Re-rank with optional CrossEncoder
4. Run local relevance filtering
5. Trigger live web search for current data when needed
6. Synthesize answer via Groq

The vector index is persisted under `backend/faiss_index/` and should only be rebuilt when the document corpus changes. Rebuild it with `python ingest.py`; the index must never be treated as a source for current prices or weather.

## Leaf disease ML pipeline

The repository contains no trained leaf-disease weights or dataset. The recommended setup is a transfer-learning model such as MobileNetV2 or EfficientNet on a plant disease dataset like PlantVillage. A training helper script is included under `backend/scripts/train_plant_disease_model.py` to document the process, but it is intentionally not claimed as already executed.

### Training requirements

- A dataset such as PlantVillage or a curated leaf-disease dataset
- Python environment with TensorFlow/Keras and Pillow
- `PLANT_DISEASE_MODEL_PATH` set to the output model path
- `class_labels.json` saved alongside the model

## Runtime data and storage

- Chat session state is stored in the runtime SQLite database configured by `CHECKPOINT_DB_PATH`. It is not source content and should not be committed.
- Redis is optional and caches live market responses for one hour when configured.
- Uploaded audio and leaf images are processed in memory and are not written to disk by the API.
- No placeholder PDFs, generated fallback documents, or fake market/weather responses are part of the project.

For a multi-instance production deployment, use a managed PostgreSQL-compatible database and set the checkpoint backend accordingly; local SQLite is suitable for a single backend instance and development.

## Testing

```powershell
cd backend
.\venv\Scripts\python.exe -m pytest tests -q
cd ..\frontend
npm run build
```

The repository currently includes backend tests for health, routing, memory, and live-data routing logic.

## Known limitations

- The app does not ship trained ML weights, so the scanner cannot produce a real diagnosis without a dataset plus training pipeline execution.
- Live market and weather sources require credentials that are not committed to source control.
- Scheme descriptions are maintained application content; the linked official portals are authoritative for current eligibility, amounts, and deadlines.
- Groq-dependent features fail clearly rather than returning fake data when set up is incomplete.

## Troubleshooting

- If `/api/chat` fails, confirm `GROQ_API_KEY` is set in `backend/.env`.
- If market requests fail, set `DATAGOV_API_KEY` and verify it is active.
- If weather requests fail, set `OPENWEATHER_API_KEY`.
- If the scanner reports model unavailable, train and deploy a model or set `PLANT_DISEASE_MODEL_PATH`.
- If the frontend cannot reach the backend, confirm Vite proxy settings or set `VITE_BACKEND_URL`.
