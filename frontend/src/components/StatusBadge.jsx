import React from 'react';

const STATUS_CONFIG = {
  verified: { label: 'Verified', className: 'badge-verified' },
  pass: { label: 'Pass', className: 'badge-pass' },
  confirmed_by_reviewer: { label: 'Confirmed', className: 'badge-approved' },
  resolved_after_reinspection: { label: 'Resolved', className: 'badge-approved' },
  
  potential_mismatch: { label: 'Potential Mismatch', className: 'badge-potential_mismatch' },
  mismatch_detected: { label: 'Mismatch Detected', className: 'badge-mismatch_detected' },
  rejected_by_reviewer: { label: 'Rejected', className: 'badge-mismatch' },
  
  needs_review: { label: 'Needs Review', className: 'badge-needs_review' },
  review_required: { label: 'Review Required', className: 'badge-review_required' },
  uncertain: { label: 'Uncertain', className: 'badge-review' },
  
  inconclusive: { label: 'Inconclusive', className: 'badge-inconclusive' },
  pending: { label: 'Pending', className: 'badge-pending' },

  // Arrangement statuses
  matches: { label: 'Arrangement matches', className: 'badge-approved' },
  order_changed: { label: 'Order changed: review required', className: 'badge-order-changed' },
  not_enough_evidence: { label: 'Not enough tags read to check the order', className: 'badge-inconclusive' },
};

export default function StatusBadge({ status, customLabel = null }) {
  const normalized = (status || '').toLowerCase();
  const config = STATUS_CONFIG[normalized] || {
    label: status || 'Unknown',
    className: 'badge-pending',
  };

  return (
    <span className={`badge ${config.className}`}>
      {customLabel || config.label}
    </span>
  );
}
