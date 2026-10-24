import React from 'react';
import { Info } from 'lucide-react';

export default function SyntheticBanner({ onDismiss }) {
  return (
    <div className="synthetic-banner" role="status">
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
        <Info size={18} />
        <div>
          <strong>SYNTHETIC DATA PREVIEW:</strong> Displaying simulated inspection observations and detections. Not a real industrial scan.
        </div>
      </div>
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          className="btn btn-secondary btn-sm"
          style={{ background: 'transparent', color: '#ffedd5', borderColor: '#7c2d12', padding: '2px 8px' }}
        >
          Dismiss
        </button>
      )}
    </div>
  );
}
