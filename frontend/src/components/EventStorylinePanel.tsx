import { useState } from 'react';
import { GitBranch, Calendar, MapPin, Users, ExternalLink, Hash, ChevronDown, ChevronUp, Star, ArrowRight, ArrowLeft, MessageCircle, Copy, Check } from 'lucide-react';
import type { EventStorylineData, StorylineEventItem } from '../types';

interface Props {
  storyline: EventStorylineData;
}

function getEventTypeColor(label?: string): string {
  if (!label) return '#6b7280';
  const l = label.toLowerCase();
  if (l.includes('conflict') || l.includes('viol') || l.includes('attack') || l.includes('force')) return '#dc2626';
  if (l.includes('cooper') || l.includes('agree') || l.includes('aid')) return '#059669';
  if (l.includes('protest') || l.includes('demonstr')) return '#d97706';
  if (l.includes('threat')) return '#ea580c';
  return '#6b7280';
}

function CopyableText({ text, icon: IconComp }: { text: string; icon?: typeof Copy }) {
  const [copied, setCopied] = useState(false);
  if (!text) return null;
  return (
    <span
      onClick={(e) => {
        e.stopPropagation();
        navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 1200);
      }}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 3,
        cursor: 'pointer',
        userSelect: 'none',
        fontSize: 11,
        color: copied ? '#059669' : '#6b7280',
        background: copied ? '#ecfdf5' : 'transparent',
        padding: '1px 4px',
        borderRadius: 4,
        transition: 'all 0.15s ease',
      }}
      title="Click to copy"
    >
      {IconComp && <IconComp size={10} />}
      {copied ? 'Copied!' : text}
    </span>
  );
}

