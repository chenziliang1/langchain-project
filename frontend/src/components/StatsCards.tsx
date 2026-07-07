import { useMemo } from 'react';
import { TrendingUp, TrendingDown, Activity, Users, Globe, Newspaper, BarChart3, Zap } from 'lucide-react';
import type { DashboardData, TimeSeriesPoint } from '../types';

interface Props {
  data: DashboardData | null;
  timeSeries?: TimeSeriesPoint[];
}

function MiniSparkline({ data, color, height = 24 }: { data: number[]; color: string; height?: number }) {
  if (data.length < 2) return <div style={{ height }} />;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const width = 60;
  const step = width / (data.length - 1);
  const points = data.map((v, i) => {
    const x = i * step;
    const y = height - ((v - min) / range) * height;
    return `${x},${y}`;
  }).join(' ');

  return (
    <svg width={width} height={height} style={{ opacity: 0.7 }}>
      <polyline
        fill="none"
        stroke={color}
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
        points={points}
      />
    </svg>
  );
}

export default function StatsCards({ data, timeSeries }: Props) {
  const stats = useMemo(() => {
    if (!data) return [];
    const summary = data.summary_stats?.data?.[0] || {};
    const trend = data.daily_trend?.data || [];
    const eventCounts = trend.map((d: any) => d.cnt || 0);
    const goldsteinValues = trend.map((d: any) => d.goldstein || 0);

    // Calculate trend: compare second half vs first half
    const half = Math.floor(eventCounts.length / 2);
    const firstHalf = eventCounts.slice(0, half);
    const secondHalf = eventCounts.slice(half);
    const firstAvg = firstHalf.reduce((a: number, b: number) => a + b, 0) / (firstHalf.length || 1);
    const secondAvg = secondHalf.reduce((a: number, b: number) => a + b, 0) / (secondHalf.length || 1);
    const trendPct = firstAvg > 0 ? ((secondAvg - firstAvg) / firstAvg) * 100 : 0;
    const isUp = trendPct >= 0;

    // Conflict rate
    const totalEvents = summary.total_events || 1;
    const conflictEvents = trend.reduce((sum: number, d: any) => sum + (d.conflict || 0), 0);
    const conflictRate = Math.round((conflictEvents / totalEvents) * 100);

    // Tone trend from time series if available
    const toneValues = (timeSeries || []).map((d) => d.avg_tone || 0);
    const avgTone = summary.avg_tone ?? 0;

    return [
      {
        label: 'Total Events',
        value: summary.total_events ?? 0,
        icon: Activity,
        color: '#2563eb',
        trend: isUp ? `+${trendPct.toFixed(1)}%` : `${trendPct.toFixed(1)}%`,
        trendUp: isUp,
        sparkline: eventCounts,
      },
      {
        label: 'Conflict Rate',
        value: `${conflictRate}%`,
        icon: Zap,
        color: conflictRate > 30 ? '#dc2626' : '#f59e0b',
        trend: conflictRate > 30 ? 'High' : 'Moderate',
        trendUp: conflictRate > 30,
        sparkline: goldsteinValues,
      },
      {
        label: 'Avg Tone',
        value: avgTone.toFixed(2),
        icon: BarChart3,
        color: avgTone < -1 ? '#dc2626' : avgTone > 1 ? '#16a34a' : '#6b7280',
        trend: avgTone < -1 ? 'Negative' : avgTone > 1 ? 'Positive' : 'Neutral',
        trendUp: avgTone > 0,
        sparkline: toneValues,
      },
      {
        label: 'Unique Actors',
        value: summary.unique_actors ?? 0,
        icon: Users,
        color: '#7c3aed',
      },
      {
        label: 'Total Articles',
        value: summary.total_articles ?? 0,
        icon: Newspaper,
        color: '#059669',
      },
      {
        label: 'Avg Goldstein',
        value: summary.avg_goldstein?.toFixed(2) ?? 'N/A',
        icon: Globe,
        color: summary.avg_goldstein < 0 ? '#dc2626' : '#2563eb',
      },
    ];
  }, [data, timeSeries]);

  if (!data) return null;

  return (
    <div className="stats-row">
      {stats.map((s) => {
        const Icon = s.icon;
        return (
          <div key={s.label} className="stat-card">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 4 }}>
              <div className="label" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <Icon size={14} color={s.color} />
                {s.label}
              </div>
              {s.sparkline && s.sparkline.length > 1 && (
                <MiniSparkline data={s.sparkline} color={s.color} />
              )}
            </div>
            <div className="value" style={{ color: s.color }}>
              {typeof s.value === 'number' ? s.value.toLocaleString() : s.value}
            </div>
            {s.trend !== undefined && (
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 4,
                  fontSize: 11,
                  fontWeight: 600,
                  marginTop: 4,
                  color: s.trendUp ? '#dc2626' : '#16a34a',
                }}
              >
                {s.trendUp ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
                {s.trend}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
