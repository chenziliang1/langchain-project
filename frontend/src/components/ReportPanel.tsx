import { FileText, Lightbulb } from 'lucide-react';
import type { ReportResult } from '../types';

interface Props {
  report: ReportResult;
  title?: string;
}

export default function ReportPanel({ report, title = 'AI Report' }: Props) {
  if (!report) return null;

  return (
    <div className="panel" style={{ background: '#fafafa' }}>
      <h3 style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <FileText size={18} color="#2563eb" />
        {title}
      </h3>

      {report.summary && (
        <div style={{ lineHeight: 1.7, color: '#374151', fontSize: 14, marginBottom: 16 }}>
          {report.summary.split('\n').map((para, i) => (
            <p key={i} style={{ marginBottom: 8 }}>{para}</p>
          ))}
        </div>
      )}

      {report.key_findings && report.key_findings.length > 0 && (
        <div>
          <h4 style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: '#555', marginBottom: 8 }}>
            <Lightbulb size={14} color="#f59e0b" />
            Key Findings
          </h4>
          <ul style={{ paddingLeft: 18, margin: 0 }}>
            {report.key_findings.map((finding, i) => (
              <li key={i} style={{ marginBottom: 6, fontSize: 13, color: '#4b5563', lineHeight: 1.5 }}>
                {finding}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