function EventCard({ event, type }: { event: StorylineEventItem; type: 'seed' | 'preceding' | 'following' | 'reaction' }) {
  const [expanded, setExpanded] = useState(false);

  const typeConfig = {
    seed: { color: '#dc2626', bg: '#fef2f2', label: 'SEED', icon: Star },
    preceding: { color: '#6b7280', bg: '#f9fafb', label: 'BEFORE', icon: ArrowLeft },
    following: { color: '#2563eb', bg: '#eff6ff', label: 'AFTER', icon: ArrowRight },
    reaction: { color: '#7c3aed', bg: '#f5f3ff', label: 'REACTION', icon: MessageCircle },
  };

  const cfg = typeConfig[type];
  const Icon = cfg.icon;
  const headline = event.headline || `${event.Actor1Name || 'Unknown'} vs ${event.Actor2Name || 'Unknown'}`;

  return (
    <div
      style={{
        background: '#fff',
        border: `1px solid ${cfg.color}20`,
        borderLeft: `3px solid ${cfg.color}`,
        borderRadius: 8,
        padding: '12px 14px',
        marginBottom: 8,
        cursor: 'pointer',
        transition: 'all 0.15s ease',
      }}
      onClick={() => setExpanded(!expanded)}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
        <div style={{
          width: 28,
          height: 28,
          borderRadius: '50%',
          background: cfg.bg,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0,
          marginTop: 2,
        }}>
          <Icon size={14} color={cfg.color} />
        </div>

        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
            <span style={{
              fontSize: 10,
              fontWeight: 700,
              color: cfg.color,
              background: cfg.bg,
              padding: '1px 6px',
              borderRadius: 4,
              letterSpacing: 0.5,
            }}>
              {cfg.label}
            </span>
            <span style={{ display: 'flex', alignItems: 'center', gap: 3, fontSize: 11, color: '#888' }}>
              <Calendar size={10} />
              {event.SQLDATE}
            </span>
            {event.NumArticles && (
              <span style={{ fontSize: 11, color: '#9ca3af' }}>
                {event.NumArticles.toLocaleString()} articles
              </span>
            )}
          </div>

          <div style={{ fontSize: 14, fontWeight: 600, color: '#1a1a1a', lineHeight: 1.4, marginBottom: 4 }}>
            {headline}
          </div>

          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px 10px', alignItems: 'center' }}>
            {event.Actor1Name && (
              <CopyableText text={event.Actor1Name} icon={Users} />
            )}
            {event.Actor2Name && (
              <>
                <span style={{ fontSize: 10, color: '#9ca3af' }}>→</span>
                <CopyableText text={event.Actor2Name} icon={Users} />
              </>
            )}
            {event.ActionGeo_FullName && (
              <CopyableText text={event.ActionGeo_FullName} icon={MapPin} />
            )}
            {event.cameo_name && (
              <span
                onClick={(e) => {
                  e.stopPropagation();
                  navigator.clipboard.writeText(event.cameo_name || '');
                }}
                style={{
                  fontSize: 10,
                  fontWeight: 600,
                  color: getEventTypeColor(event.cameo_name),
                  background: `${getEventTypeColor(event.cameo_name)}10`,
                  padding: '1px 6px',
                  borderRadius: 4,
                  cursor: 'pointer',
                  userSelect: 'none',
                }}
                title="Click to copy CAMEO"
              >
                {event.cameo_name}
              </span>
            )}
            {event.GlobalEventID && (
              <CopyableText text={String(event.GlobalEventID)} icon={Hash} />
            )}
            {event.relevance_score !== undefined && (
              <span
                title={`Relevance score: ${event.relevance_score.toFixed(1)}/100`}
                style={{
                  fontSize: 10,
                  fontWeight: 700,
                  color: event.relevance_score >= 70 ? '#dc2626' : event.relevance_score >= 40 ? '#d97706' : '#6b7280',
                  background: event.relevance_score >= 70 ? '#fef2f2' : event.relevance_score >= 40 ? '#fffbeb' : '#f9fafb',
                  padding: '1px 6px',
                  borderRadius: 4,
                }}
              >
                {event.relevance_score.toFixed(0)} pts
              </span>
            )}
            {event.shared_articles !== undefined && event.shared_articles > 0 && (
              <span
                title={`${event.shared_articles} shared article${event.shared_articles > 1 ? 's' : ''}`}
                style={{
                  fontSize: 10,
                  fontWeight: 600,
                  color: '#dc2626',
                  background: '#fef2f2',
                  padding: '1px 6px',
                  borderRadius: 4,
                }}
              >
                {event.shared_articles} article{event.shared_articles > 1 ? 's' : ''}
              </span>
            )}
            {event.theme_overlap !== undefined && event.theme_overlap > 0 && (
              <span
                title={`Theme overlap: ${(event.theme_overlap * 100).toFixed(0)}%`}
                style={{
                  fontSize: 10,
                  fontWeight: 600,
                  color: '#7c3aed',
                  background: '#f5f3ff',
                  padding: '1px 6px',
                  borderRadius: 4,
                }}
              >
                theme {(event.theme_overlap * 100).toFixed(0)}%
              </span>
            )}
            {event.shared_sources !== undefined && event.shared_sources > 0 && event.shared_articles === 0 && (
              <span
                title={`${event.shared_sources} shared news source${event.shared_sources > 1 ? 's' : ''}`}
                style={{
                  fontSize: 10,
                  fontWeight: 600,
                  color: '#059669',
                  background: '#ecfdf5',
                  padding: '1px 6px',
                  borderRadius: 4,
                }}
              >
                {event.shared_sources} source{event.shared_sources > 1 ? 's' : ''}
              </span>
            )}
          </div>

          {expanded && (
            <div style={{ marginTop: 10, paddingTop: 10, borderTop: '1px solid #f0f0f0' }}>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8, marginBottom: 10 }}>
                {event.GoldsteinScale !== undefined && event.GoldsteinScale !== null && (
                  <div style={{ textAlign: 'center', padding: '6px 8px', background: '#f8fafc', borderRadius: 6 }}>
                    <div style={{ fontSize: 10, color: '#888' }}>Goldstein</div>
                    <div style={{ fontSize: 14, fontWeight: 700, color: event.GoldsteinScale < -5 ? '#dc2626' : event.GoldsteinScale > 5 ? '#059669' : '#6b7280' }}>
                      {event.GoldsteinScale.toFixed(1)}
                    </div>
                  </div>
                )}
                {event.AvgTone !== undefined && event.AvgTone !== null && (
                  <div style={{ textAlign: 'center', padding: '6px 8px', background: '#f8fafc', borderRadius: 6 }}>
                    <div style={{ fontSize: 10, color: '#888' }}>Tone</div>
                    <div style={{ fontSize: 14, fontWeight: 700, color: event.AvgTone < 0 ? '#dc2626' : '#059669' }}>
                      {event.AvgTone > 0 ? '+' : ''}{event.AvgTone.toFixed(2)}
                    </div>
                  </div>
                )}
                {event.NumArticles && (
                  <div style={{ textAlign: 'center', padding: '6px 8px', background: '#f8fafc', borderRadius: 6 }}>
                    <div style={{ fontSize: 10, color: '#888' }}>Articles</div>
                    <div style={{ fontSize: 14, fontWeight: 700, color: '#2563eb' }}>{event.NumArticles.toLocaleString()}</div>
                  </div>
                )}
              </div>

              {event.SOURCEURL && (
                <a
                  href={event.SOURCEURL}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={(e) => e.stopPropagation()}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 4,
                    fontSize: 12,
                    color: '#2563eb',
                    textDecoration: 'none',
                    padding: '4px 10px',
                    background: '#eff6ff',
                    borderRadius: 6,
                  }}
                >
                  <ExternalLink size={12} />
                  Read Source Article
                </a>
              )}
            </div>
          )}
        </div>

        <div style={{ color: '#ccc', flexShrink: 0 }}>
          {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </div>
      </div>
    </div>
  );
}

