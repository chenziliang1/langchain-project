import { useState, useEffect } from 'react';
import { Search, Loader2, Zap, CheckCircle, FileText, MessageSquareWarning, Calendar, MapPin, Users, Brain, Terminal, Sparkles, BookOpen, Database, ToggleLeft, ToggleRight, Settings, SlidersHorizontal, X } from 'lucide-react';
import { api } from '../api/client';
import type { AnalyzeResponse, ReportResult, EventItem, EnhancedReportResult } from '../types';
import EventDetailCard from './EventDetailCard';
import SimilarEventCards from './SimilarEventCards';
import ReportPanel from './ReportPanel';
import EventReportPanel from './EventReportPanel';

// Daily brief stat card
function DailyBriefStat({ label, value, color }: { label: string; value: number | string | null; color: string }) {
  if (value === null || value === undefined) return null;
  const displayValue = typeof value === 'number' ? value.toLocaleString() : String(value);
  return (
    <div style={{ textAlign: 'center', padding: '10px 8px', background: '#f8fafc', borderRadius: 8 }}>
      <div style={{ fontSize: 11, color: '#888', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 20, fontWeight: 700, color }}>{displayValue}</div>
    </div>
  );
}

// Compact event card for search results
function CompactEventCard({ event, onClick }: { event: EventItem; onClick: () => void }) {
  const headline = event.headline || `${event.Actor1Name || 'Unknown'} vs ${event.Actor2Name || 'Unknown'}`;
  return (
    <div
      onClick={onClick}
      style={{
        background: '#f8fafc',
        border: '1px solid #e2e8f0',
        borderRadius: 10,
        padding: '12px 16px',
        cursor: 'pointer',
        transition: 'all 0.15s ease',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = '#cbd5e1';
        e.currentTarget.style.background = '#f1f5f9';
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = '#e2e8f0';
        e.currentTarget.style.background = '#f8fafc';
      }}
    >
      <div style={{ fontSize: 14, fontWeight: 600, color: '#1a1a1a', marginBottom: 6, lineHeight: 1.4 }}>
        {headline}
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px 12px', alignItems: 'center' }}>
        {event.SQLDATE && (
          <span style={{ display: 'flex', alignItems: 'center', gap: 3, fontSize: 12, color: '#6b7280' }}>
            <Calendar size={11} />
            {event.SQLDATE}
          </span>
        )}
        {event.ActionGeo_FullName && (
          <span style={{ display: 'flex', alignItems: 'center', gap: 3, fontSize: 12, color: '#6b7280' }}>
            <MapPin size={11} />
            {event.ActionGeo_FullName}
          </span>
        )}
        {(event.Actor1Name || event.Actor2Name) && (
          <span style={{ display: 'flex', alignItems: 'center', gap: 3, fontSize: 12, color: '#6b7280' }}>
            <Users size={11} />
            {event.Actor1Name || '?'}
            {event.Actor2Name ? ` vs ${event.Actor2Name}` : ''}
          </span>
        )}
        {event.NumArticles !== undefined && (
          <span style={{ fontSize: 11, color: '#f97316', fontWeight: 600 }}>
            {event.NumArticles} articles
          </span>
        )}
      </div>
    </div>
  );
}

