import { Calendar, MapPin, Users, Scale, Newspaper, Link2, Fingerprint, Tag, Copy, Check } from 'lucide-react';
import { useState } from 'react';
import type { EventItem } from '../types';

interface Props {
  event: EventItem & {
    key_actors?: string;
    location_name?: string;
    location_country?: string;
    severity_score?: number;
    SOURCEURL?: string;
    event_data?: EventItem;
  };
}

function getEventTypeColor(label?: string): string {
  if (!label) return '#6b7280';
  const l = label.toLowerCase();
  if (l.includes('conflict') || l.includes('viol') || l.includes('attack')) return '#dc2626';
  if (l.includes('cooper') || l.includes('agree') || l.includes('aid')) return '#059669';
  if (l.includes('protest') || l.includes('demonstr')) return '#d97706';
  return '#6b7280';
}

function getGoldsteinColor(scale?: number): string {
  if (scale === undefined || scale === null) return '#6b7280';
  if (scale < -5) return '#dc2626';
  if (scale > 5) return '#059669';
  return '#6b7280';
}

function formatDate(dateStr?: string): string {
  if (!dateStr) return 'Unknown date';
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    });
  } catch {
    return dateStr;
  }
}

export default function EventDetailCard({ event }: Props) {
  const [copied, setCopied] = useState(false);
  
  // Handle both fingerprint-format (with event_data nested) and EVT-format (flat)
  const ed = event.event_data || event;
  
  const headline = event.headline || `${ed.Actor1Name || 'Unknown'} vs ${ed.Actor2Name || 'Unknown'}`;
  const location = event.location_name || ed.ActionGeo_FullName || 'Unknown location';
  const country = event.location_country || ed.ActionGeo_CountryCode || '';
  const actors = event.key_actors || `${ed.Actor1Name || ''}${ed.Actor2Name ? ` vs ${ed.Actor2Name}` : ''}`;
  const goldstein = ed.GoldsteinScale;
  const tone = ed.AvgTone;
  const articles = ed.NumArticles || 0;
  const fp = event.fingerprint || '';
  const summary = event.summary;
  const eventType = event.event_type_label;
  const url = ed.SOURCEURL;
  const globalEventId = ed.GlobalEventID;

  return (
    <div className="panel" style={{ padding: 24 }}>
      {/* Event type badge */}
      {eventType && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 12 }}>
          <Tag size={14} color={getEventTypeColor(eventType)} />
          <span
            style={{
              fontSize: 12,
              fontWeight: 600,
              textTransform: 'uppercase',
              letterSpacing: 0.5,
              color: getEventTypeColor(eventType),
              background: `${getEventTypeColor(eventType)}15`,
              padding: '4px 10px',
              borderRadius: 20,
            }}
          >
            {eventType}
          </span>
        </div>
      )}

      {/* Headline */}
      <h2 style={{ fontSize: 22, fontWeight: 700, color: '#1a1a1a', marginBottom: 16, lineHeight: 1.3 }}>
        {headline}
      </h2>

      {/* Meta row */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '12px 20px', marginBottom: 20 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <Calendar size={15} color="#6b7280" />
          <span style={{ fontSize: 14, color: '#4b5563' }}>{formatDate(ed.SQLDATE)}</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <MapPin size={15} color="#6b7280" />
          <span style={{ fontSize: 14, color: '#4b5563' }}>
            {location}
            {country && country !== location ? `, ${country}` : ''}
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <Users size={15} color="#6b7280" />
          <span style={{ fontSize: 14, color: '#4b5563' }}>{actors || 'Unknown actors'}</span>
        </div>
      </div>

      {/* Metrics row */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))',
          gap: 12,
          marginBottom: 20,
        }}
      >
        <div
          style={{
            background: `${getGoldsteinColor(goldstein)}08`,
            border: `1px solid ${getGoldsteinColor(goldstein)}20`,
            borderRadius: 10,
            padding: '12px 16px',
            textAlign: 'center',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 4, marginBottom: 4 }}>
            <Scale size={14} color={getGoldsteinColor(goldstein)} />
            <span style={{ fontSize: 11, color: '#888', textTransform: 'uppercase', letterSpacing: 0.5 }}>Goldstein</span>
          </div>
          <div style={{ fontSize: 20, fontWeight: 700, color: getGoldsteinColor(goldstein) }}>
            {goldstein !== undefined && goldstein !== null ? goldstein.toFixed(1) : '—'}
          </div>
        </div>

        <div
          style={{
            background: '#f8fafc',
            border: '1px solid #e2e8f0',
            borderRadius: 10,
            padding: '12px 16px',
            textAlign: 'center',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 4, marginBottom: 4 }}>
            <Newspaper size={14} color="#2563eb" />
            <span style={{ fontSize: 11, color: '#888', textTransform: 'uppercase', letterSpacing: 0.5 }}>Articles</span>
          </div>
          <div style={{ fontSize: 20, fontWeight: 700, color: '#2563eb' }}>{articles}</div>
        </div>

        {tone !== undefined && tone !== null && (
          <div
            style={{
              background: '#f8fafc',
              border: '1px solid #e2e8f0',
              borderRadius: 10,
              padding: '12px 16px',
              textAlign: 'center',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 4, marginBottom: 4 }}>
              <span style={{ fontSize: 11, color: '#888', textTransform: 'uppercase', letterSpacing: 0.5 }}>Tone</span>
            </div>
            <div style={{ fontSize: 20, fontWeight: 700, color: tone < 0 ? '#dc2626' : '#059669' }}>
              {tone > 0 ? '+' : ''}{tone.toFixed(2)}
            </div>
          </div>
        )}
      </div>

      {/* Summary */}
      {summary && (
        <div style={{ marginBottom: 16 }}>
          <h4 style={{ fontSize: 12, color: '#888', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 8 }}>
            Summary
          </h4>
          <p style={{ fontSize: 14, color: '#4b5563', lineHeight: 1.7, margin: 0 }}>{summary}</p>
        </div>
      )}

      {/* Fingerprint, Event ID & Source URL */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px 16px', alignItems: 'center', marginTop: 8 }}>
        {fp && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <Fingerprint size={12} color="#9ca3af" />
            <code style={{ fontSize: 11, color: '#9ca3af', background: '#f3f4f6', padding: '2px 6px', borderRadius: 4 }}>
              {fp}
            </code>
          </div>
        )}
        {globalEventId && (
          <button
            onClick={() => {
              navigator.clipboard.writeText(String(globalEventId));
              setCopied(true);
              setTimeout(() => setCopied(false), 2000);
            }}
            title="Copy Event ID to clipboard"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 4,
              fontSize: 11,
              color: copied ? '#059669' : '#6b7280',
              background: copied ? '#ecfdf5' : '#f3f4f6',
              border: `1px solid ${copied ? '#a7f3d0' : '#e5e7eb'}`,
              padding: '2px 8px',
              borderRadius: 4,
              cursor: 'pointer',
              transition: 'all 0.2s ease',
            }}
          >
            {copied ? <Check size={11} /> : <Copy size={11} />}
            ID: {globalEventId}
          </button>
        )}
        {url && (
          <a
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 4,
              fontSize: 12,
              color: '#2563eb',
              textDecoration: 'none',
            }}
          >
            <Link2 size={12} />
            Source
          </a>
        )}
        {ed.EventCode && (
          <span style={{ fontSize: 11, color: '#9ca3af' }}>
            CAMEO: {ed.EventCode}
          </span>
        )}
      </div>
    </div>
  );
}
