import { Newspaper, MapPin, Calendar, AlertTriangle, Handshake, Megaphone, ArrowRight, ExternalLink } from 'lucide-react';
import type { HeadlineItem } from '../types';

interface Props {
  events: HeadlineItem[];
  onSelectEvent?: (event: HeadlineItem) => void;
}

function getEventTypeIcon(goldstein?: number, eventTypeLabel?: string) {
  if (eventTypeLabel?.toLowerCase().includes('conflict') || (goldstein !== undefined && goldstein < -5)) {
    return <AlertTriangle size={14} color="#dc2626" />;
  }
  if (eventTypeLabel?.toLowerCase().includes('cooperat') || (goldstein !== undefined && goldstein > 5)) {
    return <Handshake size={14} color="#16a34a" />;
  }
  if (eventTypeLabel?.toLowerCase().includes('protest')) {
    return <Megaphone size={14} color="#f59e0b" />;
  }
  return <ArrowRight size={14} color="#6b7280" />;
}

function getSeverityBadge(severity?: number) {
  if (!severity) return null;
  if (severity >= 7) return { text: 'High', color: '#dc2626', bg: '#fef2f2' };
  if (severity >= 4) return { text: 'Medium', color: '#f59e0b', bg: '#fffbeb' };
  return { text: 'Low', color: '#6b7280', bg: '#f9fafb' };
}

export default function HotEventsPanel({ events, onSelectEvent }: Props) {
  if (events.length === 0) {
    return (
      <div className="panel" style={{ textAlign: 'center', padding: 40, color: '#9ca3af' }}>
        <Newspaper size={32} style={{ marginBottom: 8, opacity: 0.5 }} />
        <p>No hot events found for this period.</p>
      </div>
    );
  }

  return (
    <div className="panel">
      <h3 style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
        <Newspaper size={16} color="#2563eb" />
        Top Headlines
      </h3>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {events.map((ev, idx) => {
          const severity = getSeverityBadge(ev.severity_score);
          return (
            <div
              key={ev.GlobalEventID}
              onClick={() => onSelectEvent?.(ev)}
              style={{
                padding: '12px 14px',
                borderRadius: 10,
                background: idx === 0 ? '#eff6ff' : '#f9fafb',
                border: `1px solid ${idx === 0 ? '#bfdbfe' : '#e5e7eb'}`,
                cursor: onSelectEvent ? 'pointer' : 'default',
                transition: 'all 0.15s ease',
              }}
              onMouseEnter={(e) => {
                if (onSelectEvent) {
                  (e.currentTarget as HTMLDivElement).style.background = '#f0f7ff';
                  (e.currentTarget as HTMLDivElement).style.borderColor = '#93c5fd';
                }
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLDivElement).style.background = idx === 0 ? '#eff6ff' : '#f9fafb';
                (e.currentTarget as HTMLDivElement).style.borderColor = idx === 0 ? '#bfdbfe' : '#e5e7eb';
              }}
            >
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
                <div style={{
                  width: 22,
                  height: 22,
                  borderRadius: '50%',
                  background: idx === 0 ? '#2563eb' : '#e5e7eb',
                  color: idx === 0 ? 'white' : '#6b7280',
                  fontSize: 11,
                  fontWeight: 700,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: 0,
                  marginTop: 2,
                }}>
                  {idx + 1}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{
                    fontWeight: 600,
                    fontSize: 14,
                    color: '#1f2937',
                    lineHeight: 1.4,
                    marginBottom: 6,
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                  }}>
                    {ev.headline || `${ev.Actor1Name || 'Unknown'} vs ${ev.Actor2Name || 'Unknown'}`}
                    {severity && (
                      <span style={{
                        fontSize: 10,
                        fontWeight: 700,
                        padding: '2px 8px',
                        borderRadius: 12,
                        background: severity.bg,
                        color: severity.color,
                        whiteSpace: 'nowrap',
                      }}>
                        {severity.text}
                      </span>
                    )}
                  </div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px 14px', fontSize: 12, color: '#6b7280' }}>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                      <Calendar size={11} />
                      {ev.SQLDATE}
                    </span>
                    {ev.ActionGeo_FullName && (
                      <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                        <MapPin size={11} />
                        {ev.ActionGeo_FullName}
                      </span>
                    )}
                    <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                      {getEventTypeIcon(ev.GoldsteinScale, ev.event_type_label)}
                      Goldstein: {ev.GoldsteinScale?.toFixed(1) ?? 'N/A'}
                    </span>
                    <span style={{ fontWeight: 500, color: '#2563eb' }}>
                      {ev.NumArticles?.toLocaleString() ?? 0} articles
                    </span>
                  </div>
                  {ev.summary && (
                    <div style={{ marginTop: 6, fontSize: 12, color: '#4b5563', lineHeight: 1.4 }}>
                      {ev.summary}
                    </div>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
