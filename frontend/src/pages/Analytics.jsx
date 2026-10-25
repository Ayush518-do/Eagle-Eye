import React, { useState, useEffect } from 'react';
import {
  BarChart3,
  Calendar,
  CheckCircle2,
  AlertTriangle,
  Clock,
  Layers,
  Filter,
  RefreshCw,
  Tag,
} from 'lucide-react';
import { getAnalytics } from '../api.js';
import StatusBadge from '../components/StatusBadge.jsx';
import SyntheticBanner from '../components/SyntheticBanner.jsx';
import { SkeletonCard, SkeletonRow } from '../components/Skeleton.jsx';

export default function Analytics() {
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [fromDate, setFromDate] = useState('2026-10-01');
  const [toDate, setToDate] = useState('2026-10-31');
  const [isSynthetic, setIsSynthetic] = useState(false);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await getAnalytics(fromDate, toDate);
      setData(res);
      setIsSynthetic(false);
    } catch (err) {
      setError(err.message || 'Could not load analytics from server.');
      setData(null);
      setIsSynthetic(false);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const overall = data?.overall || { pass: 0, review_required: 0, mismatch_detected: 0 };
  const findingsByType = data?.findings_by_type || {};
  const topFlagged = data?.top_flagged_tags || [];
  const reviewOutcomes = data?.review_outcomes || { confirmed_by_reviewer: 0, rejected_by_reviewer: 0, pending: 0 };

  // Calculate highest count for findings by type bar chart
  const maxFindingCount = Math.max(...Object.values(findingsByType), 1);

  const formatFindingType = (t) => {
    return t
      .split('_')
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
      .join(' ');
  };

  return (
    <div>
      {/* Synthetic Banner */}
      {isSynthetic && (
        <SyntheticBanner onDismiss={() => setIsSynthetic(false)} />
      )}

      {/* Header */}
      <div className="page-header">
        <div>
          <div className="eyebrow">QUALITY METRICS & AUDIT INTELLIGENCE</div>
          <h1 className="page-title">Inspection Analytics</h1>
          <p className="page-desc">
            Aggregated audit trends, component defect distributions, and reviewer sign-off statistics.
          </p>
        </div>

        {/* Date Filter Bar */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', background: '#fff', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-sm)', padding: '4px 8px' }}>
            <Calendar size={14} color="var(--color-text-muted)" />
            <input
              type="date"
              value={fromDate}
              onChange={(e) => setFromDate(e.target.value)}
              style={{ border: 'none', fontSize: '12px', background: 'transparent' }}
              aria-label="From Date"
            />
            <span style={{ color: 'var(--color-border)' }}>–</span>
            <input
              type="date"
              value={toDate}
              onChange={(e) => setToDate(e.target.value)}
              style={{ border: 'none', fontSize: '12px', background: 'transparent' }}
              aria-label="To Date"
            />
          </div>
          <button type="button" className="btn btn-secondary btn-sm" onClick={loadData}>
            <RefreshCw size={12} />
            <span>Apply</span>
          </button>
        </div>
      </div>

      {error && (
        <div className="panel" style={{ borderLeft: '4px solid var(--color-status-mismatch)', marginBottom: '16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <AlertTriangle size={18} color="var(--color-status-mismatch)" />
            <span style={{ fontSize: '13px', color: 'var(--color-text-main)' }}>{error}</span>
          </div>
        </div>
      )}

      {loading ? (
        <div>
          <SkeletonCard height={120} />
          <SkeletonRow count={4} height={50} />
        </div>
      ) : (
        <>
          {/* KPI Cards Row */}
          <div className="metrics-grid">
            <div className="metric-card m-b">
              <div className="metric-label">
                <span>Total Inspections</span>
                <Layers size={16} color="var(--color-navy)" />
              </div>
              <div className="metric-value">{data?.inspections ?? 0}</div>
              <div className="metric-sub">Completed automated runs</div>
            </div>

            <div className="metric-card m-p">
              <div className="metric-label">
                <span>Verified Clean Pass</span>
                <CheckCircle2 size={16} color="var(--color-status-approved)" />
              </div>
              <div className="metric-value" style={{ color: 'var(--color-status-approved)' }}>
                {overall.pass}
              </div>
              <div className="metric-sub">Zero discrepancies detected</div>
            </div>

            <div className="metric-card m-r">
              <div className="metric-label">
                <span>Review Required</span>
                <Clock size={16} color="var(--color-status-review)" />
              </div>
              <div className="metric-value" style={{ color: 'var(--color-status-review)' }}>
                {overall.review_required}
              </div>
              <div className="metric-sub">Uncertain readings / order changes</div>
            </div>

            <div className="metric-card m-f">
              <div className="metric-label">
                <span>Mismatch Detected</span>
                <AlertTriangle size={16} color="var(--color-status-mismatch)" />
              </div>
              <div className="metric-value" style={{ color: 'var(--color-status-mismatch)' }}>
                {overall.mismatch_detected}
              </div>
              <div className="metric-sub">Hardware rating or BOM conflicts</div>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.2fr) minmax(0, 1fr)', gap: '20px', marginBottom: '24px' }}>
            {/* Plain CSS Bar Chart: Findings by Type */}
            <div className="panel" style={{ margin: 0 }}>
              <div className="panel-header">
                <h2 className="panel-title">Findings by Discrepancy Type</h2>
                <span style={{ fontSize: '12px', color: 'var(--color-text-muted)' }}>Pure CSS Bars</span>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', paddingTop: '8px' }}>
                {Object.entries(findingsByType).map(([typeKey, count]) => {
                  const pct = (count / maxFindingCount) * 100;
                  const isRed = typeKey === 'rating_mismatch' || typeKey === 'type_mismatch';
                  const isBlue = typeKey === 'order_changed';
                  const isAmber = typeKey === 'missing' || typeKey === 'unexpected';

                  const barColor = isRed
                    ? 'var(--color-status-mismatch)'
                    : isBlue
                    ? '#0969da'
                    : isAmber
                    ? 'var(--color-status-review)'
                    : 'var(--color-navy)';

                  return (
                    <div key={typeKey}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', marginBottom: '4px' }}>
                        <strong>{formatFindingType(typeKey)}</strong>
                        <span className="mono" style={{ fontWeight: 600 }}>{count} occurrences</span>
                      </div>
                      <div style={{ width: '100%', height: '18px', backgroundColor: 'var(--color-surface-subtle)', borderRadius: 'var(--radius-sm)', overflow: 'hidden' }}>
                        <div
                          style={{
                            width: `${Math.max(pct, count > 0 ? 5 : 0)}%`,
                            height: '100%',
                            backgroundColor: barColor,
                            borderRadius: 'var(--radius-sm)',
                            transition: 'width 0.4s ease',
                          }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Review Outcomes Breakdown */}
            <div className="panel" style={{ margin: 0 }}>
              <div className="panel-header">
                <h2 className="panel-title">Reviewer Sign-off Outcomes</h2>
                <span style={{ fontSize: '12px', color: 'var(--color-text-muted)' }}>Human QA</span>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', paddingTop: '8px' }}>
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', marginBottom: '4px' }}>
                    <span style={{ color: 'var(--color-status-approved)', fontWeight: 600 }}>Confirmed by Reviewer</span>
                    <span className="mono">{reviewOutcomes.confirmed_by_reviewer}</span>
                  </div>
                  <div style={{ width: '100%', height: '12px', backgroundColor: 'var(--color-surface-subtle)', borderRadius: '2px', overflow: 'hidden' }}>
                    <div
                      style={{
                        width: `${(reviewOutcomes.confirmed_by_reviewer / (data?.inspections || 1)) * 100}%`,
                        height: '100%',
                        backgroundColor: 'var(--color-status-approved)',
                      }}
                    />
                  </div>
                </div>

                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', marginBottom: '4px' }}>
                    <span style={{ color: 'var(--color-status-mismatch)', fontWeight: 600 }}>Rejected by Reviewer</span>
                    <span className="mono">{reviewOutcomes.rejected_by_reviewer}</span>
                  </div>
                  <div style={{ width: '100%', height: '12px', backgroundColor: 'var(--color-surface-subtle)', borderRadius: '2px', overflow: 'hidden' }}>
                    <div
                      style={{
                        width: `${(reviewOutcomes.rejected_by_reviewer / (data?.inspections || 1)) * 100}%`,
                        height: '100%',
                        backgroundColor: 'var(--color-status-mismatch)',
                      }}
                    />
                  </div>
                </div>

                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', marginBottom: '4px' }}>
                    <span style={{ color: 'var(--color-text-muted)', fontWeight: 600 }}>Pending Review</span>
                    <span className="mono">{reviewOutcomes.pending}</span>
                  </div>
                  <div style={{ width: '100%', height: '12px', backgroundColor: 'var(--color-surface-subtle)', borderRadius: '2px', overflow: 'hidden' }}>
                    <div
                      style={{
                        width: `${(reviewOutcomes.pending / (data?.inspections || 1)) * 100}%`,
                        height: '100%',
                        backgroundColor: 'var(--color-border)',
                      }}
                    />
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Top Flagged Tags Table */}
          <div className="panel">
            <div className="panel-header">
              <h2 className="panel-title">Top Flagged Component Tags</h2>
              <p className="page-desc" style={{ fontSize: '12px' }}>
                Components triggering the highest frequency of inspection flags across production runs.
              </p>
            </div>

            <div className="table-container">
              <table className="table" aria-label="Top Flagged Tags Table">
                <thead>
                  <tr>
                    <th>Component Tag</th>
                    <th>Type</th>
                    <th>Discrepancy Count</th>
                    <th>Flag Ratio</th>
                  </tr>
                </thead>
                <tbody>
                  {topFlagged.map((item) => (
                    <tr key={item.tag}>
                      <td className="mono" style={{ fontWeight: 700, color: 'var(--color-navy)' }}>
                        {item.tag}
                      </td>
                      <td style={{ textTransform: 'uppercase', fontSize: '11px', color: 'var(--color-text-muted)' }}>
                        {item.component_type || 'MCB'}
                      </td>
                      <td>
                        <strong className="mono" style={{ color: 'var(--color-status-mismatch)' }}>
                          {item.count} flags
                        </strong>
                      </td>
                      <td style={{ width: '220px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <div style={{ flex: 1, height: '8px', backgroundColor: 'var(--color-surface-subtle)', borderRadius: '2px', overflow: 'hidden' }}>
                            <div
                              style={{
                                width: `${(item.count / (topFlagged[0]?.count || 1)) * 100}%`,
                                height: '100%',
                                backgroundColor: 'var(--color-status-mismatch)',
                              }}
                            />
                          </div>
                          <span className="mono" style={{ fontSize: '11px', color: 'var(--color-text-muted)' }}>
                            {((item.count / (data?.inspections || 1)) * 100).toFixed(0)}%
                          </span>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
