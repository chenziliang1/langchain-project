import { useState } from 'react';
import { Newspaper, ExternalLink, CheckCircle, AlertCircle, Database, ChevronDown, ChevronUp } from 'lucide-react';
import type { NewsCoverageData } from '../types';

interface Props {
  coverage: NewsCoverageData;
}

function getStatusIcon(status: string) {
  if (status === 'success') return <CheckCircle size={14} color="#059669" />;
  if (status === 'chroma_fallback') return <Database size={14} color="#2563eb" />;
  return <AlertCircle size={14} color="#dc2626" />;
}

function getStatusLabel(status: string): string {
  if (status === 'success') return 'Fetched';
  if (status === 'chroma_fallback') return 'From KB';
  if (status === 'cached_success') return 'Cached';
  if (status.startsWith('http_')) return `HTTP ${status.split('_')[1]}`;
  if (status === 'timeout') return 'Timeout';
  if (status === 'too_large') return 'Too Large';
  if (status === 'too_short') return 'No Content';
  return status;
}

function SourceCard({ source, index }: { source: any; index: number }) {
  const [expanded, setExpanded] = useState(false);
  const hasFullContent = !!(source.content_full || source.content_snippet);
  const displayContent = expanded
    ? (source.content_full || source.content_snippet || '')
    : (source.content_snippet || source.content_full || '');

  return (
    <div
      style={{
        padding: '12px 16px',
        background: '#f8fafc',
        borderRadius: 8,
        border: '1px solid #e2e8f0',
      }}
    >
      {/* Header row */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        <span style={{ fontSize: 11, color: '#888', fontWeight: 500, minWidth: 20 }}>
          {index + 1}.
        </span>
        {getStatusIcon(source.fetch_status)}
        <span style={{ fontSize: 11, color: '#888', fontWeight: 500 }}>
          {getStatusLabel(source.fetch_status)}
        </span>
        {source.url && (
          <a
            href={source.url}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              marginLeft: 'auto',
              display: 'flex',
              alignItems: 'center',
              gap: 4,
              fontSize: 12,
              color: '#2563eb',
              textDecoration: 'none',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <ExternalLink size={12} />
            Source
          </a>
        )}
      </div>

      {/* Title */}
      {source.title && (
        <div style={{ fontSize: 13, fontWeight: 600, color: '#1a1a1a', marginBottom: 8, paddingLeft: 28 }}>
          {source.title}
        </div>
      )}

      {/* Content */}
      {displayContent && (
        <div style={{ paddingLeft: 28 }}>
          <p
            style={{
              fontSize: 13,
              color: '#4b5563',
              lineHeight: 1.7,
              margin: 0,
              whiteSpace: 'pre-wrap',
            }}
          >
            {displayContent}
          </p>
          {hasFullContent && source.content_full && source.content_full.length > (source.content_snippet?.length || 0) && (
            <button
              onClick={() => setExpanded(!expanded)}
              style={{
                marginTop: 8,
                fontSize: 12,
                color: '#2563eb',
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: 4,
                padding: 0,
              }}
            >
              {expanded ? (
                <>
                  <ChevronUp size={14} /> Show less
                </>
              ) : (
                <>
                  <ChevronDown size={14} /> Read full article
                </>
              )}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

export default function NewsCoveragePanel({ coverage }: Props) {
  const sources = coverage.sources || [];
  const hasContent = coverage.has_content;

  return (
    <div className="panel">
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
        <Newspaper size={18} color="#2563eb" />
        <h3 style={{ fontSize: 16, fontWeight: 700, color: '#1a1a1a', margin: 0 }}>
          News Coverage
        </h3>
        <span
          style={{
            fontSize: 11,
            fontWeight: 600,
            color: hasContent ? '#059669' : '#dc2626',
            background: hasContent ? '#f0fdf4' : '#fef2f2',
            padding: '2px 8px',
            borderRadius: 10,
            marginLeft: 'auto',
          }}
        >
          {coverage.source_count} source{coverage.source_count !== 1 ? 's' : ''}
        </span>
      </div>

      {coverage.headline && (
        <p style={{ fontSize: 14, fontWeight: 600, color: '#374151', marginBottom: 12 }}>
          {coverage.headline}
        </p>
      )}

      {/* Source list */}
      <div style={{ display: 'grid', gap: 10 }}>
        {sources.map((source, i) => (
          <SourceCard key={i} source={source} index={i} />
        ))}
      </div>

      {sources.length === 0 && (
        <p style={{ fontSize: 13, color: '#888', textAlign: 'center', padding: '20px 0' }}>
          No news sources available for this event.
        </p>
      )}
    </div>
  );
}
