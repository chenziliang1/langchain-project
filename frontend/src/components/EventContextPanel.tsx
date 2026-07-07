import { useState } from 'react';
import { Calendar, MapPin, Users, ChevronDown, ChevronUp, Star, ExternalLink, Hash } from 'lucide-react';
import type { EventContextData } from '../types';

interface Props {
  context: EventContextData;
}

function getEventTypeColor(label?: string): string {
  if (!label) return '#6b7280';
  const l = label.toLowerCase();
  if (l.includes('conflict') || l.includes('viol') || l.includes('attack')) return '#dc2626';
  if (l.includes('cooper') || l.includes('agree') || l.includes('aid')) return '#059669';
  if (l.includes('protest') || l.includes('demonstr')) return '#d97706';
  return '#6b7280';
}

function formatDate(dateStr: string): string {
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  } catch {
    return dateStr;
  }
}



function CopyableTag({ text, color = '#4b5563', bg = '#f3f4f6' }: { text: string; color?: string; bg?: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <span
      onClick={(e) => {
        e.stopPropagation();
        navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 1200);
      }}
      style={{
        fontSize: 12,
        fontWeight: 500,
        color: copied ? '#059669' : color,
        background: copied ? '#ecfdf5' : bg,
        padding: '4px 12px',
        borderRadius: 20,
        cursor: 'pointer',
        userSelect: 'none',
        transition: 'all 0.15s ease',
        border: `1px solid ${copied ? '#a7f3d0' : 'transparent'}`,
      }}
      title="Click to copy"
    >
      {copied ? 'Copied!' : text}
    </span>
  );
}

export default function EventContextPanel({ context }: Props) {
  const { entity_evolution, theme_evolution } = context;
  const [activeTab, setActiveTab] = useState<'entities' | 'themes'>('entities');

  return (
    <div className="panel">
      <h3 style={{ fontSize: 16, fontWeight: 700, color: '#1a1a1a', marginBottom: 4 }}>
        Context Analysis
      </h3>
      <p style={{ fontSize: 12, color: '#888', marginBottom: 12 }}>
        Entities, locations, and themes from similar events
      </p>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 16, borderBottom: '1px solid #e2e8f0' }}>
        {(['entities', 'themes'] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            style={{
              padding: '8px 16px',
              fontSize: 13,
              fontWeight: 600,
              border: 'none',
              background: 'none',
              color: activeTab === tab ? '#2563eb' : '#888',
              borderBottom: activeTab === tab ? '2px solid #2563eb' : '2px solid transparent',
              cursor: 'pointer',
              textTransform: 'capitalize',
            }}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* Entities Tab */}
      {activeTab === 'entities' && (
        <div>
          <h4 style={{ fontSize: 13, color: '#555', marginBottom: 12 }}>Key Actors <span style={{ fontWeight: 400, color: '#9ca3af' }}>(click to copy)</span></h4>
          {entity_evolution.actors.length === 0 ? (
            <p style={{ color: '#888', fontSize: 14 }}>No actor data available.</p>
          ) : (
            <div style={{ display: 'grid', gap: 8 }}>
              {entity_evolution.actors.slice(0, 10).map((actor, i) => (
                <div
                  key={i}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    padding: '10px 14px',
                    background: '#f8fafc',
                    borderRadius: 8,
                  }}
                >
                  <div>
                    <CopyableTag text={actor.name} color="#1a1a1a" bg="#f8fafc" />
                    <div style={{ fontSize: 11, color: '#888', marginTop: 6 }}>
                      {actor.event_count} events · {actor.role}
                      {actor.avg_goldstein !== undefined && ` · Goldstein: ${actor.avg_goldstein}`}
                    </div>
                  </div>
                  <div style={{ fontSize: 12, color: '#888', textAlign: 'right' }}>
                    <div>{actor.first_seen}</div>
                    <div style={{ fontSize: 11 }}>to {actor.last_seen}</div>
                  </div>
                </div>
              ))}
            </div>
          )}

          <h4 style={{ fontSize: 13, color: '#555', marginTop: 20, marginBottom: 12 }}>Key Locations <span style={{ fontWeight: 400, color: '#9ca3af' }}>(click to copy)</span></h4>
          {entity_evolution.locations.length === 0 ? (
            <p style={{ color: '#888', fontSize: 14 }}>No location data available.</p>
          ) : (
            <div style={{ display: 'grid', gap: 8 }}>
              {entity_evolution.locations.slice(0, 8).map((loc, i) => (
                <div
                  key={i}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    padding: '10px 14px',
                    background: '#f8fafc',
                    borderRadius: 8,
                  }}
                >
                  <div>
                    <CopyableTag text={loc.name} color="#1a1a1a" bg="#f8fafc" />
                    <div style={{ fontSize: 11, color: '#888', marginTop: 6 }}>
                      {loc.event_count} events
                    </div>
                  </div>
                  <div style={{ fontSize: 12, color: '#888' }}>
                    {loc.first_seen} — {loc.last_seen}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Themes Tab */}
      {activeTab === 'themes' && (
        <div>
          {theme_evolution.dominant_themes.length === 0 ? (
            <p style={{ color: '#888', fontSize: 14 }}>No theme data available. GKG data may not be configured.</p>
          ) : (
            <>
              <h4 style={{ fontSize: 13, color: '#555', marginBottom: 12 }}>Dominant Themes <span style={{ fontWeight: 400, color: '#9ca3af' }}>(click to copy)</span></h4>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 20 }}>
                {theme_evolution.dominant_themes.map((t, i) => (
                  <CopyableTag key={i} text={t.theme} color="#2563eb" bg="#eff6ff" />
                ))}
              </div>

              {theme_evolution.emerging_themes.length > 0 && (
                <>
                  <h4 style={{ fontSize: 13, color: '#555', marginBottom: 12 }}>Emerging Themes <span style={{ fontWeight: 400, color: '#9ca3af' }}>(click to copy)</span></h4>
                  <div style={{ display: 'grid', gap: 8, marginBottom: 20 }}>
                    {theme_evolution.emerging_themes.slice(0, 5).map((t, i) => (
                      <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 12px', background: '#f0fdf4', borderRadius: 8 }}>
                        <CopyableTag text={t.theme} color="#166534" bg="#f0fdf4" />
                        <span style={{ fontSize: 12, color: '#16a34a', fontWeight: 600 }}>+{t.growth_ratio}x</span>
                      </div>
                    ))}
                  </div>
                </>
              )}

              {theme_evolution.declining_themes.length > 0 && (
                <>
                  <h4 style={{ fontSize: 13, color: '#555', marginBottom: 12 }}>Declining Themes <span style={{ fontWeight: 400, color: '#9ca3af' }}>(click to copy)</span></h4>
                  <div style={{ display: 'grid', gap: 8 }}>
                    {theme_evolution.declining_themes.slice(0, 5).map((t, i) => (
                      <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 12px', background: '#fef2f2', borderRadius: 8 }}>
                        <CopyableTag text={t.theme} color="#991b1b" bg="#fef2f2" />
                        <span style={{ fontSize: 12, color: '#dc2626', fontWeight: 600 }}>-{t.decline_ratio}x</span>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
