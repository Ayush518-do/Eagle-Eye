import React from 'react';
import StatusBadge from './StatusBadge.jsx';
import { ArrowRight, ArrowDown } from 'lucide-react';

export default function ArrangementSection({ arrangement = [] }) {
  if (!arrangement || arrangement.length === 0) {
    return null;
  }

  const formatDirection = (dir) => {
    if (dir === 'top_to_bottom') return 'top → bottom';
    if (dir === 'left_to_right') return 'left → right';
    return dir || '';
  };

  const formatGroupName = (grp) => {
    return (grp || '')
      .split('_')
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
      .join(' ');
  };

  return (
    <div className="arrangement-section panel">
      <div className="panel-header" style={{ marginBottom: '12px' }}>
        <div>
          <h2 className="panel-title">Component Arrangement & Sequential Order</h2>
          <p className="page-desc" style={{ fontSize: '12px' }}>
            Verification of physical part sequencing along DIN rails against engineering drawings.
          </p>
        </div>
      </div>

      <div className="arrangement-grid">
        {arrangement.map((item, index) => {
          const outOfOrderSet = new Set(item.out_of_order || []);
          return (
            <div key={item.group || index} className="arrangement-card">
              <div className="arrangement-card-header">
                <div>
                  <div className="arrangement-group-name">
                    {formatGroupName(item.group)}
                  </div>
                  {item.direction && (
                    <div className="arrangement-direction">
                      Order sequence: <strong>{formatDirection(item.direction)}</strong>
                    </div>
                  )}
                </div>
                <StatusBadge status={item.status} />
              </div>

              {/* Expected Order Row */}
              <div className="arrangement-row">
                <div className="arrangement-row-label">Expected:</div>
                <div className="arrangement-tags">
                  {item.expected_order && item.expected_order.length > 0 ? (
                    item.expected_order.map((tag, tIdx) => (
                      <span key={tIdx} className="tag-sequence-item">
                        {tag}
                      </span>
                    ))
                  ) : (
                    <span className="mono" style={{ fontSize: '12px', color: 'var(--color-text-muted)' }}>—</span>
                  )}
                </div>
              </div>

              {/* Observed / Found Order Row */}
              <div className="arrangement-row">
                <div className="arrangement-row-label">Found:</div>
                <div className="arrangement-tags">
                  {item.observed_order && item.observed_order.length > 0 ? (
                    item.observed_order.map((tag, tIdx) => {
                      const isOutOfOrder = outOfOrderSet.has(tag);
                      return (
                        <span
                          key={tIdx}
                          className={`tag-sequence-item ${isOutOfOrder ? 'out-of-order' : ''}`}
                          title={isOutOfOrder ? 'Displaced position detected in sequence' : undefined}
                        >
                          {tag}
                        </span>
                      );
                    })
                  ) : (
                    <span className="mono" style={{ fontSize: '12px', color: 'var(--color-text-muted)' }}>
                      No tags read
                    </span>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
