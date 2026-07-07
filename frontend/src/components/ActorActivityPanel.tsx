import { useState } from 'react';
import { Activity, TrendingUp, TrendingDown, Minus, Copy, Check, User } from 'lucide-react';
import type { ActorActivityItem } from '../types';

interface Props {
  activity: ActorActivityItem[];
  actorName?: string;
}

function goldsteinColor(gs: number | undefined): string {
  if (gs === undefined) return '#9ca3af';
  if (gs < -5) return '#dc2626';
  if (gs < 0) return '#f59e0b';
  if (gs > 5) return '#059669';
  return '#6b7280';
}

function goldsteinLabel(gs: number | undefined): string {
  if (gs === undefined) return 'Neutral';
  if (gs < -5) return 'Conflict';
  if (gs < 0) return 'Tension';
  if (gs > 5) return 'Cooperation';
  return 'Neutral';
}

function toneColor(tone: number | undefined): string {
  if (tone === undefined) return '#9ca3af';
  if (tone < -2) return '#dc2626';
  if (tone < 0) return '#f59e0b';
  return '#059669';
}

export default function ActorActivityPanel({ activity, actorName }: Props) {
  if (!activity || activity.length === 0) return null;

  const maxArticles = Math.max(...activity.map(t => t.total_articles || 0), 1);
  const displayActor = actorName || 'Primary Actor';

  return (
    <div className="panel" style={{ background: '#fff', border: '1px solid #e2e8f0' }}>
      <h3 style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4, fontSize: 15, fontWeight: 700, color: '#1a1a1a' }}>
        <Activity size={18} color="#059669" />
        Actor Activity Overview
      </h3>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12, color: '#059669', background: '#ecfdf5', padding: '2px 8px', borderRadius: 10 }}>
          <User size={11} />
          {displayActor}
        </span>
        <span style={{ fontSize: 11, color: '#888' }}>
          Daily aggregated stats — all events where this actor appears as Actor1 or Actor2
        </span>
      </div>

      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ borderBottom: '2px solid #e5e7eb', textAlign: 'left' }}>
              <th style={{ padding: '8px 6px', color: '#6b7280', fontWeight: 600 }}>Date</th>
              <th style={{ padding: '8px 6px', color: '#6b7280', fontWeight: 600 }}>Events</th>
              <th style={{ padding: '8px 6px', color: '#6b7280', fontWeight: 600 }}>Articles</th>
              <th style={{ padding: '8px 6px', color: '#6b7280', fontWeight: 600 }}>Goldstein</th>
              <th style={{ padding: '8px 6px', color: '#6b7280', fontWeight: 600 }}>Tone</th>
              <th style={{ padding: '8px 6px', color: '#6b7280', fontWeight: 600 }}>Top CAMEO</th>
            </tr>
          </thead>
          <tbody>
            {activity.map((item, i) => {
              const barWidth = `${((item.total_articles || 0) / maxArticles) * 100}%`;
              const gs = item.avg_goldstein;
              const tone = item.avg_tone;
              return (
                <tr
                  key={i}
                  style={{
                    borderBottom: '1px solid #f3f4f6',
                    background: i % 2 === 0 ? '#fafafa' : '#fff',
                  }}
                >
                  <td style={{ padding: '8px 6px', whiteSpace: 'nowrap', fontWeight: 500, color: '#374151' }}>
                    {item.date}
                  </td>
                  <td style={{ padding: '8px 6px', textAlign: 'center' }}>
                    <span style={{
                      display: 'inline-block',
                      minWidth: 24,
                      padding: '2px 8px',
                      borderRadius: 10,
                      background: '#f3f4f6',
                      fontWeight: 600,
                      fontSize: 12,
                      color: '#374151',
                    }}>
                      {item.total_events}
                    </span>
                  </td>
                  <td style={{ padding: '8px 6px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <div style={{ width: 60, height: 6, background: '#e5e7eb', borderRadius: 3, overflow: 'hidden' }}>
                        <div style={{ width: barWidth, height: '100%', background: '#3b82f6', borderRadius: 3 }} />
                      </div>
                      <span style={{ fontSize: 12, color: '#6b7280' }}>{(item.total_articles || 0).toLocaleString()}</span>
                    </div>
                  </td>
                  <td style={{ padding: '8px 6px' }}>
                    <span style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: 4,
                      fontSize: 12,
                      fontWeight: 600,
                      color: goldsteinColor(gs),
                    }}>
                      {gs !== undefined && gs !== null ? (
                        gs > 0 ? <TrendingUp size={12} /> : gs < 0 ? <TrendingDown size={12} /> : <Minus size={12} />
                      ) : <Minus size={12} />}
                      {gs !== undefined && gs !== null ? gs.toFixed(1) : '—'}
                      <span style={{ fontSize: 10, fontWeight: 400, color: '#9ca3af', marginLeft: 2 }}>
                        {goldsteinLabel(gs)}
                      </span>
                    </span>
                  </td>
                  <td style={{ padding: '8px 6px' }}>
                    <span style={{
                      fontSize: 12,
                      fontWeight: 600,
                      color: toneColor(tone),
                    }}>
                      {tone !== undefined && tone !== null ? `${tone > 0 ? '+' : ''}${tone.toFixed(2)}` : '—'}
                    </span>
                  </td>
                  <td style={{ padding: '8px 6px', maxWidth: 160 }}>
                    <span style={{
                      display: 'inline-block',
                      padding: '2px 8px',
                      borderRadius: 6,
                      background: '#f3f4f6',
                      fontSize: 11,
                      color: '#4b5563',
                      whiteSpace: 'nowrap',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      maxWidth: '100%',
                    }} title={item.top_cameo_name || ''}>
                      {item.top_cameo_name || 'Unknown'}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div style={{ marginTop: 12, fontSize: 11, color: '#9ca3af', display: 'flex', gap: 16 }}>
        <span>Total days: {activity.length}</span>
        <span>Total events: {activity.reduce((sum, t) => sum + (t.total_events || 0), 0).toLocaleString()}</span>
        <span>Total articles: {activity.reduce((sum, t) => sum + (t.total_articles || 0), 0).toLocaleString()}</span>
      </div>
    </div>
  );
}
