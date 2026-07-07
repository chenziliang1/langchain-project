# Final Report: GDELT Analysis Platform

## Abstract

This project develops an AI-driven event analysis platform for GDELT 2.0 North America 2024 data. The system combines a MySQL-backed spatio-temporal event database, a FastAPI service layer, a React visualization interface, semantic news retrieval through ChromaDB, and a Transformer-Hawkes Process forecasting module. Compared with the earlier checkpoint design, the final implementation no longer relies on the Model Context Protocol as the active execution path. The current main branch uses a LangChain-based hybrid planner: a local Ollama router extracts query structure, a rule-based fast path handles simple analytical requests, and a remote LLM generates natural language reports for complex analysis. Structured queries are executed through a shared SQL/DataService layer, while ChromaDB provides retrieval-augmented context for news-oriented questions. In the local final deployment, the trained THP checkpoint and training logs are stored as model artifacts and can be loaded by the FastAPI forecast service.

The final platform supports three main user workflows: AI Explore for natural language analysis, Dashboard for interactive event visualization, and Forecast for short-term event risk prediction. Database performance is improved through precomputed summary tables such as `daily_summary`, `event_fingerprints`, `region_daily_stats`, and `geo_heatmap_grid`. The forecasting module uses a compact neural Transformer-Hawkes model architecture that reads daily historical event sequences and predicts seven-day event intensity with uncertainty intervals. Together, these components transform raw GDELT records into a practical system for spatio-temporal exploration, quantitative forecasting, and narrative event analysis.

## 1. Introduction

Large-scale event datasets such as GDELT contain rich information about global conflict, cooperation, actors, locations, media attention, and sentiment. However, raw event records are difficult to explore directly because meaningful analysis usually requires filtering by time, geography, actor names, event codes, and media context. Analysts must often write many SQL queries manually before they can form a coherent understanding of what happened, where it happened, and how it changed over time.

The goal of this project is to build an interactive analysis platform that makes GDELT data easier to query, visualize, and explain. The project focuses on North American events in 2024, especially events associated with the United States, Canada, and Mexico. The final platform provides a web interface where users can inspect dashboard summaries, ask natural language questions, drill down into representative events, and generate short-term event forecasts.

The major architectural change from the checkpoint report is the replacement of the active MCP-centered agent design with a LangChain-based hybrid routing pipeline. In the current main branch, `mcp_server/` remains as a legacy, currently unused directory. The production path uses FastAPI endpoints, a shared SQL query layer, and LangChain `ChatOpenAI` integration for LLM providers such as Kimi, Moonshot, OpenAI, or Claude. This change simplifies the system, reduces tool-calling overhead, and makes the frontend/backend integration more direct.

## 2. Related Work

This project builds on prior work in event data management, geopolitical risk analysis, retrieval-augmented generation, and temporal event forecasting. GDELT provides structured event records based on actors, actions, locations, CAMEO event codes, Goldstein scores, and media tone. These features are widely used to study conflict and cooperation patterns at large scale.

Traditional database systems are effective for structured retrieval, aggregation, and indexing, but they do not automatically explain trends in natural language. LLM-based systems address this limitation by translating user intent into analytical plans and summaries. However, LLMs alone are not reliable numerical forecasters because they are not trained to model event-count time series directly. For this reason, the project combines an LLM analysis layer with a dedicated Transformer-Hawkes forecasting service.

The forecasting component is inspired by temporal point-process and Hawkes-process modeling. Hawkes processes are useful for event streams because they represent self-excitation: a spike in events can increase short-term future intensity before decaying. The final model extends this idea with a Transformer encoder, allowing the system to learn which previous days in the historical window matter most for the next seven days.

## 3. Final System Architecture

The final system follows a modular architecture with four primary layers: data storage, query services, intelligence services, and frontend presentation.

### 3.1 Data Layer

The main data store is MySQL 8.0+, containing GDELT event records in `events_table`. Important fields include `SQLDATE`, `Actor1Name`, `Actor2Name`, `EventCode`, `EventRootCode`, `QuadClass`, `GoldsteinScale`, `AvgTone`, `NumArticles`, and geographic fields such as `ActionGeo_Lat`, `ActionGeo_Long`, and `ActionGeo_FullName`.

To support fast dashboard and map queries, the project includes precomputed tables:

