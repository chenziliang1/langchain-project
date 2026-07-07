import { Lightbulb, TrendingUp, TrendingDown, MapPin, Users, Activity, AlertTriangle, Handshake } from 'lucide-react';
import type { DashboardData, TimeSeriesPoint, InsightsData } from '../types';

interface Props {
  dashboard: DashboardData | null;
  timeSeries: TimeSeriesPoint[];
  insights?: InsightsData | null;
}

interface Insight {
  icon: React.ReactNode;
  title: string;
  description: string;
  color: string;
  bg: string;
}

export default function InsightCards({ dashboard, timeSeries, insights }: Props) {
  if (!dashboard) return null;

  const computedInsights: Insight[] = [];

  // 1. Most active day
  const dailyTrend = dashboard.daily_trend?.data || [];
  if (dailyTrend.length > 0) {
    const maxDay = dailyTrend.reduce((max: any, d: any) => (d.cnt > max.cnt ? d : max), dailyTrend[0]);
    computedInsights.push({
      icon: <Activity size={16} color="#2563eb" />,
      title: 'Peak Activity Day',
      description: `${maxDay.SQLDATE} saw ${maxDay.cnt?.toLocaleString()} events — the highest in this period.`,
      color: '#2563eb',
      bg: '#eff6ff',
    });
  }

  // 2. Top actor insight
  const topActors = dashboard.top_actors?.data || [];
  if (topActors.length > 0) {
    const top = topActors[0];
    computedInsights.push({
      icon: <Users size={16} color="#7c3aed" />,
      title: 'Most Active Actor',
      description: `${top.actor} was involved in ${top.event_count?.toLocaleString()} events, leading all actors.`,
      color: '#7c3aed',
      bg: '#f5f3ff',
    });
  }

  // 3. Conflict trend
  if (timeSeries.length >= 2) {
    const firstWeek = timeSeries.slice(0, Math.min(7, Math.floor(timeSeries.length / 2)));
    const lastWeek = timeSeries.slice(-Math.min(7, Math.floor(timeSeries.length / 2)));
    const firstConflict = firstWeek.reduce((s, d) => s + (d.conflict_pct || 0), 0) / (firstWeek.length || 1);
    const lastConflict = lastWeek.reduce((s, d) => s + (d.conflict_pct || 0), 0) / (lastWeek.length || 1);
    const diff = lastConflict - firstConflict;
    if (Math.abs(diff) > 3) {
      computedInsights.push({
        icon: diff > 0 ? <TrendingUp size={16} color="#dc2626" /> : <TrendingDown size={16} color="#16a34a" />,
        title: diff > 0 ? 'Rising Tensions' : 'Improving Relations',
        description: diff > 0
          ? `Conflict rate increased by ${diff.toFixed(1)}% toward the end of this period.`
          : `Conflict rate decreased by ${Math.abs(diff).toFixed(1)}% toward the end of this period.`,
        color: diff > 0 ? '#dc2626' : '#16a34a',
        bg: diff > 0 ? '#fef2f2' : '#f0fdf4',
      });
    }
  }

  // 4. Tone insight
  const toneVal = insights?.sentiment?.avg_tone ?? dashboard?.summary_stats?.data?.[0]?.avg_tone ?? 0;
  if (toneVal < -2) {
    computedInsights.push({
      icon: <AlertTriangle size={16} color="#dc2626" />,
      title: 'Negative Media Sentiment',
      description: `Average tone of ${Number(toneVal).toFixed(2)} suggests predominantly negative media coverage.`,
      color: '#dc2626',
      bg: '#fef2f2',
    });
  } else if (toneVal > 2) {
    computedInsights.push({
      icon: <Handshake size={16} color="#16a34a" />,
      title: 'Positive Media Sentiment',
      description: `Average tone of ${Number(toneVal).toFixed(2)} suggests predominantly positive media coverage.`,
      color: '#16a34a',
      bg: '#f0fdf4',
    });
  }

  // 5. Geo hotspot
  const geoDist = dashboard.geo_distribution?.data || [];
  if (geoDist.length > 0) {
    const topGeo = geoDist[0];
    computedInsights.push({
      icon: <MapPin size={16} color="#059669" />,
      title: 'Geographic Hotspot',
      description: `${topGeo.country_code} recorded ${topGeo.event_count?.toLocaleString()} events — the most active location.`,
      color: '#059669',
      bg: '#ecfdf5',
    });
  }

  // 6. Event type dominance
  const eventTypes = dashboard.event_types?.data || [];
  if (eventTypes.length > 0) {
    const topType = eventTypes[0];
    const total = eventTypes.reduce((s: number, e: any) => s + e.event_count, 0);
    const pct = total > 0 ? Math.round((topType.event_count / total) * 100) : 0;
    computedInsights.push({
      icon: <Lightbulb size={16} color="#f59e0b" />,
      title: 'Dominant Event Type',
      description: `${topType.event_type} accounts for ${pct}% of all events (${topType.event_count?.toLocaleString()} total).`,
      color: '#f59e0b',
      bg: '#fffbeb',
    });
  }

  // Show max 4 insights
  const displayInsights = computedInsights.slice(0, 4);

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12, marginBottom: 16 }}>
      {displayInsights.map((insight, idx) => (
        <div
          key={idx}
          style={{
            padding: '14px 16px',
            borderRadius: 12,
            background: insight.bg,
            border: `1px solid ${insight.color}20`,
            display: 'flex',
            alignItems: 'flex-start',
            gap: 12,
            transition: 'transform 0.15s ease, box-shadow 0.15s ease',
          }}
          onMouseEnter={(e) => {
            (e.currentTarget as HTMLDivElement).style.transform = 'translateY(-2px)';
            (e.currentTarget as HTMLDivElement).style.boxShadow = '0 4px 12px rgba(0,0,0,0.08)';
          }}
          onMouseLeave={(e) => {
            (e.currentTarget as HTMLDivElement).style.transform = 'translateY(0)';
            (e.currentTarget as HTMLDivElement).style.boxShadow = 'none';
          }}
        >
          <div style={{
            width: 32,
            height: 32,
            borderRadius: 8,
            background: 'white',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
            boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
          }}>
            {insight.icon}
          </div>
          <div>
            <div style={{ fontSize: 12, fontWeight: 700, color: insight.color, marginBottom: 3, textTransform: 'uppercase', letterSpacing: '0.3px' }}>
              {insight.title}
            </div>
            <div style={{ fontSize: 12, color: '#4b5563', lineHeight: 1.5 }}>
              {insight.description}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
