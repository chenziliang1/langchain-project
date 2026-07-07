# GDELT Analysis Platform

An end-to-end DBMS and AI analytics platform for exploring 2024 GDELT event data. The system combines a MySQL-backed dashboard, a LangChain-style analyst chat agent, ChromaDB retrieval, and a Transformer-Hawkes Process (THP) forecasting service.

This private repository package includes the final forecast model artifacts and local training logs. API keys and local `.env` files are intentionally not included.

## Main Features

- **Dashboard:** interactive event analytics with date, location, actor, and event-type filters.
- **Map hotspot drilldown:** click geographic markers to inspect representative events at a location.
- **Representative events:** dashboard-level examples selected from the active filter range.
- **Analyst Chat:** natural-language event analysis using tool routing, SQL-backed data access, ChromaDB retrieval, and LLM summarization.
- **Forecast:** seven-day event risk forecasting powered by the final THP checkpoint.
- **Compare Mode:** compare two locations or actors over the selected range by event category.
- **Report export:** export dashboard summaries and current analytical context.

## Included Artifacts

The repository is prepared as a private complete-project package.

Included:

- `models/thp_gdelt.pt`: final THP checkpoint used by the Forecast page and API.
- `models/thp_training_dataset.npz`: cached training array.
- `models/thp_calibration_dataset_seq14_h7.npz`: calibration/evaluation data.
- `models/training_logs/`: training logs and per-run metadata.
- `models/thp_sweeps/`: sweep outputs and intermediate checkpoints.
- `logs/`: local import, ETL, and THP training logs.
- `chroma_db/`: local ChromaDB vector index used by chat retrieval.
- `reports/`: final report/case-study materials generated during the project.

Not included:

- `.env` or `.env.*` files with API keys.
- `node_modules/` and frontend build output.
- Python cache files.
- Docker volume files and live MySQL database storage.

Note: the local `data/` folder currently contains only `.gitkeep`. Raw GDELT CSV chunks must be added separately if you need to rebuild the database from scratch.

## Tech Stack

- **Backend:** Python, FastAPI, Pydantic, aiomysql, PyTorch, NumPy, Pandas.
- **AI layer:** LangChain-style tool orchestration, OpenAI-compatible LLM calls, optional local routing, ChromaDB retrieval.
- **Database:** MySQL 8.0 with indexes and spatial columns.
- **Frontend:** React, TypeScript, Vite, ECharts, Leaflet.
- **Deployment:** Docker Compose for MySQL, backend, and frontend services.

## Quick Start

### 1. Clone

```powershell
git clone https://github.com/chenziliang1/langchain-project.git
cd langchain-project
```

### 2. Create `.env`

```powershell
Copy-Item .env.example .env
```

Edit `.env` and fill only the keys you need.

Dashboard and Forecast can run without an LLM key. Analyst Chat needs an OpenAI-compatible key such as Kimi or OpenAI.

Important default values:

```env
DB_HOST=db
DB_PORT=3306
DB_HOST_PORT=3307
DB_USER=root
DB_PASSWORD=rootpassword
DB_NAME=gdelt

BACKEND_PORT=8000
FRONTEND_PORT=5173

THP_CHECKPOINT_PATH=models/thp_gdelt.pt
CHROMA_DB_PATH=/app/chroma_db
KIMI_CODE_API_KEY=
```

### 3. Start Docker

Make sure Docker Desktop is running, then start the stack:

```powershell
docker compose up -d
```

Services:

- Frontend: `http://localhost:5173`
- Backend: `http://localhost:8000`
- API docs: `http://localhost:8000/docs`
- MySQL host port: `localhost:3307`

### 4. Verify Backend

```powershell
Invoke-WebRequest http://localhost:8000/health
```

### 5. Open Forecast

Open `http://localhost:5173`, then switch to the **Forecast** tab.

The final THP model is already included at `models/thp_gdelt.pt`, so the Forecast page can load the checkpoint directly. For best results, choose forecast start dates on or after `2024-01-31`, because the model uses a historical lookback window.