- `daily_summary`: daily totals, conflict/cooperation counts, sentiment, top actors, top locations, and hot event fingerprints.
- `event_fingerprints`: enriched event-level records with headline, summary, event type label, and severity score.
- `region_daily_stats`: per-region daily aggregation.
- `geo_heatmap_grid`: pre-aggregated geographic grid cells for fast map rendering.

The database scripts also include index creation, search indexes, spatial index preparation, ETL backfill scripts, and database status checks. These components move expensive aggregation work out of real-time API calls.

### 3.2 Backend Service Layer

The backend is implemented with FastAPI. Its main responsibilities are exposing REST endpoints, managing asynchronous MySQL access, validating request/response schemas with Pydantic, and coordinating data retrieval through `DataService`.

The shared SQL layer in `backend/queries/core_queries.py` is the single source of truth for analytical queries. Dashboard, map, time-series, event search, event detail, semantic news search, and THP forecasting all rely on this shared query layer rather than duplicating SQL logic across services.

Key API groups include:

- `/api/v1/data/dashboard`: dashboard summary metrics.
- `/api/v1/data/timeseries`: daily event and conflict/cooperation trends.
- `/api/v1/data/geo`: geographic heatmap data.
- `/api/v1/data/events`: filtered event search.
- `/api/v1/data/geo/events`: hotspot drilldown events.
- `/api/v1/data/forecast`: Transformer-Hawkes risk forecast.
- `/api/v1/analyze/analyze`: AI planner and executor.
- `/api/v1/analyze/report`: LLM-generated analytical report.
- `/api/v1/analyze/event-report`: enhanced event report with storyline, news, and optional GKG context.

### 3.3 Intelligence Layer

The active intelligence layer is LangChain-based rather than MCP-based. The planner combines three mechanisms:

- Local Ollama router using `qwen2.5:3b` to extract location, date range, event type, query text, and intent category.
- Rule-based fast path for simple queries where the system can directly call dashboard, time-series, map, or event-search endpoints without a remote LLM.
- Remote LLM report generation through LangChain `ChatOpenAI` for complex queries requiring comparison, synthesis, or explanation.

This design separates structured retrieval from narrative generation. The database layer returns grounded JSON results first; the LLM then summarizes those results into readable analysis. This reduces hallucination risk because the report generator is prompted to explain retrieved data instead of inventing facts.

### 3.4 RAG and News Context

The project includes a semantic news search pipeline using ChromaDB and Sentence-Transformers. Event summaries and article snippets are embedded with `all-MiniLM-L6-v2` and stored in a persistent ChromaDB collection named `gdelt_news_collection`. When a query requires news context, the backend performs vector similarity search and returns relevant event IDs, dates, source URLs, and content snippets.

This RAG component complements the structured SQL layer. SQL is used for precise filtering by date, actor, event type, and geography, while ChromaDB is used for semantic matching when the user asks open-ended questions about topics, themes, or narratives.

### 3.5 Frontend Layer

The frontend is implemented with React, TypeScript, Vite, ECharts, and Leaflet. It provides three major tabs:

- AI Explore: natural language query interface with planner output and generated reports.
- Forecast: Transformer-Hawkes event risk forecasting workspace.
- Dashboard: interactive event visualization with KPI cards, time-series charts, geographic heatmap, filters, top actors, representative events, and hotspot drilldown.

The Dashboard tab focuses on historical exploration. The Forecast tab is separated from Dashboard so that forecasting controls and output do not duplicate dashboard visualizations. This improves page responsibility and reduces unnecessary loading.

## 4. Database Design and Optimization

The database design emphasizes fast analytical retrieval over raw storage alone. The original GDELT event data is stored in a normalized event table, while derived tables provide frequently used aggregations.

The `daily_summary` table is central to performance. Instead of grouping millions of rows every time the dashboard loads, the backend first checks for daily precomputed rows and uses them for summary cards and time-series metrics. The README describes the dashboard target as sub-200ms response time when these summary tables are populated.

The map view uses `geo_heatmap_grid`, which aggregates events into geographic cells. This reduces the cost of repeatedly scanning raw latitude/longitude rows and enables fast rendering of conflict/cooperation hotspots in Leaflet. Spatial index scripts are also included for geographic queries after coordinates and SRID values are cleaned.

The `event_fingerprints` table provides a bridge between raw event records and user-facing explanations. It stores concise labels, summaries, severity scores, and fingerprints that make event search and representative-event display more readable than raw GDELT rows alone.

