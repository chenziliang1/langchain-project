import { MapPin, Calendar, User, ArrowRight, AlertTriangle, Handshake, Megaphone } from 'lucide-react';
import type { EventItem } from '../types';

interface Props {
  events: EventItem[];
  selectedEventId?: number | null;
  onSelectEvent: (event: EventItem) => void;
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

function getEventTypeColor(goldstein?: number, eventTypeLabel?: string) {
  if (eventTypeLabel?.toLowerCase().includes('conflict') || (goldstein !== undefined && goldstein < -5)) {
    return '#fef2f2';
  }
  if (eventTypeLabel?.toLowerCase().includes('cooperat') || (goldstein !== undefined && goldstein > 5)) {
    return '#f0fdf4';
  }
  if (eventTypeLabel?.toLowerCase().includes('protest')) {
    return '#fffbeb';
  }
  return '#f9fafb';
}

function getEventTypeBorder(goldstein?: number, eventTypeLabel?: string) {
  if (eventTypeLabel?.toLowerCase().includes('conflict') || (goldstein !== undefined && goldstein < -5)) {
    return '#fecaca';
  }
  if (eventTypeLabel?.toLowerCase().includes('cooperat') || (goldstein !== undefined && goldstein > 5)) {
    return '#bbf7d0';
  }
  if (eventTypeLabel?.toLowerCase().includes('protest')) {
    return '#fde68a';
  }
  return '#e5e7eb';
}

export default function EventTimeline({ events, selectedEventId, onSelectEvent }: Props) {
  if (events.length === 0) {
    return (
      <div className="panel" style={{ textAlign: 'center', padding: 40, color: '#9ca3af' }}>
        <p>No events found. Try adjusting your filters.</p>
      </div>
    );
  }

  // Group by date
  const grouped: Record<string, EventItem[]> = {};
  events.forEach((ev) => {
    const date = ev.SQLDATE;
    if (!grouped[date]) grouped[date] = [];
    grouped[date].push(ev);
  });
  const sortedDates = Object.keys(grouped).sort();

  return (
    <div className="panel" style={{ maxHeight: 600, overflow: 'auto' }}>
      <h3 style={{ marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
        <Calendar size={16} />
        Event Timeline ({events.length} events)
      </h3>

      <div style={{ position: 'relative', paddingLeft: 20 }}>
        {/* Timeline line */}
        <div
          style={{
            position: 'absolute',
            left: 6,
            top: 0,
            bottom: 0,
            width: 2,
            background: '#e5e7eb',
            borderRadius: 1,
          }}
        />

        {sortedDates.map((date) => (
          <div key={date} style={{ marginBottom: 16 }}>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                marginBottom: 8,
                position: 'relative',
              }}
            >
              <div
                style={{
                  width: 10,
                  height: 10,
                  borderRadius: '50%',
                  background: '#3b82f6',
                  position: 'absolute',
                  left: -17,
                  top: 4,
                  border: '2px solid white',
                }}
              />
              <span style={{ fontSize: 13, fontWeight: 600, color: '#374151' }}>{date}</span>
              <span style={{ fontSize: 11, color: '#9ca3af' }}>({grouped[date].length})</span>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {grouped[date].map((ev) => {
                const isSelected = selectedEventId === ev.GlobalEventID;
                return (
                  <div
                    key={ev.GlobalEventID}
                    onClick={() => onSelectEvent(ev)}
                    style={{
                      padding: '10px 12px',
                      borderRadius: 8,
                      background: isSelected ? '#ede9fe' : getEventTypeColor(ev.GoldsteinScale, ev.event_type_label),
                      border: `1px solid ${isSelected ? '#c4b5fd' : getEventTypeBorder(ev.GoldsteinScale, ev.event_type_label)}`,
                      cursor: 'pointer',
                      transition: 'all 0.15s ease',
                      fontSize: 13,
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
                      <div style={{ marginTop: 2, flexShrink: 0 }}>
                        {getEventTypeIcon(ev.GoldsteinScale, ev.event_type_label)}
                      </div>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontWeight: 600, color: '#1f2937', marginBottom: 2, lineHeight: 1.3 }}>
                          {ev.headline || `${ev.Actor1Name || 'Unknown'} vs ${ev.Actor2Name || 'Unknown'}`}
                        </div>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px 12px', color: '#6b7280', fontSize: 12 }}>
                          {ev.Actor1Name && (
                            <span style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                              <User size={11} /> {ev.Actor1Name}
                              {ev.Actor2Name && ` → ${ev.Actor2Name}`}
                            </span>
                          )}
                          {ev.ActionGeo_FullName && (
                            <span style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                              <MapPin size={11} /> {ev.ActionGeo_FullName}
                            </span>
                          )}
                          {ev.GoldsteinScale !== undefined && (
                            <span style={{ fontWeight: 500, color: ev.GoldsteinScale < -5 ? '#dc2626' : ev.GoldsteinScale > 5 ? '#16a34a' : '#6b7280' }}>
                              Goldstein: {ev.GoldsteinScale.toFixed(1)}
                            </span>
                          )}
                          {ev.NumArticles !== undefined && (
                            <span>{ev.NumArticles.toLocaleString()} articles</span>
                          )}
                        </div>
                        {ev.summary && (
                          <div style={{ marginTop: 4, color: '#4b5563', fontSize: 12, lineHeight: 1.4 }}>
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
        ))}
      </div>
    </div>
  );
}
