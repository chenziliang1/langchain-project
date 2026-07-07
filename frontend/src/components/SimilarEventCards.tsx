import { Calendar, MapPin, Users, ArrowRight, ExternalLink, Hash } from 'lucide-react';
import type { EventItem } from '../types';

interface SimilarEvent extends EventItem {
  match_reason?: string;
  match_reasons?: string[];
}

interface Props {
  events: SimilarEvent[];
  onEventClick?: (event: SimilarEvent) => void;
}

function getReasonColor(reason?: string): string {
  if (!reason) return '#6b7280';
  if (reason.includes('actor')) return '#7c3aed';
  if (reason.includes('region')) return '#2563eb';
  if (reason.includes('type')) return '#059669';
  return '#6b7280';
}

function formatDate(dateStr?: string): string {
  if (!dateStr) return '';
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  } catch {
    return dateStr;
  }
}

export default function SimilarEventCards({ events, onEventClick }: Props) {
  if (!Array.isArray(events) || events.length === 0) {
    const errorMsg = events && typeof events === 'object' && 'error' in events
      ? String((events as any).error)
      : 'No similar events found.';
    return (
      <div className="panel">
        <h3 style={{ fontSize: 14, fontWeight: 600, color: '#555', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 12 }}>
          Similar Events
        </h3>
        <p style={{ color: '#888', fontSize: 14 }}>{errorMsg}</p>
      </div>
    );
  }

  return (
    <div className="panel">
      <h3 style={{ fontSize: 14, fontWeight: 600, color: '#555', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 16 }}>
        Similar Events <span style={{ fontSize: 12, color: '#888', fontWeight: 400 }}>({events.length})</span>
      </h3>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {events.map((evt, i) => {
          const headline = evt.headline || `${evt.Actor1Name || 'Unknown'} vs ${evt.Actor2Name || 'Unknown'}`;
          const reason = evt.match_reason || 'Related';
          const reasonColor = getReasonColor(reason);

          return (
            <div
              key={i}
              onClick={() => onEventClick?.(evt)}
              style={{
                background: '#f8fafc',
                border: '1px solid #e2e8f0',
                borderRadius: 10,
                padding: '14px 16px',
                cursor: onEventClick ? 'pointer' : 'default',
                transition: 'all 0.15s ease',
              }}
              onMouseEnter={(e) => {
                if (onEventClick) {
                  e.currentTarget.style.borderColor = '#cbd5e1';
                  e.currentTarget.style.background = '#f1f5f9';
                }
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.borderColor = '#e2e8f0';
                e.currentTarget.style.background = '#f8fafc';
              }}
            >
              <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  {/* Headline */}
                  <div style={{ fontSize: 14, fontWeight: 600, color: '#1a1a1a', marginBottom: 8, lineHeight: 1.4 }}>
                    {headline}
                  </div>

                  {/* Meta row */}
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px 14px', alignItems: 'center' }}>
                    <span
                      style={{
                        fontSize: 11,
                        fontWeight: 600,
                        color: reasonColor,
                        background: `${reasonColor}15`,
                        padding: '2px 8px',
                        borderRadius: 12,
                      }}
                    >
                      {reason}
                    </span>

                    {evt.SQLDATE && (
                      <span style={{ display: 'flex', alignItems: 'center', gap: 3, fontSize: 12, color: '#6b7280' }}>
                        <Calendar size={11} />
                        {formatDate(evt.SQLDATE)}
                      </span>
                    )}

                    {evt.ActionGeo_FullName && (
                      <span style={{ display: 'flex', alignItems: 'center', gap: 3, fontSize: 12, color: '#6b7280' }}>
                        <MapPin size={11} />
                        {evt.ActionGeo_FullName}
                      </span>
                    )}

                    {(evt.Actor1Name || evt.Actor2Name) && (
                      <span style={{ display: 'flex', alignItems: 'center', gap: 3, fontSize: 12, color: '#6b7280' }}>
                        <Users size={11} />
                        {evt.Actor1Name || '?'}
                        {evt.Actor2Name ? ` vs ${evt.Actor2Name}` : ''}
                      </span>
                    )}

                    {evt.GlobalEventID && (
                      <span style={{ display: 'flex', alignItems: 'center', gap: 3, fontSize: 11, color: '#9ca3af', background: '#f3f4f6', padding: '1px 6px', borderRadius: 8 }}>
                        <Hash size={10} />
                        {evt.GlobalEventID}
                      </span>
                    )}

                    {evt.SOURCEURL && (
                      <a
                        href={evt.SOURCEURL}
                        target="_blank"
                        rel="noopener noreferrer"
                        onClick={(e) => e.stopPropagation()}
                        style={{ display: 'flex', alignItems: 'center', gap: 3, fontSize: 11, color: '#2563eb', textDecoration: 'none' }}
                      >
                        <ExternalLink size={10} />
                        Source
                      </a>
                    )}
                  </div>
                </div>

                {onEventClick && (
                  <ArrowRight size={16} color="#9ca3af" style={{ flexShrink: 0, marginTop: 2 }} />
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
