import React from 'react';

export function SkeletonRow({ count = 3, height = 48 }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', width: '100%' }}>
      {Array.from({ length: count }).map((_, idx) => (
        <div
          key={idx}
          className="skeleton skeleton-row"
          style={{ height: `${height}px` }}
        />
      ))}
    </div>
  );
}

export function SkeletonCard({ height = 120 }) {
  return (
    <div
      className="skeleton panel"
      style={{ height: `${height}px`, marginBottom: '16px' }}
    />
  );
}
