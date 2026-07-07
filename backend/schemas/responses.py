"""
Pydantic schemas for API request/response validation.

All Dashboard endpoints return structured JSON for direct chart rendering.
"""

from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field
from datetime import date


# ============================================================================
# Base Response
# ============================================================================

class BaseResponse(BaseModel):
    ok: bool = True
    error: Optional[str] = None


# ============================================================================
# Dashboard Data
# ============================================================================

class DailyTrendPoint(BaseModel):
    sql_date: str = Field(..., alias="SQLDATE")
    event_count: int
    goldstein: Optional[float]
    conflict: int

    class Config:
        populate_by_name = True


class TopActorItem(BaseModel):
    actor: str = Field(..., alias="Actor1Name")
    event_count: int

    class Config:
        populate_by_name = True


class GeoDistributionItem(BaseModel):
    country_code: str = Field(..., alias="ActionGeo_CountryCode")
    event_count: int

    class Config:
        populate_by_name = True


class EventTypeItem(BaseModel):
    event_type: str
    event_count: int


class SummaryStats(BaseModel):
    total_events: int
    unique_actors: int
    avg_goldstein: Optional[float]
    avg_tone: Optional[float]
    total_articles: int


class DashboardData(BaseModel):
    daily_trend: Dict[str, Any]  # { data: [...], count, elapsed_ms }
    top_actors: Dict[str, Any]
    geo_distribution: Dict[str, Any]
    event_types: Dict[str, Any]
    summary_stats: Dict[str, Any]


class DashboardResponse(BaseResponse):
    data: Optional[DashboardData] = None
    start_date: str
    end_date: str
    elapsed_ms: Optional[float] = None


# ============================================================================
# Time Series Data
# ============================================================================

class TimeSeriesPoint(BaseModel):
    period: str
    event_count: int
    conflict_pct: Optional[float]
    cooperation_pct: Optional[float]
    avg_goldstein: Optional[float]
    std_goldstein: Optional[float]
    avg_tone: Optional[float]
    std_tone: Optional[float]
    top_actors_json: Optional[str] = None


class TimeSeriesResponse(BaseResponse):
    data: List[TimeSeriesPoint]
    granularity: str
    start_date: str
    end_date: str


# ============================================================================
# Geo Heatmap Data
# ============================================================================

class GeoPoint(BaseModel):
    lat: float
    lng: float
    intensity: int
    avg_conflict: Optional[float]
    sample_location: Optional[str]


class GeoHeatmapResponse(BaseResponse):
    data: List[GeoPoint]
    precision: int
    start_date: str
    end_date: str
    total_points: int


class GeoEventPoint(BaseModel):
    global_event_id: int = Field(..., alias="GlobalEventID")
    sql_date: str = Field(..., alias="SQLDATE")
    actor1_name: Optional[str] = Field(None, alias="Actor1Name")
    actor2_name: Optional[str] = Field(None, alias="Actor2Name")
    event_code: Optional[str] = Field(None, alias="EventCode")
    goldstein_scale: Optional[float] = Field(None, alias="GoldsteinScale")
    avg_tone: Optional[float] = Field(None, alias="AvgTone")
    num_articles: Optional[int] = Field(None, alias="NumArticles")
    action_geo_full_name: Optional[str] = Field(None, alias="ActionGeo_FullName")
    action_geo_country_code: Optional[str] = Field(None, alias="ActionGeo_CountryCode")
    lat: float
    lng: float
    fingerprint: Optional[str] = None
    headline: Optional[str] = None
    summary: Optional[str] = None
    event_type_label: Optional[str] = None

    class Config:
        populate_by_name = True


class GeoEventsResponse(BaseResponse):
    data: List[GeoEventPoint]
    start_date: str
    end_date: str
    total_points: int


class SuggestionsResponse(BaseResponse):
    items: List[str]
    query: str


# ============================================================================
# Event Search Data
# ============================================================================