## Database Setup

If the MySQL container is empty, add GDELT CSV files into `data/` and import them:

```powershell
docker exec -it gdelt_backend python db_scripts/import_event.py
docker exec -it gdelt_backend python db_scripts/etl_pipeline.py
Get-Content db_scripts/all_indexes.sql | docker exec -i gdelt_mysql mysql -u root -prootpassword gdelt
```

Useful database scripts:

- `db_scripts/gdelt_db_v1.sql`: base schema.
- `db_scripts/import_event.py`: CSV importer.
- `db_scripts/etl_pipeline.py`: precompute tables and event fingerprints.
- `db_scripts/all_indexes.sql`: indexes for dashboard, search, actor/location filtering, and spatial lookup.
- `db_scripts/build_knowledge_base.py`: rebuild ChromaDB retrieval index from stored event/news data.

## Forecast and THP

The Forecast module uses a neural Transformer-Hawkes Process model:

1. Load a 30-day historical lookback from GDELT summaries.
2. Build rolling features including event counts, tone, Goldstein score, actor/country-pair signals, and event category features.
3. Feed the latest 14 daily vectors into the Transformer encoder.
4. Apply a Hawkes-style forecasting head to model short-term excitation and decay.
5. Return seven days of low, median, and high forecast values.

Evaluation summary from the local checkpoint:

- THP MAE: `83.77`
- 7-day moving-average baseline MAE: `167.74`
- Approximate MAE reduction: `50%`
- Checkpoint size: about `1.56 MB`

API example:

```powershell
Invoke-RestMethod "http://localhost:8000/api/v1/data/forecast?forecast_start=2024-02-01&mode=location&target=United%20States%20and%20Canada&event_type=all"
```

## Analyst Chat and ChromaDB

The chat system is data-grounded rather than purely conversational.

High-level flow:

1. User asks a natural-language event question.
2. The planner extracts intent, dates, actors, locations, and event category.
3. The agent routes to SQL tools, dashboard/time-series tools, forecast tools, or ChromaDB retrieval.
4. Tool results are passed to the LLM for a concise analytical answer.
5. The UI displays the answer, tool trace, and optional supporting data.

ChromaDB is used for semantic retrieval over local event/news context. The included `chroma_db/` folder lets the chat layer reuse the existing vector index. To rebuild it:

```powershell
docker exec -it gdelt_backend python db_scripts/build_knowledge_base.py
```

## Local Development Without Docker

Backend:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

Frontend:

```powershell
cd frontend
npm install
npm run dev
```

If PowerShell says `npm` is not recognized, install Node.js 20+ and reopen the terminal.

## Project Structure

```text
backend/                 FastAPI app, data routers, chat planner, services
backend/agents/          Tool-routing analyst agent and enhanced reporter
backend/queries/         Shared SQL query layer
backend/services/        Dashboard data, THP forecast, Chroma/news/storyline services
db_scripts/              Schema, import, ETL, precompute, index, and THP training scripts
frontend/                React + TypeScript + Vite UI
models/                  Final THP checkpoint, training arrays, sweeps, logs
chroma_db/               Local persistent ChromaDB retrieval index
logs/                    Import, ETL, runtime, and training logs
reports/                 Project report and case-study materials
data/                    Place raw GDELT CSV chunks here when rebuilding the DB
```

## Common Issues

- **Frontend opens but dashboard is empty:** import CSV data into MySQL and run `etl_pipeline.py`.
- **Forecast says not enough historical data:** use forecast start `2024-01-31` or later.
- **Chat responds without data:** check MySQL data, `.env` LLM key, and `CHROMA_DB_PATH`.
- **Docker cannot connect:** start Docker Desktop before running `docker compose up -d`.
- **Map drilldown has no events:** run ETL/precompute scripts and verify spatial indexes.

## Safety Notes

- Do not commit `.env`.
- Do not paste API keys into README, source files, notebooks, or logs.
- Docker MySQL volumes are not part of this Git upload; they must be recreated by import scripts or shared separately as a dump.