export default function ExplorePanel() {
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AnalyzeResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Typing animation for thinking
  const [thinkingText, setThinkingText] = useState('');
  const [thinkingDone, setThinkingDone] = useState(false);
  const [showData, setShowData] = useState(false);

  // Loading phase animation
  const [loadingPhaseIndex, setLoadingPhaseIndex] = useState(0);
  const loadingPhases = [
    "Analyzing your question...",
    "Routing intent via local AI...",
    "Generating query plan...",
    "Executing database queries...",
    "Processing results...",
  ];

  // Report delayed load state
  const [report, setReport] = useState<ReportResult | null>(null);
  const [reportLoading, setReportLoading] = useState(false);

  // Enhanced report state (Reporter v2)
  const [enhancedReport, setEnhancedReport] = useState<EnhancedReportResult | null>(null);
  const [enhancedReportLoading, setEnhancedReportLoading] = useState(false);
  
  // Report config panel
  const [showConfig, setShowConfig] = useState(false);
  
  // User-configurable report settings (persisted in session)
  const [reportConfig, setReportConfig] = useState({
    useGKG: true,
    useStoryline: true,
    gkgToneDays: 14,
    gkgThemesDays: 1,
    storylineDaysBefore: 7,
    storylineDaysAfter: 7,
    maxReportLength: 12000,
    useGKGStorylineFilter: false,
    useMentionsStorylineFilter: false,
  });

  // Loading phase cycling
  useEffect(() => {
    if (!loading) {
      setLoadingPhaseIndex(0);
      return;
    }
    setLoadingPhaseIndex(0);
    const interval = setInterval(() => {
      setLoadingPhaseIndex(prev => {
        if (prev >= loadingPhases.length - 1) return prev;
        return prev + 1;
      });
    }, 500);
    return () => clearInterval(interval);
  }, [loading]);

  // Typing effect for AI thinking
  useEffect(() => {
    if (result?.plan?.thinking) {
      const fullText = result.plan.thinking;
      setThinkingText('');
      setThinkingDone(false);
      setShowData(false);
      let i = 0;
      const interval = setInterval(() => {
        i++;
        setThinkingText(fullText.slice(0, i));
        if (i >= fullText.length) {
          clearInterval(interval);
          setThinkingDone(true);
          setTimeout(() => setShowData(true), 400);
        }
      }, 12);
      return () => clearInterval(interval);
    }
  }, [result]);

  const handleSubmit = async () => {
    if (!query.trim() || loading) return;
    setLoading(true);
    setError(null);
    setResult(null);
    setReport(null);
    setEnhancedReport(null);

    try {
      const res = await api.analyze(query.trim());
      if (res.ok === false) {
        setError(res.error || 'Analysis failed');
      } else {
        setResult(res);
      }
    } catch (err: any) {
      setError(err.message || 'Network error');
    } finally {
      setLoading(false);
    }
  };

  const loadReport = async (data: any, prompt: string) => {
    setReportLoading(true);
    try {
      const res = await api.generateReport(data, prompt);
      setReport(res);
    } catch (err: any) {
      console.error('Report load failed:', err);
    } finally {
      setReportLoading(false);
    }
  };

  const loadEnhancedReport = async (data: any, prompt?: string) => {
    setEnhancedReportLoading(true);
    try {
      const config = {
        gkg_tone_days: reportConfig.gkgToneDays,
        gkg_themes_days: reportConfig.gkgThemesDays,
        storyline_days_before: reportConfig.storylineDaysBefore,
        storyline_days_after: reportConfig.storylineDaysAfter,
        max_report_length: reportConfig.maxReportLength,
        use_gkg_storyline_filter: reportConfig.useGKGStorylineFilter,
        use_mentions_storyline_filter: reportConfig.useMentionsStorylineFilter,
      };
      const res = await api.generateEventReport(
        data, prompt,
        reportConfig.useStoryline,
        false,
        reportConfig.useGKG,
        undefined,
        config,
      );
      if (res.report) {
        setEnhancedReport(res.report);
      }
    } catch (err: any) {
      console.error('Enhanced report load failed:', err);
    } finally {
      setEnhancedReportLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  // Extract data from result by type
  const getDataByType = (type: string) => {
    if (!result) return null;
    for (const key of Object.keys(result.data)) {
      const item = result.data[key];
      if (item.type === type && !item.error) return item.data;
    }
    return null;
  };

  const vizes = result?.plan?.visualizations || [];
  const isOffTopic = result?.plan?.intent === 'off_topic';

  // Get event detail data
  const eventDetail = getDataByType('event_detail');
  const similarEvents = getDataByType('similar_events');
  const searchEvents = getDataByType('events') || getDataByType('top_events') || getDataByType('hot_events');
  const dailyBrief = getDataByType('daily_brief');

  // When user clicks a search result or similar event, populate the input box
  // but do NOT auto-run — user must click Analyze.
  const handleEventClick = (evt: EventItem) => {
    const gid = evt.GlobalEventID;
    if (!gid) return;
    const date = evt.SQLDATE || '2024-01-01';
    const formattedDate = date.includes('-') ? date : `${date.slice(0, 4)}-${date.slice(4, 6)}-${date.slice(6, 8)}`;
    const evtQuery = `EVT-${formattedDate}-${gid}`;
    setQuery(evtQuery);
    // Clear previous reports so they don't show for the new event
    setReport(null);
    setEnhancedReport(null);
  };

  return (
    <div style={{ padding: 16 }}>
      <div style={{ marginBottom: 16 }}>
        <h2 style={{ fontSize: 20, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 10 }}>
          <Sparkles size={22} color="#2563eb" />
          AI Explore
        </h2>
        <p style={{ fontSize: 13, color: '#6b7280', marginTop: 4 }}>
          Search for specific events and incidents. Use the Dashboard tab for trends, stats, and maps.
        </p>
      </div>

      {/* Search Input */}
      <div className="search-box">
        <Search size={20} color="#888" style={{ flexShrink: 0 }} />
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Search events by location, type, date, or event ID. For data analysis &amp; trends, use the Dashboard tab."
          className="search-input"
        />
        <button
          onClick={handleSubmit}
          disabled={loading || !query.trim()}
          className="search-btn"
        >
          {loading ? <Loader2 size={18} className="spinning" /> : <Zap size={18} />}
          {loading ? 'Analyzing...' : 'Analyze'}
        </button>
      </div>

      {/* Loading State */}
      {loading && (
        <div className="loading-plan" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: 10 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Loader2 size={18} className="spinning" />
            <span style={{ fontWeight: 600, fontSize: 14 }}>AI Pipeline</span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, paddingLeft: 4 }}>
            {loadingPhases.map((phase, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, opacity: i <= loadingPhaseIndex ? 1 : 0.4, transition: 'opacity 0.3s ease' }}>
                {i < loadingPhaseIndex ? (
                  <CheckCircle size={14} color="#10b981" />
                ) : i === loadingPhaseIndex ? (
                  <Loader2 size={14} className="spinning" color="#0284c7" />
                ) : (
                  <div style={{ width: 14, height: 14, borderRadius: '50%', border: '2px solid #cbd5e1', flexShrink: 0 }} />
                )}
                <span style={{ fontSize: 13, color: i <= loadingPhaseIndex ? '#0f172a' : '#94a3b8', transition: 'color 0.3s ease' }}>{phase}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Error */}
      {error && <div className="error-banner">{error}</div>}

      {/* Off-topic */}
      {isOffTopic && (
        <div style={{ padding: 24, background: '#f8fafc', borderRadius: 12, textAlign: 'center' }}>
          <MessageSquareWarning size={40} color="#64748b" style={{ marginBottom: 12 }} />
          <h3 style={{ color: '#475569', marginBottom: 8 }}>I&apos;m a GDELT event analyst</h3>
          <p style={{ color: '#64748b', fontSize: 14 }}>
            Ask me about specific geopolitical events, incidents, or search by event ID.
            <br />
            For example: &quot;What happened with US-20240101-VIR-MASS-1149261787?&quot; or &quot;Show me protests in Washington DC.&quot;
          </p>
        </div>
      )}

      {/* Results */}
      {result && !isOffTopic && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* AI Decision */}
          {result.plan.thinking && (
            <div
              style={{
                background: '#f0f9ff',
                border: '1px solid #bae6fd',
                borderRadius: 12,
                padding: '14px 18px',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                <Brain size={16} color="#0284c7" />
                <span style={{ fontSize: 13, fontWeight: 600, color: '#0369a1' }}>
                  AI Decision
                </span>
                <span style={{ fontSize: 11, color: '#7dd3fc', marginLeft: 'auto' }}>
                  {result.elapsed_ms}ms
                </span>
              </div>

              {/* Phases */}
              {result.phases && result.phases.length > 0 && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 12 }}>
                  {result.phases.map((phase, i) => (
                    <div key={i} style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <CheckCircle size={14} color="#10b981" />
                        <span style={{ fontSize: 13, color: '#0f172a', flex: 1, fontWeight: 500 }}>{phase.name}</span>
                        {phase.elapsed_ms !== undefined && phase.elapsed_ms > 0 && (
                          <span style={{ fontSize: 11, color: '#64748b', fontFamily: 'monospace' }}>
                            {phase.elapsed_ms}ms
                          </span>
                        )}
                      </div>
                      {phase.detail && (
                        <div style={{ paddingLeft: 22, fontSize: 12, color: '#64748b', lineHeight: 1.4 }}>
                          {phase.detail}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}

              {/* Thinking text */}
              <p style={{ fontSize: 13, color: '#0c4a6e', lineHeight: 1.6, margin: 0, minHeight: 20, opacity: 0.85 }}>
                {thinkingText}
                {!thinkingDone && <span style={{ display: 'inline-block', width: 2, height: 14, background: '#0284c7', marginLeft: 2, verticalAlign: 'middle', animation: 'blink 1s infinite' }} />}
              </p>

              {/* Tool execution status */}
              {thinkingDone && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 10, paddingTop: 10, borderTop: '1px solid #bae6fd' }}>
                  <Terminal size={13} color="#0284c7" />
                  <span style={{ fontSize: 12, color: '#0369a1', fontFamily: 'monospace' }}>
                    {result.plan.steps.map(s => s.type).join(' → ')}
                  </span>
                </div>
              )}
            </div>
          )}

          {/* Data loading state */}
          {thinkingDone && !showData && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '16px 20px', background: '#fafafa', borderRadius: 10, border: '1px dashed #e2e8f0' }}>
              <Loader2 size={16} className="spinning" color="#888" />
              <span style={{ fontSize: 14, color: '#888' }}>
                Executing {result.plan.steps.length} tool{result.plan.steps.length > 1 ? 's' : ''}...
              </span>
            </div>
          )}

          {/* Data content — fades in after thinking completes */}
          {showData && (
            <>
              {/* Report Buttons */}
              {vizes.includes('report') && result?.plan?.report_prompt && !report && !reportLoading && !enhancedReport && !enhancedReportLoading && (
                <div style={{ marginBottom: 16 }}>
                  <div style={{ display: 'flex', gap: 10, marginBottom: 10, alignItems: 'center' }}>
                    <button
                      onClick={() => loadReport(result.data, result.plan.report_prompt!)}
                      style={{
                        padding: '8px 16px',
                        borderRadius: 6,
                        border: '1px solid #2563eb',
                        background: '#fff',
                        color: '#2563eb',
                        fontSize: 13,
                        fontWeight: 500,
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        gap: 6,
                      }}
                    >
                      <FileText size={14} />
                      Quick Report
                    </button>
                    <button
                      onClick={() => loadEnhancedReport(result.data, result.plan.report_prompt!)}
                      style={{
                        padding: '8px 16px',
                        borderRadius: 6,
                        border: '1px solid #7c3aed',
                        background: '#fff',
                        color: '#7c3aed',
                        fontSize: 13,
                        fontWeight: 500,
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        gap: 6,
                      }}
                    >
                      <BookOpen size={14} />
                      Deep Dive Report
                    </button>
                    <button
                      onClick={() => setShowConfig(!showConfig)}
                      style={{
                        padding: '8px 12px',
                        borderRadius: 6,
                        border: '1px solid #e2e8f0',
                        background: showConfig ? '#f1f5f9' : '#fff',
                        color: '#64748b',
                        fontSize: 13,
                        fontWeight: 500,
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        gap: 6,
                        marginLeft: 'auto',
                      }}
                      title="Configure report settings"
                    >
                      <SlidersHorizontal size={14} />
                      Settings
                    </button>
                  </div>
                  
                  {/* Config Panel */}
                  {showConfig && (
                    <div style={{
                      padding: 16,
                      background: '#fafafa',
                      borderRadius: 8,
                      border: '1px solid #e2e8f0',
                      fontSize: 13,
                    }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                        <Settings size={14} color="#64748b" />
                        <span style={{ fontWeight: 600, color: '#374151' }}>Report Configuration</span>
                        <button
                          onClick={() => setShowConfig(false)}
                          style={{ marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer', padding: 2 }}
                        >
                          <X size={14} color="#9ca3af" />
                        </button>
                      </div>
                      
                      {/* Toggles */}
                      <div style={{ display: 'grid', gap: 10, marginBottom: 16 }}>
                        <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer' }}>
                          <input
                            type="checkbox"
                            checked={reportConfig.useGKG}
                            onChange={(e) => setReportConfig({ ...reportConfig, useGKG: e.target.checked })}
                          />
                          <span>
                            <span style={{ fontWeight: 500 }}>GKG BigQuery</span>
                            <span style={{ color: '#9ca3af', marginLeft: 6, fontSize: 12 }}>
                              {reportConfig.useGKG ? '~$0.005-0.01 per report' : 'disabled — saving money'}
                            </span>
                          </span>
                        </label>
                        <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer' }}>
                          <input
                            type="checkbox"
                            checked={reportConfig.useStoryline}
                            onChange={(e) => setReportConfig({ ...reportConfig, useStoryline: e.target.checked })}
                          />
                          <span>
                            <span style={{ fontWeight: 500 }}>Storyline</span>
                            <span style={{ color: '#9ca3af', marginLeft: 6, fontSize: 12 }}>
                              Timeline + entity evolution
                            </span>
                          </span>
                        </label>
                      </div>

                      {/* Storyline Precision Layers */}
                      {reportConfig.useStoryline && (
                        <div style={{ marginBottom: 16, padding: '10px 12px', background: '#f8fafc', borderRadius: 8, border: '1px solid #e2e8f0' }}>
                          <div style={{ fontSize: 12, fontWeight: 600, color: '#4b5563', marginBottom: 8 }}>
                            Storyline Precision (BigQuery)
                          </div>
                          <div style={{ display: 'grid', gap: 8 }}>
                            <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer' }}>
                              <input
                                type="checkbox"
                                checked={reportConfig.useGKGStorylineFilter}
                                onChange={(e) => setReportConfig({ ...reportConfig, useGKGStorylineFilter: e.target.checked })}
                              />
                              <span>
                                <span style={{ fontWeight: 500, fontSize: 13 }}>GKG Theme Overlap</span>
                                <span style={{ color: '#9ca3af', marginLeft: 6, fontSize: 12 }}>
                                  {reportConfig.useGKGStorylineFilter ? '~$0.09 per report' : 'off'}
                                </span>
                              </span>
                            </label>
                            <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer' }}>
                              <input
                                type="checkbox"
                                checked={reportConfig.useMentionsStorylineFilter}
                                onChange={(e) => setReportConfig({ ...reportConfig, useMentionsStorylineFilter: e.target.checked })}
                              />
                              <span>
                                <span style={{ fontWeight: 500, fontSize: 13 }}>Shared News Sources</span>
                                <span style={{ color: '#9ca3af', marginLeft: 6, fontSize: 12 }}>
                                  {reportConfig.useMentionsStorylineFilter ? '~$0.005 per report' : 'off'}
                                </span>
                              </span>
                            </label>
                          </div>
                        </div>
                      )}
                      
                      {/* Sliders */}
                      {reportConfig.useGKG && (
                        <div style={{ display: 'grid', gap: 12 }}>
                          <div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                              <span style={{ color: '#4b5563' }}>Tone Timeline Window</span>
                              <span style={{ fontWeight: 600, color: '#7c3aed' }}>{reportConfig.gkgToneDays} days</span>
                            </div>
                            <input
                              type="range"
                              min={3}
                              max={14}
                              value={reportConfig.gkgToneDays}
                              onChange={(e) => setReportConfig({ ...reportConfig, gkgToneDays: parseInt(e.target.value) })}
                              style={{ width: '100%' }}
                            />
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: '#9ca3af', marginTop: 2 }}>
                              <span>3 days</span>
                              <span>14 days (max)</span>
                            </div>
                          </div>
                          
                          <div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                              <span style={{ color: '#4b5563' }}>Themes Query Days</span>
                              <span style={{ fontWeight: 600, color: '#7c3aed' }}>{reportConfig.gkgThemesDays} day{reportConfig.gkgThemesDays > 1 ? 's' : ''}</span>
                            </div>
                            <input
                              type="range"
                              min={1}
                              max={7}
                              value={reportConfig.gkgThemesDays}
                              onChange={(e) => setReportConfig({ ...reportConfig, gkgThemesDays: parseInt(e.target.value) })}
                              style={{ width: '100%' }}
                            />
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: '#9ca3af', marginTop: 2 }}>
                              <span>1 day</span>
                              <span>7 days</span>
                            </div>
                          </div>
                          
                          <div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                              <span style={{ color: '#4b5563' }}>Storyline Look Back</span>
                              <span style={{ fontWeight: 600, color: '#dc2626' }}>{reportConfig.storylineDaysBefore} days</span>
                            </div>
                            <input
                              type="range"
                              min={1}
                              max={30}
                              value={reportConfig.storylineDaysBefore}
                              onChange={(e) => setReportConfig({ ...reportConfig, storylineDaysBefore: parseInt(e.target.value) })}
                              style={{ width: '100%' }}
                            />
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: '#9ca3af', marginTop: 2 }}>
                              <span>1 day</span>
                              <span>30 days</span>
                            </div>
                          </div>

                          <div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                              <span style={{ color: '#4b5563' }}>Storyline Look Forward</span>
                              <span style={{ fontWeight: 600, color: '#dc2626' }}>{reportConfig.storylineDaysAfter} days</span>
                            </div>
                            <input
                              type="range"
                              min={1}
                              max={30}
                              value={reportConfig.storylineDaysAfter}
                              onChange={(e) => setReportConfig({ ...reportConfig, storylineDaysAfter: parseInt(e.target.value) })}
                              style={{ width: '100%' }}
                            />
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: '#9ca3af', marginTop: 2 }}>
                              <span>1 day</span>
                              <span>30 days</span>
                            </div>
                          </div>

                          <div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                              <span style={{ color: '#4b5563' }}>Report Length</span>
                              <span style={{ fontWeight: 600, color: '#7c3aed' }}>{(reportConfig.maxReportLength / 1000).toFixed(0)}k chars</span>
                            </div>
                            <input
                              type="range"
                              min={4000}
                              max={16000}
                              step={2000}
                              value={reportConfig.maxReportLength}
                              onChange={(e) => setReportConfig({ ...reportConfig, maxReportLength: parseInt(e.target.value) })}
                              style={{ width: '100%' }}
                            />
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: '#9ca3af', marginTop: 2 }}>
                              <span>4k</span>
                              <span>16k</span>
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
              {reportLoading && (
                <div className="panel" style={{ background: '#fafafa', animation: 'fadeIn 0.5s ease' }}>
                  <h3 style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <FileText size={18} color="#2563eb" />
                    AI Report
                  </h3>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#888', fontSize: 14 }}>
                    <Loader2 size={16} className="spinning" />
                    Generating summary...
                  </div>
                </div>
              )}
              {enhancedReportLoading && (
                <div className="panel" style={{ background: '#fafafa', animation: 'fadeIn 0.5s ease' }}>
                  <h3 style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <BookOpen size={18} color="#7c3aed" />
                    Deep Dive Report
                  </h3>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6, color: '#888', fontSize: 14 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <Loader2 size={16} className="spinning" />
                      Fetching news sources...
                    </div>
                    <div style={{ fontSize: 12, color: '#aaa', paddingLeft: 24 }}>
                      Building storyline · Querying GKG · Generating narrative
                    </div>
                  </div>
                </div>
              )}
              {report && !enhancedReport && <div style={{ animation: 'fadeIn 0.5s ease' }}><ReportPanel report={report} /></div>}
              {enhancedReport && <EventReportPanel report={enhancedReport} />}

              {/* Event Detail Card */}
              {eventDetail && (
                <div style={{ animation: 'fadeIn 0.5s ease' }}>
                  <EventDetailCard event={eventDetail} />
                </div>
              )}

              {/* Similar Events */}
              {similarEvents && (
                <div style={{ animation: 'fadeIn 0.6s ease' }}>
                  <SimilarEventCards events={similarEvents} onEventClick={handleEventClick} />
                </div>
              )}

              {/* Daily Brief Stats */}
              {dailyBrief && (
                <div className="panel" style={{ animation: 'fadeIn 0.5s ease' }}>
                  <h3 style={{ fontSize: 14, fontWeight: 600, color: '#555', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 12 }}>
                    Daily Brief
                  </h3>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: 12 }}>
                    <DailyBriefStat label="Total Events" value={dailyBrief.total_events} color="#2563eb" />
                    <DailyBriefStat label="Conflict Events" value={dailyBrief.conflict_events} color="#dc2626" />
                    <DailyBriefStat label="Cooperation Events" value={dailyBrief.cooperation_events} color="#16a34a" />
                    <DailyBriefStat label="Avg Goldstein" value={typeof dailyBrief.avg_goldstein === 'number' ? dailyBrief.avg_goldstein.toFixed(2) : dailyBrief.avg_goldstein} color="#7c3aed" />
                    <DailyBriefStat label="Avg Tone" value={typeof dailyBrief.avg_tone === 'number' ? dailyBrief.avg_tone.toFixed(2) : dailyBrief.avg_tone} color="#059669" />
                  </div>
                </div>
              )}

              {/* Search Results */}
              {searchEvents && Array.isArray(searchEvents) && searchEvents.length > 0 && !eventDetail && (
                <div className="panel" style={{ animation: 'fadeIn 0.6s ease' }}>
                  <h3 style={{ fontSize: 14, fontWeight: 600, color: '#555', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 16 }}>
                    Search Results <span style={{ fontSize: 12, color: '#888', fontWeight: 400 }}>({searchEvents.length})</span>
                  </h3>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                    {searchEvents.slice(0, 10).map((evt: EventItem, i: number) => (
                      <CompactEventCard key={i} event={evt} onClick={() => handleEventClick(evt)} />
                    ))}
                    {searchEvents.length > 10 && (
                      <p style={{ textAlign: 'center', color: '#888', fontSize: 12, marginTop: 4 }}>
                        + {searchEvents.length - 10} more events
                      </p>
                    )}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