class EventItem(BaseModel):
    global_event_id: int = Field(..., alias="GlobalEventID")
    sql_date: str = Field(..., alias="SQLDATE")
    actor1_name: Optional[str] = Field(None, alias="Actor1Name")
    actor2_name: Optional[str] = Field(None, alias="Actor2Name")
    event_code: Optional[str] = Field(None, alias="EventCode")
    goldstein_scale: Optional[float] = Field(None, alias="GoldsteinScale")
    avg_tone: Optional[float] = Field(None, alias="AvgTone")
    num_articles: Optional[int] = Field(None, alias="NumArticles")
    action_geo_full_name: Optional[str] = Field(None, alias="ActionGeo_FullName")
    action_geo_country_code: Optional[str] = Field(None, alias="ActionGeo_CountryCode")
    action_geo_lat: Optional[float] = Field(None, alias="ActionGeo_Lat")
    action_geo_long: Optional[float] = Field(None, alias="ActionGeo_Long")
    fingerprint: Optional[str] = None
    headline: Optional[str] = None
    summary: Optional[str] = None
    event_type_label: Optional[str] = None
    severity_score: Optional[float] = None

    class Config:
        populate_by_name = True


class EventSearchResponse(BaseResponse):
    data: List[EventItem]
    query: str
    total: int


# ============================================================================
# News / RAG Data
# ============================================================================

class NewsResult(BaseModel):
    event_id: str
    date: str
    source_url: str
    snippet: str


class NewsSearchResponse(BaseResponse):
    data: List[NewsResult]
    query: str


# ============================================================================
# Forecast Data
# ============================================================================

class ForecastPoint(BaseModel):
    date: str
    expected_events: float
    low: Optional[float] = None
    median: Optional[float] = None
    high: Optional[float] = None
    risk_score: Optional[float] = None
    risk_level: Optional[str] = None


class ForecastResponse(BaseResponse):
    data: Dict[str, Any]
    start_date: str
    end_date: str


# ============================================================================
# Health
# ============================================================================

class HealthResponse(BaseResponse):
    db_status: str
    db_latency_ms: Optional[float]
    cache_stats: Dict[str, Any]
    server_time: Optional[str]


# ============================================================================
# Insights Data
# ============================================================================

class QuadClassItem(BaseModel):
    quad_class: str
    event_count: int
    avg_goldstein: Optional[float]


class ActorTypeItem(BaseModel):
    actor_type: str
    event_count: int


class HeadlineItem(BaseModel):
    global_event_id: int
    sql_date: str
    actor1_name: Optional[str]
    actor2_name: Optional[str]
    goldstein_scale: Optional[float]
    avg_tone: Optional[float]
    num_articles: Optional[int]
    action_geo_full_name: Optional[str]
    headline: Optional[str]
    summary: Optional[str]
    event_type_label: Optional[str]
    severity_score: Optional[float]


class SentimentSummary(BaseModel):
    avg_tone: Optional[float]
    avg_goldstein: Optional[float]
    conflict_count: Optional[int]
    cooperation_count: Optional[int]
    total_events: Optional[int]


class InsightsData(BaseModel):
    quad_class: Dict[str, Any]
    actor_types: Dict[str, Any]
    top_headlines: Dict[str, Any]
    sentiment: SentimentSummary


class InsightsResponse(BaseResponse):
    data: InsightsData
    start_date: str
    end_date: str


class TopEventsResponse(BaseResponse):
    data: List[EventItem]
    start_date: str
    end_date: str
    total: int


# ============================================================================
# Agent Chat
# ============================================================================

class LLMConfig(BaseModel):
    """User-provided LLM configuration for custom model selection."""
    provider: str = Field(default="kimi", description="kimi, openai, claude, moonshot")
    api_key: str = Field(..., description="API key for the selected provider")
    model: Optional[str] = Field(None, description="Model name, e.g. gpt-4o, claude-3-5-sonnet-20241022")
    base_url: Optional[str] = Field(None, description="Custom base URL for the API")


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    history: List[Dict[str, str]] = Field(default_factory=list)
    session_id: Optional[str] = None
    llm_config: Optional[LLMConfig] = Field(None, description="Custom LLM configuration. If not provided, uses server default.")


class ThinkingStep(BaseModel):
    type: str
    content: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


class ChatResponse(BaseResponse):
    reply: str
    session_id: str
    thinking_steps: List[ThinkingStep] = Field(default_factory=list)
    tools_used: List[str] = Field(default_factory=list)


