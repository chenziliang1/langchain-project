"""
Data Routes — Dashboard API

All endpoints return structured JSON for direct frontend chart rendering.
Delegates to MCP tools (core_tools_v2) via DataService.
"""

import time
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException

from backend.dependencies import get_data_service
from backend.services.data_service import DataService
from backend.schemas.responses import (
    DashboardResponse,
    TimeSeriesResponse,
    GeoHeatmapResponse,
    GeoEventsResponse,
    EventSearchResponse,
    SuggestionsResponse,
    ForecastResponse,
    HealthResponse,
    EventItem,
    TimeSeriesPoint,
    GeoPoint,
    GeoEventPoint,
    TopEventsResponse,
    InsightsResponse,
    HeadlineItem,
    QuadClassItem,
    ActorTypeItem,
    SentimentSummary,
)

router = APIRouter(prefix="/data", tags=["data"])


@router.get("/dashboard", response_model=DashboardResponse)
async def get_dashboard(
    start: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end: str = Query(..., description="End date (YYYY-MM-DD)"),
    service: DataService = Depends(get_data_service),
):
    """
    Get comprehensive dashboard data via MCP get_dashboard tool (format=json).
    """
    start_time = time.time()
    try:
        result = await service.get_dashboard(start, end)
        elapsed_ms = round((time.time() - start_time) * 1000, 2)
        
        return DashboardResponse(
            data=result,
            start_date=start,
            end_date=end,
            elapsed_ms=elapsed_ms,
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Dashboard query failed: {e}")


@router.get("/timeseries", response_model=TimeSeriesResponse)
async def get_timeseries(
    start: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end: str = Query(..., description="End date (YYYY-MM-DD)"),
    granularity: str = Query("day", description="day | week | month"),
    service: DataService = Depends(get_data_service),
):
    """
    Get time series data via MCP analyze_time_series tool (format=json).
    """
    try:
        rows = await service.get_time_series(start, end, granularity)
        data = [TimeSeriesPoint(**row) for row in rows]
        return TimeSeriesResponse(
            data=data,
            granularity=granularity,
            start_date=start,
            end_date=end,
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Time series query failed: {e}")


@router.get("/geo", response_model=GeoHeatmapResponse)
async def get_geo_heatmap(
    start: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end: str = Query(..., description="End date (YYYY-MM-DD)"),
    precision: int = Query(2, ge=1, le=4, description="Grid precision (1-4 decimal places)"),
    service: DataService = Depends(get_data_service),
):
    """
    Get geo heatmap grid data via MCP get_geo_heatmap tool (format=json).
    """
    try:
        rows = await service.get_geo_heatmap(start, end, precision)
        data = [GeoPoint(**row) for row in rows]
        return GeoHeatmapResponse(
            data=data,
            precision=precision,
            start_date=start,
            end_date=end,
            total_points=len(data),
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Geo query failed: {e}")


@router.get("/events", response_model=EventSearchResponse)
async def search_events(
    query: Optional[str] = Query(None, description="Search query text"),
    start: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    time_hint: Optional[str] = Query(None, description="e.g. 2024-01, this_month"),
    location_hint: Optional[str] = Query(None, description="Location keyword (fuzzy)"),
    location_exact: Optional[str] = Query(None, description="Location exact match (fast, uses index)"),
    event_type: Optional[str] = Query(None, description="conflict | cooperation | protest"),
    actor: Optional[str] = Query(None, description="Actor name keyword (fuzzy)"),
    actor_exact: Optional[str] = Query(None, description="Actor exact match (fast, uses index)"),
    limit: int = Query(20, ge=1, le=50),
    service: DataService = Depends(get_data_service),
):
    """
    Structured event search. Use *_exact params for fast index-backed exact match.
    """
    try:
        rows = await service.search_events(
            query_text=query,
            start_date=start,
            end_date=end,
            time_hint=time_hint,
            location_hint=location_hint,
            location_exact=location_exact,
            event_type=event_type,
            actor=actor,
            actor_exact=actor_exact,
            max_results=limit,
        )
        data = [EventItem(**row) for row in rows]
        return EventSearchResponse(
            data=data,
            query=query or "",
            total=len(data),
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Event search failed: {e}")


@router.get("/geo/events", response_model=GeoEventsResponse)
async def get_geo_events(
    start: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end: str = Query(..., description="End date (YYYY-MM-DD)"),
    location_hint: Optional[str] = Query(None, description="Location keyword (fuzzy)"),
    location_exact: Optional[str] = Query(None, description="Location exact match (fast, uses index)"),
    event_type: Optional[str] = Query(None, description="conflict | cooperation | protest"),
    actor: Optional[str] = Query(None, description="Actor name keyword (fuzzy)"),
    actor_exact: Optional[str] = Query(None, description="Actor exact match (fast, uses index)"),
    limit: int = Query(100, ge=1, le=200),
    service: DataService = Depends(get_data_service),
):
    """
    Get individual event points with coordinates for map display.
    """
    try:
        rows = await service.get_geo_events(
            start_date=start,
            end_date=end,
            location_hint=location_hint,
            location_exact=location_exact,
            event_type=event_type,
            actor=actor,
            actor_exact=actor_exact,
            max_results=limit,
        )
        data = [GeoEventPoint(**row) for row in rows]
        return GeoEventsResponse(
            data=data,
            start_date=start,
            end_date=end,
            total_points=len(data),
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Geo events query failed: {e}")


@router.get("/suggestions/actors", response_model=SuggestionsResponse)
async def suggest_actors(
    q: str = Query(..., min_length=1, description="Actor name prefix"),
    limit: int = Query(10, ge=1, le=50),
    service: DataService = Depends(get_data_service),
):
    """Return actor names matching the prefix for autocomplete."""
    try:
        items = await service.suggest_actors(prefix=q, limit=limit)
        return SuggestionsResponse(items=items, query=q)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Suggestion failed: {e}")


@router.get("/suggestions/locations", response_model=SuggestionsResponse)
async def suggest_locations(
    q: str = Query(..., min_length=1, description="Location name prefix"),
    limit: int = Query(10, ge=1, le=50),
    service: DataService = Depends(get_data_service),
):
    """Return location names matching the prefix for autocomplete."""
    try:
        items = await service.suggest_locations(prefix=q, limit=limit)
        return SuggestionsResponse(items=items, query=q)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Suggestion failed: {e}")


@router.get("/forecast", response_model=ForecastResponse)
async def get_forecast(
    start: str = Query(..., description="Historical input start date (YYYY-MM-DD)"),
    end: str = Query(..., description="Historical input end date (YYYY-MM-DD)"),
    region: Optional[str] = Query(None, description="Optional country, region, or country pair"),
    actor: Optional[str] = Query(None, description="Optional actor keyword"),
    event_type: str = Query("all", description="all | conflict | cooperation | protest"),
    forecast_days: int = Query(7, ge=1, le=60),
    service: DataService = Depends(get_data_service),
):
    """Forecast event intensity with the Transformer Hawkes service."""
    try:
        data = await service.forecast_event_risk(
            start_date=start,
            end_date=end,
            region=region,
            actor=actor,
            event_type=event_type,
            forecast_days=forecast_days,
        )
        return ForecastResponse(data=data, start_date=start, end_date=end)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Forecast query failed: {e}")


@router.get("/top-events", response_model=TopEventsResponse)
async def get_top_events(
    start: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end: str = Query(..., description="End date (YYYY-MM-DD)"),
    region: Optional[str] = Query(None, description="Optional region filter"),
    event_type: Optional[str] = Query(None, description="Optional event type filter"),
    limit: int = Query(5, ge=1, le=20),
    service: DataService = Depends(get_data_service),
):
    """Get top events by media coverage (NumArticles) for the date range."""
    try:
        rows = await service.get_top_events(start, end, region, event_type, limit)
        data = [EventItem(**row) for row in rows]
        return TopEventsResponse(
            data=data,
            start_date=start,
            end_date=end,
            total=len(data),
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Top events query failed: {e}")


@router.get("/insights", response_model=InsightsResponse)
async def get_insights(
    start: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end: str = Query(..., description="End date (YYYY-MM-DD)"),
    service: DataService = Depends(get_data_service),
):
    """Get overview insights: QuadClass distribution, actor types, top headlines, sentiment summary."""
    try:
        result = await service.get_insights(start, end)
        return InsightsResponse(
            data=result,
            start_date=start,
            end_date=end,
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Insights query failed: {e}")


@router.get("/health", response_model=HealthResponse)
async def health_check(
    service: DataService = Depends(get_data_service),
):
    """
    Health check including MCP latency.
    """
    try:
        db_health = await service.health_check()
        cache_stats = service.get_cache_stats()
        return HealthResponse(
            db_status=db_health.get("status", "unknown"),
            db_latency_ms=db_health.get("latency_ms"),
            cache_stats=cache_stats,
            server_time=None,
        )
    except Exception as e:
        return HealthResponse(
            ok=False,
            db_status="unhealthy",
            error=str(e),
            cache_stats=service.get_cache_stats(),
        )