export default function EventStorylinePanel({ storyline }: Props) {
  if (!storyline) return null;

  const { seed, preceding, following, reactions } = storyline;
  const hasContent = seed || preceding.length > 0 || following.length > 0 || reactions.length > 0;
  if (!hasContent) return null;

  return (
    <div className="panel" style={{ background: '#fff', border: '1px solid #e2e8f0' }}>
      <h3 style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16, fontSize: 15, fontWeight: 700, color: '#1a1a1a' }}>
        <GitBranch size={18} color="#dc2626" />
        Event Storyline
        <span style={{ fontSize: 11, color: '#888', fontWeight: 400, marginLeft: 8 }}>
          Chronological event chain with source links
        </span>
      </h3>

      {/* Preceding events */}
      {preceding.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <h4 style={{ fontSize: 11, fontWeight: 700, color: '#6b7280', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 8 }}>
            Preceding Events ({preceding.length})
          </h4>
          {preceding.map((evt, i) => (
            <EventCard key={`pre-${i}`} event={evt} type="preceding" />
          ))}
        </div>
      )}

      {/* Seed event */}
      {seed && (
        <div style={{ marginBottom: 12 }}>
          <h4 style={{ fontSize: 11, fontWeight: 700, color: '#dc2626', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 8 }}>
            Seed Event
          </h4>
          <EventCard event={seed} type="seed" />
        </div>
      )}

      {/* Following events */}
      {following.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <h4 style={{ fontSize: 11, fontWeight: 700, color: '#2563eb', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 8 }}>
            Following Events ({following.length})
          </h4>
          {following.map((evt, i) => (
            <EventCard key={`fol-${i}`} event={evt} type="following" />
          ))}
        </div>
      )}

      {/* Reactions */}
      {reactions.length > 0 && (
        <div>
          <h4 style={{ fontSize: 11, fontWeight: 700, color: '#7c3aed', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 8 }}>
            International Reactions ({reactions.length})
          </h4>
          {reactions.map((evt, i) => (
            <EventCard key={`reac-${i}`} event={evt} type="reaction" />
          ))}
        </div>
      )}
    </div>
  );
}
