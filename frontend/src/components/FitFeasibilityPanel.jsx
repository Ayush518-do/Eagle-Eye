import React from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Info,
  Layers,
  HelpCircle,
} from 'lucide-react';

export default function FitFeasibilityPanel({ report, loading, error, tag }) {
  if (loading) {
    return (
      <div className="panel fit-panel" style={{ marginTop: '16px', padding: '20px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--color-navy)' }}>
          <Layers size={18} className="animate-spin" />
          <span style={{ fontWeight: 600 }}>Analyzing DIN-rail slot and replacement feasibility…</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="panel fit-panel" style={{ marginTop: '16px', padding: '16px', borderLeft: '4px solid var(--color-status-mismatch)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--color-status-mismatch)' }}>
          <AlertTriangle size={18} />
          <span style={{ fontWeight: 600 }}>Fit Feasibility Assessment Unavailable</span>
        </div>
        <p style={{ fontSize: '12px', color: 'var(--color-text-muted)', marginTop: '4px' }}>{error}</p>
      </div>
    );
  }

  if (!report || !report.candidates || report.candidates.length === 0) {
    return null;
  }

  const slotLabel = report.slot_status === 'unoccupied_verified'
    ? 'Verified Unoccupied Slot'
    : report.slot_status === 'unoccupied_inconclusive'
    ? 'Unoccupied (Inconclusive Lighting/Sharpness)'
    : report.slot_status;

  const getBadgeStyle = (classification) => {
    switch (classification) {
      case 'Compatible':
        return {
          bg: 'var(--color-status-approved-bg)',
          color: 'var(--color-status-approved)',
          border: 'var(--color-status-approved)',
          icon: <CheckCircle2 size={13} />,
        };
      case 'Potentially compatible':
        return {
          bg: 'var(--color-status-review-bg)',
          color: 'var(--color-status-review)',
          border: 'var(--color-status-review)',
          icon: <AlertTriangle size={13} />,
        };
      case 'Incompatible':
        return {
          bg: 'var(--color-status-mismatch-bg)',
          color: 'var(--color-status-mismatch)',
          border: 'var(--color-status-mismatch)',
          icon: <XCircle size={13} />,
        };
      default:
        return {
          bg: 'var(--color-status-inconclusive-bg)',
          color: 'var(--color-status-inconclusive)',
          border: 'var(--color-status-inconclusive)',
          icon: <HelpCircle size={13} />,
        };
    }
  };

  return (
    <div className="panel fit-feasibility-section" style={{ marginTop: '16px' }}>
      {/* Panel Header */}
      <div className="panel-header" style={{ marginBottom: '14px', alignItems: 'flex-start' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Layers size={18} color="var(--color-navy)" />
            <h3 className="panel-title" style={{ fontSize: '15px' }}>
              Slot Fit Feasibility & Replacement Analysis
            </h3>
          </div>
          <p style={{ fontSize: '12px', color: 'var(--color-text-muted)', marginTop: '4px' }}>
            Position <span className="mono" style={{ fontWeight: 600 }}>{tag || report.tag}</span> · Type: <span style={{ textTransform: 'uppercase' }}>{report.component_type}</span> · {slotLabel}
          </p>
        </div>
        <div style={{ textAlign: 'right', fontSize: '11px', color: 'var(--color-text-muted)' }}>
          <div>Mounting: <strong>{report.mounting_type}</strong></div>
          {report.available_width_mm && (
            <div>Envelope: <strong>{report.available_width_mm}mm W × {report.available_height_mm || '—'}mm H</strong></div>
          )}
        </div>
      </div>

      {/* Candidate Components Cards */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
        {report.candidates.map((cand, idx) => {
          const badge = getBadgeStyle(cand.classification);
          return (
            <div
              key={idx}
              className="fit-candidate-card"
              style={{
                backgroundColor: 'var(--color-surface-subtle)',
                border: '1px solid var(--color-border)',
                borderLeft: `4px solid ${badge.border}`,
                borderRadius: 'var(--radius-sm)',
                padding: '12px 14px',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px' }}>
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ fontWeight: 600, color: 'var(--color-navy)' }}>{cand.model_name}</span>
                    <span className="mono" style={{ fontSize: '11px', color: 'var(--color-text-muted)' }}>
                      ({cand.candidate_part_number})
                    </span>
                  </div>
                  <div style={{ fontSize: '12px', color: 'var(--color-text-muted)' }}>
                    Manufacturer: <strong>{cand.manufacturer}</strong>
                  </div>
                </div>

                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '5px',
                    padding: '3px 8px',
                    borderRadius: 'var(--radius-xs)',
                    fontSize: '11px',
                    fontWeight: 600,
                    backgroundColor: badge.bg,
                    color: badge.color,
                  }}
                >
                  {badge.icon}
                  <span>{cand.classification}</span>
                </div>
              </div>

              {/* Rationale */}
              {cand.reasons && cand.reasons.length > 0 && (
                <div style={{ fontSize: '12px', marginTop: '6px', color: 'var(--color-text-main)' }}>
                  {cand.reasons.join(' ')}
                </div>
              )}

              {/* Evaluated Constraints Checklist */}
              {cand.evaluated_constraints && (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginTop: '8px' }}>
                  {Object.entries(cand.evaluated_constraints).map(([k, v]) => {
                    const isOk = v.startsWith('OK');
                    const isPotential = v.includes('POTENTIAL');
                    const chipColor = isOk
                      ? 'var(--color-status-approved)'
                      : isPotential
                      ? 'var(--color-status-review)'
                      : 'var(--color-status-mismatch)';
                    const chipBg = isOk
                      ? 'var(--color-status-approved-bg)'
                      : isPotential
                      ? 'var(--color-status-review-bg)'
                      : 'var(--color-status-mismatch-bg)';
                    return (
                      <span
                        key={k}
                        style={{
                          fontSize: '11px',
                          padding: '2px 6px',
                          borderRadius: '4px',
                          backgroundColor: chipBg,
                          color: chipColor,
                          fontWeight: 500,
                        }}
                      >
                        {v}
                      </span>
                    );
                  })}
                </div>
              )}

              {/* Uncertainty Notes */}
              {cand.uncertainty_notes && cand.uncertainty_notes.length > 0 && (
                <div style={{ fontSize: '11px', color: 'var(--color-text-muted)', marginTop: '6px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <Info size={12} />
                  <span>{cand.uncertainty_notes.join('; ')}</span>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Mandatory Engineering Safety Disclaimer Banner */}
      <div
        className="notice"
        style={{
          marginTop: '12px',
          padding: '10px 12px',
          backgroundColor: '#FFFBEB',
          borderColor: '#FDE68A',
          color: '#92400E',
          fontSize: '11px',
          lineHeight: 1.4,
          borderRadius: 'var(--radius-sm)',
        }}
      >
        <AlertTriangle size={15} style={{ flexShrink: 0, marginTop: '2px' }} />
        <div>
          <strong>Safety Note:</strong> Physical fit feasibility check only. Physical fit does{' '}
          <strong>not</strong> imply electrical safety, thermal suitability, interrupting rating, or protection coordination.
          All replacement components must be verified and approved by a qualified electrical engineer prior to installation.
        </div>
      </div>
    </div>
  );
}