class ToolInfo(BaseModel):
    name: str
    description: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None


class ToolsResponse(BaseResponse):
    tools: List[ToolInfo]


# ============================================================================
# Help / Documentation
# ============================================================================

class HelpItem(BaseModel):
    command: str
    description: str
    example: Optional[str] = None


class HelpsResponse(BaseResponse):
    helps: List[HelpItem]
    system_prompt_summary: str = "GDELT Analyst — conversational intelligence for geopolitical events"
    tips: List[str] = Field(default_factory=list)


# ============================================================================
# AI Analyze / Visualization
# ============================================================================

class AnalyzeRequest(BaseModel):
    """Natural language query for AI-driven data exploration."""
    query: str = Field(..., min_length=1, max_length=4000, description="Natural language data request")
    llm_config: Optional[LLMConfig] = Field(None, description="Custom LLM configuration for Planner and Report")


class QueryStepOutput(BaseModel):
    type: str
    params: Dict[str, Any]


class QueryPlanOutput(BaseModel):
    intent: str
    thinking: Optional[str] = None
    time_range: Optional[Dict[str, str]] = None
    steps: List[QueryStepOutput]
    visualizations: List[str]
    report_prompt: Optional[str] = None
    notice: Optional[str] = None


class ReportOutput(BaseResponse):
    summary: str = ""
    key_findings: List[str] = Field(default_factory=list)


class PhaseOutput(BaseModel):
    name: str
    status: str = "pending"  # pending | running | completed
    detail: Optional[str] = None  # Human-readable description of what happened
    elapsed_ms: Optional[float] = None


class AnalyzeResponse(BaseResponse):
    query: str
    plan: QueryPlanOutput
    data: Dict[str, Any]
    report: Optional[ReportOutput] = None
    elapsed_ms: Optional[float] = None
    phases: List[PhaseOutput] = Field(default_factory=list)


class ReportRequest(BaseModel):
    """Request to generate an AI report from existing query results."""
    data: Dict[str, Any] = Field(..., description="Query results from /analyze")
    prompt: Optional[str] = Field(None, description="Optional custom prompt for the report")


# ============================================================================
# Enhanced Event Report (Reporter v2)
# ============================================================================

class NewsSourceItem(BaseModel):
    url: str
    title: Optional[str] = None
    content_snippet: str = ""
    fetch_status: str = ""  # success | failed | cached | chroma_fallback


class TimelineEventItem(BaseModel):
    index: int
    event_id: Optional[int] = None
    date: str
    title: str
    description: str
    actors: List[str] = Field(default_factory=list)
    location: Optional[str] = None
    event_type: Optional[str] = None
    significance_score: float = 0.0
    goldstein_scale: Optional[float] = None
    num_articles: Optional[int] = None
    avg_tone: Optional[float] = None


class StorylineTimelineData(BaseModel):
    events: List[TimelineEventItem] = Field(default_factory=list)
    period: Dict[str, Any] = Field(default_factory=dict)
    key_milestones: List[Dict[str, Any]] = Field(default_factory=list)
    total_events: int = 0


class EntityEvolutionData(BaseModel):
    actors: List[Dict[str, Any]] = Field(default_factory=list)
    locations: List[Dict[str, Any]] = Field(default_factory=list)
    total_actors: int = 0
    total_locations: int = 0


class ThemeEvolutionData(BaseModel):
    themes_over_time: List[Dict[str, Any]] = Field(default_factory=list)
    emerging_themes: List[Dict[str, Any]] = Field(default_factory=list)
    declining_themes: List[Dict[str, Any]] = Field(default_factory=list)
    dominant_themes: List[Dict[str, Any]] = Field(default_factory=list)
    total_unique_themes: int = 0


class StorylineData(BaseModel):
    timeline: StorylineTimelineData = Field(default_factory=StorylineTimelineData)
    entity_evolution: EntityEvolutionData = Field(default_factory=EntityEvolutionData)
    theme_evolution: ThemeEvolutionData = Field(default_factory=ThemeEvolutionData)
    narrative_arc: str = ""


class NewsCoverageData(BaseModel):
    event_id: Optional[int] = None
    headline: Optional[str] = None
    sources: List[NewsSourceItem] = Field(default_factory=list)
    primary_content: str = ""
    source_count: int = 0
    has_content: bool = False


