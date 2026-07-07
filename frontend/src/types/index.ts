export interface DashboardData {
  daily_trend: { data: any[]; count: number };
  top_actors: { data: any[]; count: number };
  geo_distribution: { data: any[]; count: number };
  event_types: { data: any[]; count: number };
  summary_stats: { data: any[]; count: number };
  _meta: { elapsed_ms: number; start_date: string; end_date: string };
}

export interface TimeSeriesPoint {
  period: string;
  event_count: number;
  conflict_pct?: number;
  cooperation_pct?: number;
  avg_goldstein?: number;
  avg_tone?: number;
}

export interface GeoPoint {
  lat: number;
  lng: number;
  intensity: number;
  avg_conflict?: number;
  sample_location?: string;
}

export interface EventItem {
  GlobalEventID: number;
  SQLDATE: string;
  Actor1Name?: string;
  Actor2Name?: string;
  EventCode?: string;
  GoldsteinScale?: number;
  AvgTone?: number;
  NumArticles?: number;
  ActionGeo_FullName?: string;
  ActionGeo_CountryCode?: string;
  ActionGeo_Lat?: number;
  ActionGeo_Long?: number;
  fingerprint?: string;
  headline?: string;
  summary?: string;
  event_type_label?: string;
  severity_score?: number;
  SOURCEURL?: string;
  key_actors?: string;
  location_name?: string;
  location_country?: string;
}

export interface GeoEventPoint {
  GlobalEventID: number;
  SQLDATE: string;
  Actor1Name?: string;
  Actor2Name?: string;
  EventCode?: string;
  GoldsteinScale?: number;
  AvgTone?: number;
  NumArticles?: number;
  ActionGeo_FullName?: string;
  ActionGeo_CountryCode?: string;
  lat: number;
  lng: number;
  fingerprint?: string;
  headline?: string;
  summary?: string;
  event_type_label?: string;
}

export interface FilterState {
  startDate: string;
  endDate: string;
  location: string;
  locationExact: string;
  actor: string;
  actorExact: string;
  eventType: string;
  keyword: string;
}

// Forecast types
export interface ForecastPoint {
  date: string;
  low: number;
  median: number;
  high: number;
}

export interface ThpForecastPoint {
  date: string;
  expected_events: number;
  low_events: number;
  median_events: number;
  high_events: number;
  risk_score?: number;
  risk_level?: string;
  hawkes_excitation?: number;
}

export interface ThpForecastResult {
  model: string;
  ok: boolean;
  error?: string;
  target?: Record<string, any>;
  summary?: Record<string, any>;
  forecast?: ThpForecastPoint[];
  checkpoint?: Record<string, any>;
  recent_history?: Array<{
    date: string;
    event_count: number;
    avg_goldstein?: number;
    avg_tone?: number;
  }>;
  attention_context?: Array<Record<string, any>>;
  _meta?: Record<string, any>;
}

// AI Analyze types
export interface LLMConfig {
  provider: string;
  api_key: string;
  model?: string;
  base_url?: string;
}

export interface QueryStep {
  type: string;
  params: Record<string, any>;
}

export interface QueryPlan {
  intent: string;
  thinking?: string;
  time_range?: { start: string; end: string };
  steps: QueryStep[];
  visualizations: string[];
  report_prompt?: string;
  notice?: string;
}

export interface ReportResult {
  summary: string;
  key_findings: string[];
}

// Enhanced Reporter v2 types
export interface NewsSourceItem {
  url: string;
  title?: string;
  content_snippet: string;
  fetch_status: string;
}

export interface TimelineEventItem {
  index: number;
  event_id?: number;
  date: string;
  title: string;
  description: string;
  actors: string[];
  location?: string;
  event_type?: string;
  significance_score: number;
  goldstein_scale?: number;
  num_articles?: number;
  avg_tone?: number;
  source_url?: string;
}

export interface StorylineTimelineData {
  events: TimelineEventItem[];
  period: Record<string, any>;
  key_milestones: Record<string, any>[];
  total_events: number;
}

