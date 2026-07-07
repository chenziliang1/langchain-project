const API_BASE = '';

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${url}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(err.error || `HTTP ${res.status}`);
  }
  return res.json();
}

export const api = {
  // Dashboard (direct data endpoints)
  getDashboard: (start: string, end: string) =>
    fetchJson<any>(`/api/v1/data/dashboard?start=${start}&end=${end}`),

  getTimeSeries: (start: string, end: string, granularity = 'day') =>
    fetchJson<any>(`/api/v1/data/timeseries?start=${start}&end=${end}&granularity=${granularity}`),

  getGeoHeatmap: (start: string, end: string, precision = 2) =>
    fetchJson<any>(`/api/v1/data/geo?start=${start}&end=${end}&precision=${precision}`),

  searchEvents: (query?: string, start?: string, end?: string, location?: string, locationExact?: string, eventType?: string, actor?: string, actorExact?: string, limit = 20) => {
    const params = new URLSearchParams();
    if (query) params.set('query', query);
    if (start) params.set('start', start);
    if (end) params.set('end', end);
    if (location) params.set('location_hint', location);
    if (locationExact) params.set('location_exact', locationExact);
    if (eventType && eventType !== 'any') params.set('event_type', eventType);
    if (actor) params.set('actor', actor);
    if (actorExact) params.set('actor_exact', actorExact);
    params.set('limit', String(limit));
    return fetchJson<any>(`/api/v1/data/events?${params.toString()}`);
  },

  getGeoEvents: (start: string, end: string, location?: string, locationExact?: string, eventType?: string, actor?: string, actorExact?: string, limit = 100) => {
    const params = new URLSearchParams();
    params.set('start', start);
    params.set('end', end);
    if (location) params.set('location_hint', location);
    if (locationExact) params.set('location_exact', locationExact);
    if (eventType && eventType !== 'any') params.set('event_type', eventType);
    if (actor) params.set('actor', actor);
    if (actorExact) params.set('actor_exact', actorExact);
    params.set('limit', String(limit));
    return fetchJson<any>(`/api/v1/data/geo/events?${params.toString()}`);
  },

  suggestActors: (q: string, limit = 10) =>
    fetchJson<any>(`/api/v1/data/suggestions/actors?q=${encodeURIComponent(q)}&limit=${limit}`),

  suggestLocations: (q: string, limit = 10) =>
    fetchJson<any>(`/api/v1/data/suggestions/locations?q=${encodeURIComponent(q)}&limit=${limit}`),

  health: () => fetchJson<any>('/api/v1/data/health'),

  // Forecast (THP)
  getForecast: (
    start: string,
    end: string,
    params: { region?: string; actor?: string; event_type?: string; forecast_days?: number } = {}
  ) => {
    const qs = new URLSearchParams({
      start,
      end,
      event_type: params.event_type || 'all',
      forecast_days: String(params.forecast_days || 7),
    });
    if (params.region) qs.set('region', params.region);
    if (params.actor) qs.set('actor', params.actor);
    return fetchJson<any>(`/api/v1/data/forecast?${qs.toString()}`);
  },

  // AI Analyze (Planner + Executor)
  analyze: (query: string, llmConfig?: any) =>
    fetchJson<any>('/api/v1/analyze', {
      method: 'POST',
      body: JSON.stringify({ query, llm_config: llmConfig }),
    }),

  // AI Report (delayed load)
  generateReport: (data: any, prompt?: string, llmConfig?: any) =>
    fetchJson<any>('/api/v1/analyze/report', {
      method: 'POST',
      body: JSON.stringify({ data, prompt, llm_config: llmConfig }),
    }),

  // Dashboard insights
  getInsights: (start: string, end: string) =>
    fetchJson<any>(`/api/v1/data/insights?start=${start}&end=${end}`),

  getTopEvents: (start: string, end: string, limit = 5) =>
    fetchJson<any>(`/api/v1/data/top-events?start=${start}&end=${end}&limit=${limit}`),

  // Enhanced Event Report (Reporter v2)
  generateEventReport: (data: any, prompt?: string, includeStoryline = true, includeNews = false, includeGKG = true, llmConfig?: any, config?: any) =>
    fetchJson<any>('/api/v1/analyze/event-report', {
      method: 'POST',
      body: JSON.stringify({
        data,
        prompt,
        include_storyline: includeStoryline,
        include_news: includeNews,
        include_gkg: includeGKG,
        llm_config: llmConfig,
        config,
      }),
    }),

  getStoryline: (eventId?: number, fingerprint?: string, dateRange?: { start: string; end: string }) =>
    fetchJson<any>('/api/v1/analyze/storyline', {
      method: 'POST',
      body: JSON.stringify({ event_id: eventId, fingerprint, date_range: dateRange }),
    }),
};
