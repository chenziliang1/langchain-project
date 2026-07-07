import { useCallback, useEffect, useState } from 'react';
import { RefreshCw, TrendingUp, Filter } from 'lucide-react';
import { api } from '../api/client';
import type { ThpForecastResult } from '../types';
import ForecastPanel from './ForecastPanel';

type ForecastFocusMode = 'location' | 'actor';

function addDays(date: string, days: number) {
  const value = new Date(`${date}T00:00:00`);
  value.setDate(value.getDate() + days);
  return value.toISOString().slice(0, 10);
}

function hasPairSeparator(value: string) {
  const lowered = value.toLowerCase();
  return [' and ', ' vs ', ' versus ', '/', ','].some((s) => lowered.includes(s));
}

export default function ForecastWorkspace() {
  const [forecastDate, setForecastDate] = useState('2024-02-01');
  const [forecastFocusMode, setForecastFocusMode] = useState<ForecastFocusMode>('location');
  const [forecastTarget, setForecastTarget] = useState('United States');
  const [forecastEventType, setForecastEventType] = useState('all');
  const [forecastResult, setForecastResult] = useState<ThpForecastResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const historyStartDate = addDays(forecastDate, -30);
  const historyEndDate = addDays(forecastDate, -1);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    const trimmedTarget = forecastTarget.trim();
    const forecastTargetParams =
      forecastFocusMode === 'actor'
        ? hasPairSeparator(trimmedTarget)
          ? { region: trimmedTarget ? `actor_pair:${trimmedTarget}` : undefined }
          : { actor: trimmedTarget || undefined }
        : { region: trimmedTarget || undefined };
    try {
      const forecastRes = await api.getForecast(historyStartDate, historyEndDate, {
        ...forecastTargetParams,
        event_type: forecastEventType,
        forecast_days: 7,
      });
      if (forecastRes.ok) setForecastResult(forecastRes.data || null);
      else setError(forecastRes.error || 'Forecast failed');
    } catch (err: any) {
      setError(err.message || 'Forecast failed');
    } finally {
      setLoading(false);
    }
  }, [historyStartDate, historyEndDate, forecastFocusMode, forecastTarget, forecastEventType]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <div style={{ padding: 16 }}>
      {/* Page title */}
      <div style={{ marginBottom: 16 }}>
        <h2 style={{ fontSize: 20, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 10 }}>
          <TrendingUp size={22} color="#2563eb" />
          Event Forecast
        </h2>
        <p style={{ fontSize: 13, color: '#6b7280', marginTop: 4 }}>
          Predict event intensity for the next 7 days using Transformer Hawkes Process.
        </p>
      </div>

      {/* Control bar */}
      <div className="search-box" style={{ marginBottom: 16 }}>
        <Filter size={16} color="#888" />
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap', flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontSize: 13, color: '#555', fontWeight: 500, whiteSpace: 'nowrap' }}>Forecast from</span>
            <input
              type="date"
              value={forecastDate}
              onChange={(e) => setForecastDate(e.target.value)}
              style={{
                border: '1px solid #e5e7eb',
                borderRadius: 8,
                padding: '6px 10px',
                fontSize: 13,
                outline: 'none',
              }}
            />
          </div>
          <select
            value={forecastFocusMode}
            onChange={(e) => setForecastFocusMode(e.target.value as ForecastFocusMode)}
            style={{
              border: '1px solid #e5e7eb',
              borderRadius: 8,
              padding: '6px 10px',
              fontSize: 13,
              outline: 'none',
              background: 'white',
            }}
          >
            <option value="location">Location</option>
            <option value="actor">Actor</option>
          </select>
          <input
            value={forecastTarget}
            onChange={(e) => setForecastTarget(e.target.value)}
            placeholder={
              forecastFocusMode === 'location'
                ? 'e.g. Canada, US, United States and Canada'
                : 'e.g. POLICE, GOVERNMENT'
            }
            style={{
              border: '1px solid #e5e7eb',
              borderRadius: 8,
              padding: '6px 12px',
              fontSize: 13,
              outline: 'none',
              minWidth: 220,
              flex: 1,
            }}
          />
          <select
            value={forecastEventType}
            onChange={(e) => setForecastEventType(e.target.value)}
            style={{
              border: '1px solid #e5e7eb',
              borderRadius: 8,
              padding: '6px 10px',
              fontSize: 13,
              outline: 'none',
              background: 'white',
            }}
          >
            <option value="all">All events</option>
            <option value="conflict">Conflict</option>
            <option value="cooperation">Cooperation</option>
            <option value="protest">Protest</option>
          </select>
        </div>
        <button
          className="search-btn"
          onClick={refresh}
          disabled={loading}
          style={{ opacity: loading ? 0.6 : 1 }}
        >
          <RefreshCw size={14} className={loading ? 'spinning' : ''} />
          {loading ? 'Loading...' : 'Refresh'}
        </button>
      </div>

      {error && (
        <div className="error-banner" style={{ marginBottom: 16 }}>
          {error}
        </div>
      )}

      <ForecastPanel
        forecastResult={forecastResult}
        historyStartDate={historyStartDate}
        historyEndDate={historyEndDate}
      />
    </div>
  );
}