export interface EntityEvolutionData {
  actors: Record<string, any>[];
  locations: Record<string, any>[];
  total_actors: number;
  total_locations: number;
}

export interface ThemeEvolutionData {
  themes_over_time: Record<string, any>[];
  emerging_themes: Record<string, any>[];
  declining_themes: Record<string, any>[];
  dominant_themes: Record<string, any>[];
  total_unique_themes: number;
}

export interface EventContextData {
  entity_evolution: EntityEvolutionData;
  theme_evolution: ThemeEvolutionData;
}

export interface NewsCoverageData {
  event_id?: number;
  headline?: string;
  sources: NewsSourceItem[];
  primary_content: string;
  source_count: number;
  has_content: boolean;
}

export interface GKGInsightData {
  cooccurring?: Record<string, any>;
  themes?: Record<string, any>;
  tone_timeline: Record<string, any>[];
}

export interface ActorActivityItem {
  date: string;
  total_events: number;
  total_articles: number;
  avg_goldstein?: number;
  avg_tone?: number;
  severe_conflict?: number;
  severe_cooperation?: number;
  top_event_code?: string;
  top_cameo_name?: string;
}

export interface StorylineEventItem {
  GlobalEventID: number;
  SQLDATE: string;
  Actor1Name?: string;
  Actor2Name?: string;
  EventCode?: string;
  cameo_name?: string;
  GoldsteinScale?: number;
  AvgTone?: number;
  NumArticles?: number;
  ActionGeo_FullName?: string;
  ActionGeo_CountryCode?: string;
  SOURCEURL?: string;
  headline?: string;
  summary?: string;
  event_type_label?: string;
  /** GKG theme overlap score with seed event (0-1) */
  theme_overlap?: number;
  /** Shared themes with seed event */
  shared_themes?: string[];
  /** Number of shared news sources with seed event (Mentions layer) */
  shared_sources?: number;
  /** Number of exact shared articles with seed event (Mentions layer v2) */
  shared_articles?: number;
  /** Sample URLs of shared articles */
  sample_urls?: string[];
  /** Composite relevance score (0-100) for storyline ranking */
  relevance_score?: number;
}

export interface EventStorylineData {
  seed?: StorylineEventItem;
  preceding: StorylineEventItem[];
  following: StorylineEventItem[];
  reactions: StorylineEventItem[];
}

export interface EnhancedReportResult {
  summary: string;
  key_findings: string[];
  event_context?: EventContextData;
  news_coverage?: NewsCoverageData;
  gkg_insights?: GKGInsightData;
  actor_activity?: ActorActivityItem[];
  event_storyline?: EventStorylineData;
  generated_at: string;
}

export interface Phase {
  name: string;
  status: "pending" | "running" | "completed";
  detail?: string;
  elapsed_ms?: number;
}

export interface AnalyzeResponse {
  ok: boolean;
  query: string;
  plan: QueryPlan;
  data: Record<string, { type: string; data: any; error?: string }>;
  report?: ReportResult;
  elapsed_ms?: number;
  phases?: Phase[];
  error?: string;
}

export interface QuadClassItem {
  quad_class: string;
  event_count: number;
  avg_goldstein?: number;
}

export interface ActorTypeItem {
  actor_type: string;
  event_count: number;
}

export interface HeadlineItem {
  GlobalEventID: number;
  SQLDATE: string;
  Actor1Name?: string;
  Actor2Name?: string;
  GoldsteinScale?: number;
  AvgTone?: number;
  NumArticles?: number;
  ActionGeo_FullName?: string;
  headline?: string;
  summary?: string;
  event_type_label?: string;
  severity_score?: number;
}

export interface SentimentSummary {
  avg_tone?: number;
  avg_goldstein?: number;
  conflict_count?: number;
  cooperation_count?: number;
  total_events?: number;
}

export interface InsightsData {
  quad_class: { data: QuadClassItem[] };
  actor_types: { data: ActorTypeItem[] };
  top_headlines: { data: HeadlineItem[] };
  sentiment: SentimentSummary;
}

export interface ApiResponse<T> {
  ok: boolean;
  error?: string;
  data?: T;
}
