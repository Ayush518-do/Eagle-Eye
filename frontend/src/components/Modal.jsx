import React, { useEffect } from 'react';
import { X } from 'lucide-react';

export default function Modal({
  isOpen,
  title,
  onClose,
  onConfirm,
  confirmText = 'Confirm',
  confirmVariant = 'primary',
  isConfirming = false,
  children,
}) {
  useEffect(() => {
    function handleKeyDown(e) {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    }
    if (isOpen) {
      document.addEventListener('keydown', handleKeyDown);
      document.body.style.overflow = 'hidden';
    }
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = 'unset';
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div className="modal-overlay" onClick={onClose} role="dialog" aria-modal="true" aria-labelledby="modal-title">
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h3 id="modal-title" className="modal-title">{title}</h3>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={onClose}
            aria-label="Close dialog"
            style={{ padding: '2px 6px', border: 'none' }}
          >
            <X size={16} />
          </button>
        </div>
        <div className="modal-body">
          {children}
        </div>
        <div className="modal-footer">
          <button
            type="button"
            className="btn btn-secondary"
            onClick={onClose}
            disabled={isConfirming}
          >
            Cancel
          </button>
          <button
            type="button"
            className={`btn btn-${confirmVariant}`}
            onClick={onConfirm}
            disabled={isConfirming}
          >
            {isConfirming ? 'Processing…' : confirmText}
          </button>
        </div>
      </div>
    </div>
  );
}
