# GDELT Analysis Platform — Architecture

## Overview

The current platform is a tabbed analytics application with three complementary modes:

- **AI Explore**: Natural language event analysis and report generation
- **Dashboard**: Fast, structured visual analytics
- **Forecast**: Event risk forecasting based on historical patterns

The core design separates fast data access from LLM-driven reasoning.

## Design Principles

1. **Fast data path for dashboard**: Structured dashboard queries should avoid LLM round trips.
2. **AI Explore is a planner + executor flow**: Natural language is interpreted by an LLM planner, then converted into targeted database queries.
3. **Reports are delayed-load**: Analysis returns data first; report generation happens only when requested.
4. **Reuse the shared query layer**: `backend/queries/core_queries.py` is the single source of truth for database SQL.
5. **Forecasting is a separate service**: Event risk estimation runs in `backend/services/thp_service.py`.

## Layer Diagram

```
┌─────────────────────────────────────────┐
│              Frontend Layer             │
│  ┌──────────┐ ┌───────────┐ ┌───────────┐│
│  │ AI Explore│ │ Forecast │ │ Dashboard ││
│  └────┬──────┘ └────┬──────┘ └────┬──────┘│
└───────┼──────────────┼───────────────┘
        │              │
        ▼              ▼
   ┌──────────────────────────────────────┐
   │         FastAPI Backend              │
   │                                      │
   │  /api/v1/data/*   →  DataService      │
   │  /api/v1/analyze  →  Planner/Executor │
   │                                      │
   └────────────┬─────────────────────────┘
                │
                ▼
       ┌──────────────────────────┐
       │      MySQL Database      │
       └──────────────────────────┘
```

## Layers

### 1. Frontend

**React + Vite + TypeScript**

- `App.tsx` presents three tabs: `AI Explore`, `Forecast`, `Dashboard`
- `ExplorePanel.tsx` drives natural language exploration and report loading
- `Dashboard.tsx` renders charts, maps, and stats from `/api/v1/data`
- `ForecastWorkspace.tsx` interacts with forecasting APIs

### 2. FastAPI Backend

**Backend entry point**: `backend/main.py`

- Registers `/api/v1/data` and `/api/v1/analyze`
- Provides CORS for local frontend development
- Serves built frontend from `frontend/dist` when available

### 3. Data API Path

**Router**: `backend/routers/data.py`

- Directly returns structured JSON for charts
- Uses `DataService` to call shared query functions
- Supports autocomplete, event search, geo points, dashboard summaries, and forecast

### 4. AI Explore Path

**Router**: `backend/routers/analyze.py`

- `POST /api/v1/analyze`: LLM planner decides query steps and executor runs them
- `POST /api/v1/analyze/report`: generates natural language reports from returned data
- `Planner` and `ReportGenerator` live in `backend/agents/planner.py`

### 5. Shared Query Layer

**Shared SQL**: `backend/queries/core_queries.py`

- Encapsulates SQL for dashboard and analysis execution
- Used by `DataService`, `Executor`, and backend query routes
- Keeps database logic centralized and reusable

### 6. Forecasting

**Service**: `backend/services/thp_service.py`

- Implements Transformer-Hawkes forecasting logic
- Powered by event sequence data from `query_event_sequence`
- Exposed through `GET /api/v1/data/forecast`

## Notes on `mcp_server`

The `mcp_server/` directory remains in the repo as an optional tool server and legacy reference layer, but the current core app runs from `backend/` without requiring the separate MCP server process.
