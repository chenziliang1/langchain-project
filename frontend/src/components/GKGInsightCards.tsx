import { useState } from 'react';
import { Network, Tag, TrendingUp, AlertCircle, BarChart3 } from 'lucide-react';
import type { GKGInsightData } from '../types';

function CopyableTag({ text, color, bg, count }: { text: string; color: string; bg: string; count?: number }) {
  const [copied, setCopied] = useState(false);
  return (
    <span
      onClick={() => {
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
        display: 'inline-flex',
        alignItems: 'center',
        gap: 4,
        cursor: 'pointer',
        userSelect: 'none',
        transition: 'all 0.15s ease',
        border: `1px solid ${copied ? '#a7f3d0' : 'transparent'}`,
      }}
      title="Click to copy"
    >
      {copied ? 'Copied!' : text}
      {count !== undefined && !copied && (
        <span style={{ fontSize: 10, opacity: 0.6 }}>({count})</span>
      )}
    </span>
  );
}

interface Props {
  insights: GKGInsightData;
}

export default function GKGInsightCards({ insights }: Props) {
  const cooccur = insights.cooccurring;
  const themes = insights.themes;
  const toneTimeline = insights.tone_timeline || [];

  const hasAnyData = cooccur || themes || toneTimeline.length > 0;

  if (!hasAnyData) {
    return (
      <div className="panel" style={{ background: '#fafafa' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
          <Network size={18} color="#888" />
          <h3 style={{ fontSize: 16, fontWeight: 700, color: '#888', margin: 0 }}>
            GKG Insights
          </h3>
        </div>
        <p style={{ fontSize: 13, color: '#aaa', margin: 0 }}>
          <AlertCircle size={14} style={{ display: 'inline', marginRight: 4, verticalAlign: 'text-bottom' }} />
          GKG BigQuery data not available. Configure GCP credentials to enable media knowledge graph insights.
        </p>
      </div>
    );
  }

  return (
    <div className="panel">
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
        <Network size={18} color="#7c3aed" />
        <h3 style={{ fontSize: 16, fontWeight: 700, color: '#1a1a1a', margin: 0 }}>
          Media Knowledge Graph
        </h3>
      </div>

      {/* Related People */}
      {cooccur && cooccur.top_persons && cooccur.top_persons.length > 0 && (
        <div style={{ marginBottom: 20 }}>
          <h4 style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: '#555', marginBottom: 10 }}>
            <TrendingUp size={14} color="#7c3aed" />
            Related People in Media <span style={{ fontWeight: 400, color: '#9ca3af', fontSize: 11 }}>(click to copy)</span>
          </h4>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {cooccur.top_persons.slice(0, 10).map((p: any, i: number) => (
              <CopyableTag key={i} text={p.name} color="#7c3aed" bg="#f5f3ff" count={p.count} />
            ))}
          </div>
        </div>
      )}

      {/* Related Organizations */}
      {cooccur && cooccur.top_organizations && cooccur.top_organizations.length > 0 && (
        <div style={{ marginBottom: 20 }}>
          <h4 style={{ fontSize: 13, color: '#555', marginBottom: 10 }}>
            Related Organizations <span style={{ fontWeight: 400, color: '#9ca3af', fontSize: 11 }}>(click to copy)</span>
          </h4>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {cooccur.top_organizations.slice(0, 6).map((o: any, i: number) => (
              <CopyableTag key={i} text={o.name} color="#555" bg="#f3f4f6" />
            ))}
          </div>
        </div>
      )}

      {/* Themes */}
      {themes && themes.top_themes && themes.top_themes.length > 0 && (
        <div style={{ marginBottom: 20 }}>
          <h4 style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: '#555', marginBottom: 10 }}>
            <Tag size={14} color="#059669" />
            Media Themes <span style={{ fontWeight: 400, color: '#9ca3af', fontSize: 11 }}>(click to copy)</span>
          </h4>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {themes.top_themes.slice(0, 12).map((t: any, i: number) => (
              <CopyableTag key={i} text={t.theme} color="#059669" bg="#f0fdf4" count={t.count} />
            ))}
          </div>
        </div>
      )}

      {/* Tone Timeline with numeric values */}
      {toneTimeline.length > 0 && (
        <div>
          <h4 style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: '#555', marginBottom: 10 }}>
            <BarChart3 size={14} color="#2563eb" />
            Media Tone Trend
          </h4>
          
          {/* Tone data table */}
          <div style={{ marginBottom: 12, overflow: 'hidden', borderRadius: 8, border: '1px solid #e2e8f0' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
              <thead>
                <tr style={{ background: '#f8fafc' }}>
                  <th style={{ padding: '8px 12px', textAlign: 'left', color: '#888', fontWeight: 600, borderBottom: '1px solid #e2e8f0' }}>Date</th>
                  <th style={{ padding: '8px 12px', textAlign: 'center', color: '#888', fontWeight: 600, borderBottom: '1px solid #e2e8f0' }}>Tone</th>
                  <th style={{ padding: '8px 12px', textAlign: 'center', color: '#888', fontWeight: 600, borderBottom: '1px solid #e2e8f0' }}>Mentions</th>
                </tr>
              </thead>
              <tbody>
                {toneTimeline.map((t: any, i: number) => {
                  const tone = t.avg_tone || t.tone || 0;
                  const mentions = t.mention_count || t.mentions || 0;
                  const isNegative = tone < 0;
                  return (
                    <tr key={i} style={{ borderBottom: i < toneTimeline.length - 1 ? '1px solid #f1f5f9' : 'none' }}>
                      <td style={{ padding: '8px 12px', color: '#4b5563' }}>{t.date}</td>
                      <td style={{ padding: '8px 12px', textAlign: 'center' }}>
                        <span style={{
                          fontWeight: 700,
                          color: isNegative ? '#dc2626' : '#059669',
                          background: isNegative ? '#fef2f2' : '#f0fdf4',
                          padding: '2px 8px',
                          borderRadius: 10,
                          fontSize: 11,
                        }}>
                          {tone > 0 ? '+' : ''}{tone.toFixed(2)}
                        </span>
                      </td>
                      <td style={{ padding: '8px 12px', textAlign: 'center', color: '#6b7280', fontSize: 11 }}>
                        {mentions.toLocaleString()}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Visual bar chart */}
          <div style={{ display: 'flex', alignItems: 'flex-end', gap: 4, height: 60, padding: '8px 0' }}>
            {toneTimeline.map((t: any, i: number) => {
              const tone = t.avg_tone || t.tone || 0;
              const height = Math.min(Math.abs(tone) * 20 + 10, 50);
              const color = tone < 0 ? '#dc2626' : '#059669';
              return (
                <div key={i} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', flex: 1 }}>
                  <div
                    style={{
                      width: '100%',
                      height: `${height}px`,
                      background: color,
                      borderRadius: '4px 4px 0 0',
                      opacity: 0.7,
                      minWidth: 20,
                    }}
                    title={`${t.date}: tone=${tone.toFixed(2)}, mentions=${t.mention_count || t.mentions || 0}`}
                  />
                  <span style={{ fontSize: 9, color: '#aaa', marginTop: 2 }}>
                    {t.date?.slice(5) || ''}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