## 5. AI Explore Pipeline

The AI Explore workflow begins when a user enters a natural language question. The local router first extracts structured context such as date range, location, event type, and intent. If the query is simple, the rule-based fast path directly retrieves data through the DataService. If the query requires reasoning or comparison, the planner creates a query plan and the backend executes the necessary steps.

The system uses a two-stage report design:

1. The planner and executor return grounded data and visualization plans.
2. The report generator lazily converts those results into natural language.

This design keeps the interface responsive because the frontend can display retrieved data before waiting for the full LLM narrative. It also makes debugging easier because the returned data, plan, and report are separate.

For event-specific analysis, the enhanced report endpoint can include an executive summary, event storyline, actor activity overview, GKG insights, and news coverage. Optional BigQuery-based GKG and Mentions queries can be enabled for deeper media-context analysis while preserving cost controls.

## 6. Transformer-Hawkes Forecasting Module

The final project includes a Transformer-Hawkes Process forecasting module for seven-day event risk prediction. The backend endpoint is `/api/v1/data/forecast`, and the frontend exposes it through the Forecast tab.

The forecast service loads a historical daily sequence for the selected target and event type. Targets may be based on location/country, actor, country pair, or actor pair depending on the request parameters and normalization logic. Supported event types include all events, conflict, cooperation, and protest.

The neural model uses:

- A 30-day sequence length by default.
- Sixteen daily features, including event count, conflict ratio, cooperation ratio, Goldstein score, media tone, article volume, calendar features, and rolling statistics.
- Series embeddings for target identity.
- Event-type embeddings for multitask forecasting.
- Series-group embeddings for global, country, actor, country-pair, actor-pair, event-root, and event-code groups.
- A Transformer encoder with attention pooling.
- A Hawkes-style head that models baseline intensity, excitation, and exponential decay.
- A direct multi-horizon head for seven-day forecasts.

The training script `db_scripts/train_thp_model.py` supports GPU training, mixed precision, `torch.compile`, early stopping, hyperparameter search, dataset caching, per-category evaluation, rolling-origin backtesting, and baseline comparison against naive, moving average, and empirical Hawkes baselines.

The FastAPI service attempts to load a checkpoint from `THP_CHECKPOINT_PATH`, defaulting to `models/thp_gdelt.pt`. In the local final environment, the trained checkpoint exists at `models/thp_gdelt.pt`, with training logs stored under `models/training_logs/`. The final local checkpoint metadata identifies the model version as `thp_v5_series_event_normalized+calibrated`, uses CUDA mixed-precision training, supports a seven-day forecast horizon, and contains 736 target series across all, conflict, cooperation, and protest event types.

Although the local environment contains these model artifacts, the GitHub main branch does not necessarily track generated model weights, training caches, or training logs. This is intentional because those files are environment-specific artifacts. When the checkpoint is present, the forecast service uses the trained neural model. If it is missing, the service falls back to an empirical Transformer-Hawkes style forecast so the API contract remains usable.

The Forecast page displays:

- Recent historical trend and seven-day forecast.
- Expected/median event count.
- Low and high uncertainty interval.
- Peak forecast day.
- Model/checkpoint metadata when available.
- Source indicators showing whether the neural checkpoint was loaded.

## 7. Evaluation Strategy

The current training script evaluates the THP model on held-out historical windows. It reports standard regression metrics:

- MAE: average absolute forecast error.
- RMSE: square-rooted mean squared error, which penalizes large errors more strongly.
- MAPE: percentage error where applicable.

It also compares the neural THP model against baselines:

- Naive last-value baseline.
- Seven-day moving average baseline.
- Empirical Hawkes baseline.

The checkpoint metadata can store evaluation results, baseline improvement, per-category evaluation, residual calibration, and rolling-origin backtest statistics. This allows the Forecast page and backend to explain not only a prediction, but also how the model performed during historical validation.

In the local final checkpoint, the neural THP model reports an MAE of approximately 83.77. Compared with the seven-day moving average baseline MAE of approximately 167.74, this is about a 50.06% MAE reduction. The same checkpoint also reports improvements over the naive last-value baseline and the empirical Hawkes baseline. These results indicate that the trained neural model provides a substantially more accurate short-term forecast than simple historical baselines on the held-out validation windows.

