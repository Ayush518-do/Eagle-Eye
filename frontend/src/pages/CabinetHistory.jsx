import React, { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import {
  ShieldCheck,
  Calendar,
  User,
  FileText,
  ArrowLeft,
  ArrowRight,
  ExternalLink,
  PlusCircle,
  RefreshCw,
  Clock,
  Layers,
  Printer,
  QrCode,
} from 'lucide-react';
import { getQualityPassport, getCabinet, getCabinets, getCabinetQrUrl, syntheticData } from '../api.js';
import StatusBadge from '../components/StatusBadge.jsx';
import { SkeletonCard, SkeletonRow } from '../components/Skeleton.jsx';

export default function CabinetHistory() {
  const { cabinetId } = useParams();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [passport, setPassport] = useState(null);
  const [cabinetMeta, setCabinetMeta] = useState(null);

  const loadPassport = async () => {
    setLoading(true);
    setError(null);
    try {
      const [passRes, cabRes] = await Promise.allSettled([
        getQualityPassport(cabinetId),
        getCabinets(),
      ]);

      if (passRes.status === 'fulfilled' && passRes.value) {
        setPassport(passRes.value);
      } else {
        // Fallback to synthetic passport
        setPassport({
          ...syntheticData.passport,
          cabinet_id: cabinetId,
        });
      }

      if (cabRes.status === 'fulfilled' && Array.isArray(cabRes.value)) {
        const found = cabRes.value.find((c) => c.cabinet_id === cabinetId);
        if (found) setCabinetMeta(found);
      }
    } catch (err) {
      setError(err.message);
      setPassport({
        ...syntheticData.passport,
        cabinet_id: cabinetId,
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadPassport();
  }, [cabinetId]);

  const inspections = passport?.inspections || [];
  const latestInspection = inspections[0];

  return (
    <div>
      {/* Top Header */}
      <div className="page-header">
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
            <Link to="/cabinets" style={{ color: 'var(--color-text-muted)', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: '4px', fontSize: '12px' }}>
              <ArrowLeft size={12} /> Cabinet Registry
            </Link>
            <span style={{ color: 'var(--color-border)' }}>/</span>
            <span className="eyebrow" style={{ margin: 0 }}>DIGITAL QUALITY PASSPORT</span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
            <h1 className="page-title">{passport?.name || cabinetMeta?.name || `Cabinet ${cabinetId}`}</h1>
            {latestInspection && (
              <StatusBadge status={latestInspection.overall_status} />
            )}
          </div>
          <p className="page-desc">
            ID: <span className="mono">{cabinetId}</span> · Serial: <span className="mono">{passport?.serial || cabinetMeta?.serial || 'SN-UNKNOWN'}</span>
          </p>
        </div>

        <div style={{ display: 'flex', gap: '10px' }}>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={loadPassport}
            title="Refresh quality passport"
          >
            <RefreshCw size={14} />
            <span>Refresh</span>
          </button>
          <Link to="/inspect" className="btn btn-accent">
            <PlusCircle size={15} />
            <span>Run New Scan</span>
          </Link>
        </div>
      </div>

      {/* QR Traceability Card (§3.2) */}
      <div className="cabinet-qr-card">
        <div className="qr-image-frame">
          <img
            src={getCabinetQrUrl(cabinetId)}
            alt={`QR code for cabinet ${cabinetId}`}
            onError={(e) => {
              e.target.onerror = null;
              e.target.src = 'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" viewBox="0 0 100 100"><rect width="100" height="100" fill="%23fff"/><rect x="10" y="10" width="30" height="30" fill="%230a1930"/><rect x="15" y="15" width="20" height="20" fill="%23fff"/><rect x="20" y="20" width="10" height="10" fill="%230a1930"/><rect x="60" y="10" width="30" height="30" fill="%230a1930"/><rect x="65" y="15" width="20" height="20" fill="%23fff"/><rect x="70" y="20" width="10" height="10" fill="%230a1930"/><rect x="10" y="60" width="30" height="30" fill="%230a1930"/><rect x="15" y="65" width="20" height="20" fill="%23fff"/><rect x="20" y="70" width="10" height="10" fill="%230a1930"/><rect x="50" y="50" width="15" height="15" fill="%230a1930"/><rect x="70" y="70" width="20" height="20" fill="%230a1930"/></svg>';
            }}
          />
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <QrCode size={16} color="var(--color-navy)" />
            <strong style={{ fontSize: '14px', color: 'var(--color-navy)' }}>Physical Asset Traceability QR</strong>
          </div>
          <p className="page-desc" style={{ margin: '4px 0 10px', fontSize: '12px' }}>
            Scan on the factory floor with a mobile device to open this cabinet's quality passport ({window.location.origin}/cabinets/{cabinetId}).
          </p>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={() => {
              window.print();
            }}
            title="Print factory label with QR code"
          >
            <Printer size={13} />
            <span>Print Label</span>
          </button>
        </div>
      </div>

      {/* Overview Cards */}
      <div className="metrics-grid" style={{ gridTemplateColumns: 'repeat(3, 1fr)', marginBottom: '24px' }}>
        <div className="metric-card">
          <div className="metric-label">
            <span>Passport Verifications</span>
            <Clock size={16} color="var(--color-navy)" />
          </div>
          <div className="metric-value">{inspections.length}</div>
          <div className="metric-sub">Total historical inspection runs</div>
        </div>

        <div className="metric-card">
          <div className="metric-label">
            <span>Latest Quality Status</span>
            <ShieldCheck size={16} color="var(--color-navy)" />
          </div>
          <div style={{ margin: '10px 0 6px' }}>
            {latestInspection ? (
              <StatusBadge status={latestInspection.overall_status} />
            ) : (
              <span className="mono">Pending Initial Scan</span>
            )}
          </div>
          <div className="metric-sub">
            {latestInspection
              ? `Executed ${new Date(latestInspection.created_at).toLocaleDateString()}`
              : 'Awaiting first inspection'}
          </div>
        </div>

        <div className="metric-card">
          <div className="metric-label">
            <span>Design Revision</span>
            <Layers size={16} color="var(--color-navy)" />
          </div>
          <div className="metric-value mono">
            {latestInspection?.design_revision_id || 'REV-B'}
          </div>
          <div className="metric-sub">Approved engineering drawing standard</div>
        </div>
      </div>

      {/* Timeline Section */}
      <div className="panel">
        <div className="panel-header">
          <div>
            <h2 className="panel-title">Inspection Lifecycle Timeline</h2>
            <p className="page-desc" style={{ fontSize: '12px' }}>
              Full chronological log of visual inspections, detector findings, reviewer sign-offs, and reinspection requests.
            </p>
          </div>
        </div>

        {loading ? (
          <SkeletonRow count={3} height={90} />
        ) : inspections.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '36px 0', color: 'var(--color-text-muted)' }}>
            <p style={{ marginBottom: '12px' }}>No inspections recorded for this cabinet yet.</p>
            <Link to="/inspect" className="btn btn-primary btn-sm">
              Perform First Inspection
            </Link>
          </div>
        ) : (
          <div className="timeline">
            {inspections.map((insp, index) => (
              <div key={insp.inspection_id} className="timeline-item">
                <div className="timeline-marker">
                  {index + 1}
                </div>

                <div className="timeline-content">
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '10px', marginBottom: '8px' }}>
                    <div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                        <Link
                          to={`/inspections/${insp.inspection_id}`}
                          className="mono"
                          style={{ fontSize: '14px', fontWeight: 700, color: 'var(--color-navy)', textDecoration: 'none' }}
                        >
                          {insp.inspection_id}
                        </Link>
                        <StatusBadge status={insp.overall_status} />
                      </div>
                      <div style={{ fontSize: '12px', color: 'var(--color-text-muted)', marginTop: '4px' }}>
                        Revision: <span className="mono">{insp.design_revision_id || 'REV-A'}</span>
                      </div>
                    </div>

                    <div style={{ textAlign: 'right' }}>
                      <div style={{ fontSize: '12px', color: 'var(--color-text-muted)', display: 'flex', alignItems: 'center', gap: '5px' }}>
                        <Calendar size={13} />
                        <span>{new Date(insp.created_at).toLocaleString()}</span>
                      </div>
                      {insp.inspector && (
                        <div style={{ fontSize: '11px', color: 'var(--color-text-muted)', marginTop: '2px', display: 'flex', alignItems: 'center', gap: '5px', justifyContent: 'flex-end' }}>
                          <User size={12} />
                          <span>Inspector: {insp.inspector}</span>
                        </div>
                      )}
                    </div>
                  </div>

                  {insp.summary && (
                    <div style={{ fontSize: '13px', color: 'var(--color-text-main)', marginTop: '10px', padding: '8px 12px', backgroundColor: 'var(--color-surface-subtle)', borderRadius: 'var(--radius-sm)' }}>
                      <strong>Summary:</strong> {insp.summary}
                    </div>
                  )}

                  <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '12px' }}>
                    <Link
                      to={`/inspections/${insp.inspection_id}`}
                      className="btn btn-secondary btn-sm"
                    >
                      <span>Open Full Inspection Workspace</span>
                      <ArrowRight size={13} />
                    </Link>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
