"""
Data Service — Thin wrapper around shared core_queries.

No SQL is written here. All queries go through backend.queries.core_queries,
ensuring a single source of truth for data logic.

Dashboard calls these directly (fast, < 300ms).
Planner Executor calls them via parallel asyncio.gather.
"""

import time
from typing import List, Dict, Any, Optional

from backend.database.pool import DatabasePool, get_db_pool
from backend.queries.core_queries import (
    query_dashboard,
    query_time_series,
    query_geo_heatmap,
    query_search_events,
    query_geo_events,
    query_suggest_actors,
    query_suggest_locations,
    query_event_detail,
    query_similar_events,
    query_regional_overview,
    query_hot_events,
    query_top_events,
    query_daily_brief,
    query_stream_events,
    query_search_news_context,
    query_event_sequence,
    query_insights,
)
from backend.services.thp_service import TransformerHawkesForecaster


class DataService:
    """High-performance data service for Dashboard APIs and Planner Executor."""

    def __init__(self):
        self._pool: Optional[DatabasePool] = None
        self._initialized = False
        self._thp = TransformerHawkesForecaster()

    async def initialize(self):
        if not self._initialized:
            self._pool = await get_db_pool()
            self._initialized = True

    async def close(self):
        from backend.database.pool import close_db_pool
        await close_db_pool()
        self._pool = None
        self._initialized = False

    async def get_dashboard(self, start_date: str, end_date: str) -> Dict[str, Any]:
        start = time.time()
        result = await query_dashboard(self._pool, start_date, end_date)
        result["_meta"] = {
            "elapsed_ms": round((time.time() - start) * 1000, 2),
            "start_date": start_date,
            "end_date": end_date,
        }
        return result

    async def get_time_series(
        self, start_date: str, end_date: str, granularity: str = "day"
    ) -> List[Dict[str, Any]]:
        return await query_time_series(self._pool, start_date, end_date, granularity)

    async def get_geo_heatmap(
        self, start_date: str, end_date: str, precision: int = 2
    ) -> List[Dict[str, Any]]:
        return await query_geo_heatmap(self._pool, start_date, end_date, precision)

    async def search_events(
        self, query_text: Optional[str] = None,
        start_date: Optional[str] = None, end_date: Optional[str] = None,
        time_hint: Optional[str] = None,
        location_hint: Optional[str] = None,
        location_exact: Optional[str] = None,
        event_type: Optional[str] = None,
        actor: Optional[str] = None,
        actor_exact: Optional[str] = None,
        max_results: int = 20,
    ) -> List[Dict[str, Any]]:
        return await query_search_events(
            self._pool, query_text, start_date, end_date,
            time_hint, location_hint, location_exact,
            event_type, actor, actor_exact, max_results
        )

    async def get_geo_events(
        self, start_date: str, end_date: str,
        location_hint: Optional[str] = None,
        location_exact: Optional[str] = None,
        event_type: Optional[str] = None,
        actor: Optional[str] = None,
        actor_exact: Optional[str] = None,
        max_results: int = 100,
    ) -> List[Dict[str, Any]]:
        return await query_geo_events(
            self._pool, start_date, end_date,
            location_hint, location_exact,
            event_type, actor, actor_exact, max_results
        )

    async def suggest_actors(self, prefix: str, limit: int = 10) -> List[str]:
        return await query_suggest_actors(self._pool, prefix, limit)

    async def suggest_locations(self, prefix: str, limit: int = 10) -> List[str]:
        return await query_suggest_locations(self._pool, prefix, limit)

    async def get_event_detail(self, fingerprint: str) -> Optional[Dict[str, Any]]:
        return await query_event_detail(self._pool, fingerprint)

    async def get_similar_events(self, seed_event_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        return await query_similar_events(self._pool, seed_event_id, limit)

    async def get_regional_overview(
        self, region: str, time_range: str = "week",
        start_date: Optional[str] = None, end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        return await query_regional_overview(self._pool, region, time_range, start_date, end_date)

    async def get_hot_events(
        self, query_date: Optional[str] = None, region_filter: Optional[str] = None, top_n: int = 5
    ) -> List[Dict[str, Any]]:
        return await query_hot_events(self._pool, query_date, region_filter, top_n)

    async def get_top_events(
        self, start_date: str, end_date: str,
        region_filter: Optional[str] = None, event_type: Optional[str] = None, top_n: int = 10
    ) -> List[Dict[str, Any]]:
        return await query_top_events(self._pool, start_date, end_date, region_filter, event_type, top_n)

    async def get_daily_brief(self, query_date: Optional[str] = None) -> Optional[Dict[str, Any]]:
        return await query_daily_brief(self._pool, query_date)

    async def get_insights(self, start_date: str, end_date: str) -> Dict[str, Any]:
        return await query_insights(self._pool, start_date, end_date)

    async def forecast_event_risk(
        self,
        start_date: str,
        end_date: str,
        region: Optional[str] = None,
        actor: Optional[str] = None,
        event_type: str = "all",
        forecast_days: int = 7,
    ) -> Dict[str, Any]:
        """Forecast event intensity with the Transformer Hawkes service."""
        rows = await query_event_sequence(
            self._pool,
            start_date=start_date,
            end_date=end_date,
            region=region,
            actor=actor,
            event_type=event_type,
        )
        return self._thp.forecast(
            rows=rows,
            start_date=start_date,
            end_date=end_date,
            forecast_days=forecast_days,
            region=region,
            actor=actor,
            event_type=event_type,
        )

    async def stream_events(
        self,
        actor_name: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        max_results: int = 100,
    ) -> List[Dict[str, Any]]:
        """Memory-friendly streaming query for events by actor name."""
        rows = []
        async for row in query_stream_events(
            self._pool, actor_name, start_date, end_date, max_results
        ):
            rows.append(row)
            if len(rows) >= max_results:
                break
        return rows

    async def search_news_context(
        self, query: str, n_results: int = 5
    ) -> Dict[str, Any]:
        """Search news article content via ChromaDB vector semantic search."""
        return await query_search_news_context(query, n_results)

    def get_cache_stats(self) -> Dict[str, Any]:
        checkpoint = getattr(self._thp, "neural_checkpoint", None)
        return {
            "mode": "shared_queries",
            "note": "Queries handled by core_queries",
            "thp_model": self._thp._model_name(),
            "thp_checkpoint_available": bool(getattr(checkpoint, "available", False)),
            "thp_checkpoint_error": getattr(checkpoint, "error", None),
        }

    async def health_check(self) -> Dict[str, Any]:
        try:
            import time as _time
            t0 = _time.time()
            await self._pool.fetchone("SELECT 1 as test, NOW() as server_time")
            latency_ms = round((_time.time() - t0) * 1000, 2)
            return {"status": "healthy", "latency_ms": latency_ms}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}


# Singleton instance
data_service = DataService()