For final deployment, model evaluation should be interpreted by target category. Global event counts are much larger and easier to stabilize, while narrow actor-pair or rare protest series are usually harder to predict. Therefore, global MAE and target-specific MAE should not be compared as if they had the same scale.

## 8. User Interface and Visualization

The Dashboard provides the historical data exploration layer. It includes:

- Total events, unique actors, total articles, and average Goldstein score.
- Daily event count and conflict/cooperation trend charts.
- Geographic heatmap with conflict/cooperation coloring.
- Map hotspot drilldown for location-specific event examples.
- Top actors and representative events.
- Search and filter controls for date, location, actor, and event type.
- Markdown report export.

The Forecast workspace is dedicated to future-looking analysis. It asks the user for a single forecast start date, a focus mode, a target, and an event type. It then loads the prior historical window and predicts the next seven days. This separation prevents Dashboard and Forecast from overlapping responsibilities.

The AI Explore tab provides the natural language interface. It is intended for questions such as comparing conflict and cooperation trends, summarizing regional events, asking for important events on a date, or requesting media-context explanations.

## 9. Implementation Results

Compared with the earlier checkpoint version, the final implementation makes several important improvements:

- The active architecture shifted from MCP-based tool execution to a LangChain-based hybrid planner with direct FastAPI/DataService queries.
- The React frontend was expanded from a basic chat-like interface into a three-tab analysis platform.
- Dashboard performance was improved through precomputed database tables and optimized query paths.
- ChromaDB was added for semantic news retrieval and RAG-style context enrichment.
- Event storyline and enhanced event report endpoints were added for deeper narrative analysis.
- A Transformer-Hawkes forecasting module was added for seven-day event risk prediction.
- A local final THP checkpoint and training logs were produced, with the checkpoint loaded by the FastAPI forecast service through `models/thp_gdelt.pt`.
- The THP training pipeline was expanded with multitask event types, target embeddings, rolling features, baseline comparison, per-category evaluation, and GPU-capable training options.
- The system supports multiple LLM providers through LangChain using OpenAI-compatible API configuration.

These changes move the project from a proof-of-concept agent architecture toward a complete analytical application with structured retrieval, semantic context, forecasting, and visualization.

## 10. Limitations and Future Work

The current system still has several limitations. First, the quality of forecasts depends on the availability of a trained THP checkpoint and sufficient historical data. The local final environment includes the checkpoint, but a fresh clone must either receive the model artifact or retrain the model before reproducing the same neural forecast behavior. If the checkpoint is missing, the backend falls back to the empirical forecaster. Second, narrow actor-pair or rare-event queries may have limited training samples, making their forecasts less stable than global or country-level forecasts. Third, ChromaDB search requires a built vector knowledge base; if `chroma_db/` has not been generated, semantic news search will not return results.

The system also relies on external LLM APIs for complex narrative generation unless a local model is configured. This introduces latency, cost, and API-key setup requirements. Optional BigQuery GKG and Mentions enrichment can improve event context, but it also requires Google Cloud configuration and cost controls.

Future work could include automated model artifact management, scheduled incremental updates for precomputed tables and ChromaDB, richer uncertainty calibration for THP predictions, more robust actor normalization, and a clearer deployment workflow for users who do not already have the local Docker database.

## 11. Conclusion

The final GDELT Analysis Platform integrates database systems, LLM-based analysis, vector retrieval, interactive visualization, and neural temporal forecasting. The project began with an MCP-centered design, but the current main branch uses a more direct LangChain-based hybrid architecture. FastAPI and the shared SQL layer provide grounded data access, ChromaDB adds semantic news context, and the Transformer-Hawkes module provides short-term quantitative forecasts.

The resulting system allows users to move from raw event records to dashboards, natural language explanations, event storylines, and forecasted event risk. This makes the platform useful not only as a database project, but also as a practical example of combining structured data management with modern AI-assisted analysis.

## References

[1] The GDELT Project. "GDELT 2.0 Event Database." https://www.gdeltproject.org/

[2] SolomonGao. "DBMSproject." GitHub repository, main branch. https://github.com/SolomonGao/DBMSproject/tree/main

[3] LangChain Documentation. https://python.langchain.com/

[4] ChromaDB Documentation. https://docs.trychroma.com/

[5] Hawkes, A. G. "Spectra of Some Self-Exciting and Mutually Exciting Point Processes." Biometrika, 1971.