class GKGInsightData(BaseModel):
    cooccurring: Optional[Dict[str, Any]] = None
    themes: Optional[Dict[str, Any]] = None
    tone_timeline: List[Dict[str, Any]] = Field(default_factory=list)


class ActorActivityItem(BaseModel):
    date: str
    total_events: int
    total_articles: int
    avg_goldstein: Optional[float] = None
    avg_tone: Optional[float] = None
    severe_conflict: int = 0
    severe_cooperation: int = 0
    top_event_code: Optional[str] = None
    top_cameo_name: Optional[str] = None


class StorylineEventItem(BaseModel):
    GlobalEventID: int
    SQLDATE: str
    Actor1Name: Optional[str] = None
    Actor2Name: Optional[str] = None
    EventCode: Optional[str] = None
    cameo_name: Optional[str] = None
    GoldsteinScale: Optional[float] = None
    AvgTone: Optional[float] = None
    NumArticles: Optional[int] = None
    ActionGeo_FullName: Optional[str] = None
    ActionGeo_CountryCode: Optional[str] = None
    SOURCEURL: Optional[str] = None
    headline: Optional[str] = None
    summary: Optional[str] = None
    event_type_label: Optional[str] = None


class EventStorylineData(BaseModel):
    seed: Optional[StorylineEventItem] = None
    preceding: List[StorylineEventItem] = Field(default_factory=list)
    following: List[StorylineEventItem] = Field(default_factory=list)
    reactions: List[StorylineEventItem] = Field(default_factory=list)


class EnhancedReportOutput(BaseModel):
    summary: str
    key_findings: List[str] = Field(default_factory=list)
    event_context: Optional[StorylineData] = None
    news_coverage: Optional[NewsCoverageData] = None
    gkg_insights: Optional[GKGInsightData] = None
    actor_activity: List[ActorActivityItem] = Field(default_factory=list)
    event_storyline: Optional[EventStorylineData] = None
    generated_at: str = ""


class ReportConfig(BaseModel):
    """User-configurable report generation settings."""
    include_storyline: bool = True
    include_news: bool = False
    include_gkg: bool = True
    gkg_tone_days: int = Field(14, ge=3, le=14, description="Days of GKG tone timeline (3-14)")
    gkg_themes_days: int = Field(1, ge=1, le=7, description="Days of GKG themes query (1-7)")
    gkg_cooccurring_limit: int = Field(30, ge=10, le=100, description="GKG co-occurring entities limit")
    storyline_days_before: int = Field(7, ge=1, le=30, description="Storyline: days to look back (1-30)")
    storyline_days_after: int = Field(7, ge=1, le=30, description="Storyline: days to look forward (1-30)")
    max_report_length: int = Field(12000, ge=4000, le=16000, description="Max report chars (4000-16000)")
    use_gkg_storyline_filter: bool = Field(False, description="Enable GKG theme overlap filtering for storyline precision (~$0.09)")
    use_mentions_storyline_filter: bool = Field(False, description="Enable Mentions shared-source detection for storyline precision (~$0.005)")


class EventReportRequest(BaseModel):
    """Request to generate a comprehensive event report."""
    data: Dict[str, Any] = Field(..., description="Query results from /analyze")
    prompt: Optional[str] = Field(None, description="Optional custom prompt")
    include_storyline: bool = True
    include_news: bool = False
    include_gkg: bool = True
    llm_config: Optional[LLMConfig] = None
    config: Optional[ReportConfig] = Field(None, description="Advanced report configuration")


class EventReportResponse(BaseModel):
    ok: bool = True
    error: Optional[str] = None
    report: Optional[EnhancedReportOutput] = None
    elapsed_ms: Optional[float] = None


class StorylineRequest(BaseModel):
    event_id: Optional[int] = None
    fingerprint: Optional[str] = None
    date_range: Optional[Dict[str, str]] = None


class StorylineResponse(BaseModel):
    ok: bool = True
    error: Optional[str] = None
    storyline: Optional[StorylineData] = None
    elapsed_ms: Optional[float] = None
    llm_config: Optional[LLMConfig] = Field(None, description="Custom LLM configuration")
