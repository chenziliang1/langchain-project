import { TrendingUp, TrendingDown, Activity, AlertTriangle, CalendarDays, BarChart3 } from 'lucide-react';
import ForecastChart from './ForecastChart';
import type { ThpForecastResult } from '../types';

interface Props {
  forecastResult?: ThpForecastResult | null;
  historyStartDate: string;
  historyEndDate: string;
}

function riskColor(level?: string) {
  if (!level) return '#6b7280';
  if (level.includes('high')) return '#dc2626';
  if (level.includes('moderate')) return '#f59e0b';
  return '#16a34a';
}

function riskBg(level?: string) {
  if (!level) return '#f3f4f6';
  if (level.includes('high')) return '#fef2f2';
  if (level.includes('moderate')) return '#fffbeb';
  return '#f0fdf4';
}

export default function ForecastPanel({
  forecastResult,
  historyStartDate,
  historyEndDate,
}: Props) {
  if (!forecastResult || !forecastResult.forecast || forecastResult.forecast.length === 0) {
    return (
      <div className="panel" style={{ textAlign: 'center', padding: 48, color: '#888' }}>
        <BarChart3 size={40} style={{ marginBottom: 12, opacity: 0.4 }} />
        <p>No forecast data available.</p>
        <p style={{ fontSize: 13, marginTop: 4 }}>
          Select a date range with historical data and click Refresh.
        </p>
      </div>
    );
  }

  const forecast = forecastResult.forecast;
  const history = forecastResult.recent_history || [];
  const summary = forecastResult.summary || {};

  const avgEvents = forecast.reduce((sum, f) => sum + f.expected_events, 0) / forecast.length;
  const peakDay = forecast.reduce((max, f) => (f.expected_events > max.expected_events ? f : max), forecast[0]);
  const riskLevel = summary.risk_level || peakDay.risk_level || 'low';
  const trendPct = summary.recent_vs_history_pct ?? 0;
  const trendUp = trendPct >= 0;

  const stats = [
    {
      label: 'Avg Forecast',
      value: Math.round(avgEvents).toLocaleString(),
      icon: Activity,
      color: '#2563eb',
    },
    {
      label: 'Peak Day',
      value: peakDay.date.slice(5),
      icon: CalendarDays,
      color: '#7c3aed',
    },
    {
      label: 'Risk Level',
      value: riskLevel.charAt(0).toUpperCase() + riskLevel.slice(1),
      icon: AlertTriangle,
      color: riskColor(riskLevel),
    },
    {
      label: 'Trend vs Past',
      value: `${trendUp ? '+' : ''}${trendPct.toFixed(1)}%`,
      icon: trendUp ? TrendingUp : TrendingDown,
      color: trendUp ? '#dc2626' : '#16a34a',
    },
  ];

  return (
    <div>
      {/* Stats row */}
      <div className="stats-row" style={{ marginBottom: 16 }}>
        {stats.map((s) => {
          const Icon = s.icon;
          return (
            <div key={s.label} className="stat-card">
              <div className="label" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <Icon size={14} color={s.color} />
                {s.label}
              </div>
              <div className="value" style={{ color: s.color }}>
                {s.value}
              </div>
            </div>
          );
        })}
      </div>

      {/* Chart */}
      <div className="dashboard-grid" style={{ padding: 0, marginBottom: 16 }}>
        <ForecastChart
          history={history}
          forecast={forecast}
          title={`Historical (${historyStartDate} → ${historyEndDate}) + Forecast`}
        />
        <div className="panel">
          <h3>7-Day Forecast Detail</h3>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            {forecast.map((point) => (
              <div
                key={point.date}
                style={{
                  background: riskBg(point.risk_level),
                  borderRadius: 10,
                  padding: 12,
                  border: '1px solid #e5e7eb',
                }}
              >
                <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>
                  {point.date}
                </div>
                <div style={{ fontSize: 20, fontWeight: 700, color: '#1a1a1a' }}>
                  {Math.round(point.expected_events).toLocaleString()}
                </div>
                <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 2 }}>
                  {Math.round(point.low_events).toLocaleString()} – {Math.round(point.high_events).toLocaleString()}
                </div>
                {point.risk_level && (
                  <div
                    style={{
                      fontSize: 11,
                      fontWeight: 600,
                      color: riskColor(point.risk_level),
                      marginTop: 4,
                      textTransform: 'capitalize',
                    }}
                  >
                    {point.risk_level} risk
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Model info */}
      <div className="panel" style={{ display: 'flex', gap: 16, alignItems: 'center', flexWrap: 'wrap' }}>
        <div style={{ fontSize: 12, color: '#6b7280' }}>
          <strong style={{ color: '#1a1a1a' }}>Model:</strong> {forecastResult.model?.replace(/_/g, ' ') || 'THP'}
        </div>
        <div style={{ fontSize: 12, color: '#6b7280' }}>
          <strong style={{ color: '#1a1a1a' }}>Input window:</strong> {historyStartDate} → {historyEndDate}
        </div>
        <div style={{ fontSize: 12, color: '#6b7280' }}>
          <strong style={{ color: '#1a1a1a' }}>Checkpoint:</strong>{' '}
          {forecastResult.checkpoint?.available ? (
            <span style={{ color: '#16a34a' }}>Neural loaded</span>
          ) : (
            <span style={{ color: '#f59e0b' }}>Empirical fallback</span>
          )}
        </div>
      </div>
    </div>
  );
}
