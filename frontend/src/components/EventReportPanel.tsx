import { FileText, Lightbulb, BookOpen, Network, CalendarDays, GitBranch, Activity } from 'lucide-react';
import type { EnhancedReportResult, EventItem } from '../types';
import EventContextPanel from './EventContextPanel';
import GKGInsightCards from './GKGInsightCards';
import ActorActivityPanel from './ActorActivityPanel';
import EventStorylinePanel from './EventStorylinePanel';

interface Props {
  report: EnhancedReportResult;
  event?: EventItem;
}

export default function EventReportPanel({ report, event }: Props) {
  if (!report) return null;

  const hasEventContext = !!report.event_context;
  const hasGKG = !!report.gkg_insights;
  const hasActorActivity = !!report.actor_activity && report.actor_activity.length > 0;
  const hasEventStoryline = !!report.event_storyline;

  return (
    <div style={{ animation: 'fadeIn 0.5s ease' }}>
      {/* Report Header */}
      <div className="panel" style={{ background: '#fafafa' }}>
        <h3 style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
          <FileText size={20} color="#2563eb" />
          <span style={{ fontSize: 18, fontWeight: 700, color: '#1a1a1a' }}>
            Event Report
          </span>
          {report.generated_at && (
            <span style={{ fontSize: 11, color: '#aaa', marginLeft: 'auto' }}>
              Generated {new Date(report.generated_at).toLocaleString()}
            </span>
          )}
        </h3>

        {/* Summary */}
        {report.summary && (
          <div style={{ lineHeight: 1.7, color: '#374151', fontSize: 14, marginBottom: 16 }}>
            {report.summary.split('\n').map((para, i) => (
              <p key={i} style={{ marginBottom: 10 }}>{para}</p>
            ))}
          </div>
        )}

        {/* Key Findings */}
        {report.key_findings && report.key_findings.length > 0 && (
          <div>
            <h4 style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: '#555', marginBottom: 10 }}>
              <Lightbulb size={14} color="#f59e0b" />
              Key Findings
            </h4>
            <ul style={{ paddingLeft: 18, margin: 0 }}>
              {report.key_findings.map((finding, i) => (
                <li key={i} style={{ marginBottom: 8, fontSize: 13, color: '#4b5563', lineHeight: 1.6 }}>
                  {finding}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Data Source Indicators */}
        <div style={{ display: 'flex', gap: 12, marginTop: 16, paddingTop: 12, borderTop: '1px solid #e2e8f0' }}>
          {hasEventStoryline && (
            <span style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: '#dc2626', background: '#fef2f2', padding: '4px 10px', borderRadius: 10 }}>
              <GitBranch size={12} />
              Event Storyline
            </span>
          )}
          {hasEventContext && (
            <span style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: '#2563eb', background: '#eff6ff', padding: '4px 10px', borderRadius: 10 }}>
              <BookOpen size={12} />
              Context Analysis
            </span>
          )}
          {hasActorActivity && (
            <span style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: '#059669', background: '#ecfdf5', padding: '4px 10px', borderRadius: 10 }}>
              <Activity size={12} />
              Actor Activity
            </span>
          )}
          {hasGKG && (
            <span style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: '#7c3aed', background: '#f5f3ff', padding: '4px 10px', borderRadius: 10 }}>
              <Network size={12} />
              GKG Insights
            </span>
          )}
        </div>
      </div>

      {/* Event Storyline */}
      {hasEventStoryline && report.event_storyline && (
        <div style={{ marginTop: 16 }}>
          <EventStorylinePanel storyline={report.event_storyline} />
        </div>
      )}

      {/* Event Context (Entities & Themes) */}
      {hasEventContext && report.event_context && (
        <div style={{ marginTop: 16 }}>
          <EventContextPanel context={report.event_context} />
        </div>
      )}

      {/* Actor Activity Overview */}
      {hasActorActivity && report.actor_activity && (
        <div style={{ marginTop: 16 }}>
          <ActorActivityPanel
            activity={report.actor_activity}
            actorName={event?.Actor1Name || report.event_storyline?.seed?.Actor1Name}
          />
        </div>
      )}

      {/* GKG Insights */}
      {report.gkg_insights && (
        <div style={{ marginTop: 16 }}>
          <GKGInsightCards insights={report.gkg_insights} />
        </div>
      )}
    </div>
  );
}
