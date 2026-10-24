import React, { useState, useEffect, useMemo } from 'react';
import { useParams, Link } from 'react-router-dom';
import {
  CheckCircle2,
  XCircle,
  AlertTriangle,
  RotateCcw,
  Filter,
  FileCheck,
  ChevronRight,
  Info,
  Calendar,
  Layers,
  ArrowLeft,
  ExternalLink,
  Download,
  FileText,
  Crosshair,
} from 'lucide-react';
import {
  API_URL,
  getInspection,
  reviewFinding,
  requestReinspection,
  syntheticData,
  getReportUrl,
  getExportCsvUrl,
  downloadFindingsCsv,
  deleteAlignment,
  getDrawingPageUrl,
  visualCompareImages,
} from '../api.js';
import ImageWithBoxes from '../components/ImageWithBoxes.jsx';
import StatusBadge from '../components/StatusBadge.jsx';
import SyntheticBanner from '../components/SyntheticBanner.jsx';
import Modal from '../components/Modal.jsx';
import { SkeletonCard, SkeletonRow } from '../components/Skeleton.jsx';
import ArrangementSection from '../components/ArrangementSection.jsx';
import AlignmentModal from '../components/AlignmentModal.jsx';

export default function Results() {
  const { inspectionId } = useParams();
  const isExplicitSynthetic = inspectionId === 'synthetic' || inspectionId?.includes('SYNTH');

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [data, setData] = useState(null);
  const [selectedImageIndex, setSelectedImageIndex] = useState(0);
  const [selectedFindingId, setSelectedFindingId] = useState(null);

  // Filters
  const [typeFilter, setTypeFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');

  // Review & Reinspection Action State
  const [reviewNotes, setReviewNotes] = useState('');
  const [reviewerName, setReviewerName] = useState('Inspector 01');
  const [isSubmittingReview, setIsSubmittingReview] = useState(false);
  const [actionFeedback, setActionFeedback] = useState('');

  // Modals
  const [isRejectModalOpen, setIsRejectModalOpen] = useState(false);
  const [isReinspectModalOpen, setIsReinspectModalOpen] = useState(false);
  const [isAlignmentModalOpen, setIsAlignmentModalOpen] = useState(false);
  const [reinspectNotes, setReinspectNotes] = useState('');

  // Visual compare state — per candidate image, store its latest change-region result.
  const [compareReferenceId, setCompareReferenceId] = useState('');
  const [compareResultByImage, setCompareResultByImage] = useState({}); // image_id -> {regions, diagnostic, sift_matches}
  const [isComparing, setIsComparing] = useState(false);

  // Load Inspection Data
  const loadInspection = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await getInspection(inspectionId);
      setData(res);
      // Select first finding by default if available
      if (res?.findings?.length > 0) {
        setSelectedFindingId(res.findings[0].finding_id);
      }
    } catch (err) {
      // Only fall back to synthetic for the explicit demo IDs; otherwise show the real error state.
      setError(err.message || 'Inspection could not be retrieved.');
      if (isExplicitSynthetic) {
        setData(syntheticData.inspection);
        if (syntheticData.inspection.findings?.length > 0) {
          setSelectedFindingId(syntheticData.inspection.findings[0].finding_id);
        }
      } else {
        setData(null);
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadInspection();
  }, [inspectionId]);

  // Normalize findings list
  const findings = useMemo(() => data?.findings || [], [data]);

  // Filter findings
  const filteredFindings = useMemo(() => {
    return findings.filter((f) => {
      const matchesType = typeFilter === 'all' || f.type === typeFilter;
      const matchesStatus = statusFilter === 'all' || f.status === statusFilter;
      return matchesType && matchesStatus;
    });
  }, [findings, typeFilter, statusFilter]);

  // Current active image
  const activeImage = useMemo(() => {
    if (!data?.images || data.images.length === 0) {
      return {
        image_id: 'IMG-DEFAULT',
        url: '',
        width: 1600,
        height: 1000,
        quality_flags: [],
      };
    }
    return data.images[selectedImageIndex] || data.images[0];
  }, [data, selectedImageIndex]);

  // Map findings into SVG bounding boxes for ImageWithBoxes
  const boxes = useMemo(() => {
    const list = [];
    for (const f of findings) {
      let bbox = null;
      let imgId = null;

      if (f.observation?.bbox) {
        bbox = f.observation.bbox;
        imgId = f.observation.image_id;
      } else if (f.evidence && f.evidence.length > 0 && f.evidence[0].bbox) {
        bbox = f.evidence[0].bbox;
        imgId = f.evidence[0].image_id;
      }

      // Check if this box belongs to the active image
      if (bbox && (!imgId || imgId === activeImage.image_id || data?.images?.length <= 1)) {
        // Derive class
        let className = f.observation?.class_name || f.component_type;
        if (!className) {
          const tag = (f.expected_tag || f.observed_tag || f.tag || '').toUpperCase();
          if (tag.startsWith('CB') || tag.startsWith('DS')) className = 'mcb';
          else if (tag.startsWith('PS')) className = 'power_supply';
          else if (tag.startsWith('IO')) className = 'io_module';
          else className = 'mcb';
        }

        list.push({
          id: f.finding_id,
          bbox,
          label: f.observed_tag || f.expected_tag || f.tag || f.finding_id,
          className,
          status: f.status,
          sources: f.sources,
          confidence: f.observation?.detector_confidence ?? f.detector_confidence,
          ocr_confidence: f.observation?.ocr_confidence ?? f.ocr_confidence,
        });
      }
    }
    // Append visual-compare change regions (if any) for the active image.
    const compare = compareResultByImage[activeImage.image_id];
    if (compare?.diagnostic === 'ok' && compare.regions?.length) {
      compare.regions.forEach((reg, i) => {
        list.push({
          id: `CHG-${activeImage.image_id}-${i}`,
          bbox: reg.bbox,
          label: `CHG ${(reg.change_score * 100).toFixed(0)}%`,
          className: 'change_region',
          status: 'needs_review',
          sources: ['visual_compare'],
          confidence: reg.change_score,
        });
      });
    }
    return list;
  }, [findings, activeImage, data, compareResultByImage]);

  // Missing components expected positions (§3.4, contract E)
  const missingExpectedBoxes = useMemo(() => {
    return findings
      .filter(
        (f) =>
          (f.type === 'missing' || f.type === 'missing_component') &&
          (f.expected_bbox || f.observation?.expected_bbox)
      )
      .map((f) => ({
        tag: f.expected_tag || f.tag || f.finding_id,
        expected_bbox: f.expected_bbox || f.observation?.expected_bbox,
        status: f.status,
      }));
  }, [findings]);

  // Reset 4-point corner alignment (§3.4)
  const handleResetAlignment = async () => {
    try {
      await deleteAlignment(activeImage.image_id);
    } catch {
      // offline / mock tolerance
    }
    setData((prev) => {
      if (!prev || !prev.images) return prev;
      return {
        ...prev,
        images: prev.images.map((img) =>
          img.image_id === activeImage.image_id ? { ...img, alignment_set: false, ghost: [] } : img
        ),
      };
    });
    setActionFeedback('Alignment reset to default.');
  };

  // Handle saved 4-point corner alignment (§3.4)
  const handleAlignmentSaved = () => {
    setData((prev) => {
      if (!prev || !prev.images) return prev;
      const ghostBoxes = prev.findings
        .filter((f) => f.observation?.bbox || f.expected_bbox)
        .map((f) => ({
          tag: f.expected_tag || f.observed_tag || f.tag,
          bbox: f.expected_bbox || f.observation?.bbox,
          status: f.status,
        }));

      return {
        ...prev,
        images: prev.images.map((img) =>
          img.image_id === activeImage.image_id
            ? {
                ...img,
                alignment_set: true,
                ghost: img.ghost && img.ghost.length > 0 ? img.ghost : ghostBoxes,
              }
            : img
        ),
      };
    });
    setActionFeedback('Corner alignment saved! Ghost overlay mapped.');
  };

  // Currently selected finding object
  const selectedFinding = useMemo(() => {
    return findings.find((f) => f.finding_id === selectedFindingId) || null;
  }, [findings, selectedFindingId]);

  // Handle Finding Review (Approve / Confirm)
  const handleApprove = async () => {
    if (!selectedFinding) return;
    setIsSubmittingReview(true);
    setActionFeedback('');

    try {
      await reviewFinding(selectedFinding.finding_id, {
        decision: 'confirmed_by_reviewer',
        reviewer: reviewerName,
        note: reviewNotes,
      });
      // Optimistically update local status & record review event
      const reviewEvent = {
        decision: 'confirmed_by_reviewer',
        reviewer: reviewerName,
        note: reviewNotes || null,
        created_at: new Date().toISOString(),
      };
      setData((prev) => ({
        ...prev,
        findings: prev.findings.map((f) =>
          f.finding_id === selectedFinding.finding_id
            ? { ...f, status: 'confirmed_by_reviewer', reviews: [...(f.reviews || []), reviewEvent] }
            : f
        ),
      }));
      setActionFeedback(`Finding ${selectedFinding.finding_id} approved.`);
      setReviewNotes('');
    } catch (err) {
      const reviewEvent = {
        decision: 'confirmed_by_reviewer',
        reviewer: reviewerName,
        note: reviewNotes || null,
        created_at: new Date().toISOString(),
      };
      setData((prev) => ({
        ...prev,
        findings: prev.findings.map((f) =>
          f.finding_id === selectedFinding.finding_id
            ? { ...f, status: 'confirmed_by_reviewer', reviews: [...(f.reviews || []), reviewEvent] }
            : f
        ),
      }));
      setActionFeedback(`Local status updated to Confirmed (Mock fallback).`);
      setReviewNotes('');
    } finally {
      setIsSubmittingReview(false);
    }
  };

  // Handle Finding Rejection (Confirmed via Modal)
  const handleConfirmReject = async () => {
    if (!selectedFinding) return;
    setIsSubmittingReview(true);
    const reviewEvent = {
      decision: 'rejected_by_reviewer',
      reviewer: reviewerName,
      note: reviewNotes || null,
      created_at: new Date().toISOString(),
    };
    try {
      await reviewFinding(selectedFinding.finding_id, {
        decision: 'rejected_by_reviewer',
        reviewer: reviewerName,
        note: reviewNotes,
      });
      setData((prev) => ({
        ...prev,
        findings: prev.findings.map((f) =>
          f.finding_id === selectedFinding.finding_id
            ? { ...f, status: 'rejected_by_reviewer', reviews: [...(f.reviews || []), reviewEvent] }
            : f
        ),
      }));
      setActionFeedback(`Finding ${selectedFinding.finding_id} rejected.`);
      setIsRejectModalOpen(false);
      setReviewNotes('');
    } catch (err) {
      setData((prev) => ({
        ...prev,
        findings: prev.findings.map((f) =>
          f.finding_id === selectedFinding.finding_id
            ? { ...f, status: 'rejected_by_reviewer', reviews: [...(f.reviews || []), reviewEvent] }
            : f
        ),
      }));
      setActionFeedback(`Local status updated to Rejected (Mock fallback).`);
      setIsRejectModalOpen(false);
      setReviewNotes('');
    } finally {
      setIsSubmittingReview(false);
    }
  };

  // Unreviewed findings tracker (§2.1)
  const unreviewedFindingIds = useMemo(() => {
    return findings
      .filter((f) => f.status === 'needs_review' || f.status === 'potential_mismatch')
      .map((f) => f.finding_id);
  }, [findings]);

  const handleNextReview = () => {
    if (unreviewedFindingIds.length === 0) return;
    const currentIndex = unreviewedFindingIds.indexOf(selectedFindingId);
    const nextIndex = (currentIndex + 1) % unreviewedFindingIds.length;
    setSelectedFindingId(unreviewedFindingIds[nextIndex]);
  };

  // Handle Request Reinspection
  const handleConfirmReinspection = async () => {
    setIsSubmittingReview(true);
    try {
      await requestReinspection(data?.inspection_id || inspectionId, reinspectNotes);
      setActionFeedback('Reinspection request dispatched to inspection technicians.');
      setIsReinspectModalOpen(false);
      setReinspectNotes('');
    } catch (err) {
      setActionFeedback('Reinspection request dispatched (Simulated session).');
      setIsReinspectModalOpen(false);
      setReinspectNotes('');
    } finally {
      setIsSubmittingReview(false);
    }
  };

  if (loading) {
    return (
      <div>
        <div className="page-header">
          <div>
            <div className="eyebrow">INSPECTION WORKSPACE</div>
            <h1 className="page-title">Loading Inspection Results…</h1>
          </div>
        </div>
        <SkeletonCard height={200} />
        <SkeletonRow count={5} height={60} />
      </div>
    );
  }

  const overallStatus = data?.overall_status || 'review_required';
  const cabinetId = data?.cabinet_id || 'CAB-2024-X401';

  return (
    <div>
      {/* Banner if Synthetic / Fallback */}
      {(isExplicitSynthetic || error) && (
        <SyntheticBanner
          onDismiss={error ? () => setError(null) : null}
        />
      )}

      {/* Top Header */}
      <div className="page-header">
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
            <Link to="/" style={{ color: 'var(--color-text-muted)', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: '4px', fontSize: '12px' }}>
              <ArrowLeft size={12} /> Dashboard
            </Link>
            <span style={{ color: 'var(--color-border)' }}>/</span>
            <span className="eyebrow" style={{ margin: 0 }}>
              INSPECTION {data?.inspection_id || inspectionId}
            </span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
            <h1 className="page-title">Detection & BOM Verification</h1>
            <StatusBadge status={overallStatus} />
          </div>
          <p className="page-desc">
            Enclosure: <strong>{data?.cabinet_name || cabinetId}</strong> · Revision: <span className="mono">{data?.design_revision_id || 'REV-A'}</span> · Scanned {new Date(data?.created_at || Date.now()).toLocaleString()}
          </p>
          {/* Counts summary — tiny chips so the operator sees the outcome without scrolling */}
          {data?.counts && Object.keys(data.counts).length > 0 && (
            <div className="counts-pills" aria-label="Finding counts">
              {['verified', 'potential_mismatch', 'needs_review', 'inconclusive', 'confirmed_by_reviewer', 'rejected_by_reviewer'].map((k) => (
                data.counts[k] ? (
                  <span key={k} className={`counts-pill cp-${k}`}>
                    <strong>{data.counts[k]}</strong>
                    <span>{k.replace(/_/g, ' ')}</span>
                  </span>
                ) : null
              ))}
            </div>
          )}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
          <a
            href={getReportUrl(data?.inspection_id || inspectionId)}
            target="_blank"
            rel="noopener noreferrer"
            className="btn btn-secondary"
            title="Open printable inspection report (GET /api/inspections/{id}/report)"
          >
            <FileText size={14} />
            <span>Download Report</span>
          </a>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => {
              const url = getExportCsvUrl(data?.inspection_id || inspectionId);
              fetch(url)
                .then((res) => {
                  if (!res.ok) throw new Error('Backend export unavailable');
                  window.location.href = url;
                })
                .catch(() => {
                  downloadFindingsCsv(data?.inspection_id || inspectionId, findings);
                });
            }}
            title="Export findings as CSV (GET /api/inspections/{id}/export.csv)"
          >
            <Download size={14} />
            <span>Export CSV</span>
          </button>
          <Link to={`/cabinets/${cabinetId}`} className="btn btn-secondary">
            <span>Quality Passport</span>
            <ExternalLink size={14} />
          </Link>
          <button
            type="button"
            className="btn btn-accent"
            onClick={() => setIsReinspectModalOpen(true)}
          >
            <RotateCcw size={14} />
            <span>Request Reinspection</span>
          </button>
        </div>
      </div>

      {/* Action feedback message */}
      {actionFeedback && (
        <div className="notice" style={{ backgroundColor: 'var(--color-status-approved-bg)', borderColor: '#a3e3af', color: 'var(--color-status-approved)' }}>
          <CheckCircle2 size={16} />
          <div>{actionFeedback}</div>
        </div>
      )}

      {/* Dual Column Workspace */}
      <div className="results-workspace">
        {/* LEFT COLUMN: Image with Boxes Viewer */}
        <div>
          {/* Multiple Photos Selector Tab if more than 1 image */}
          {data?.images && data.images.length > 1 && (
            <div style={{ display: 'flex', gap: '8px', marginBottom: '10px' }}>
              {data.images.map((img, idx) => (
                <button
                  key={img.image_id}
                  type="button"
                  className={`btn btn-sm ${selectedImageIndex === idx ? 'btn-primary' : 'btn-secondary'}`}
                  onClick={() => setSelectedImageIndex(idx)}
                >
                  <Layers size={13} />
                  <span>Photo {idx + 1} ({img.image_id})</span>
                </button>
              ))}
            </div>
          )}

          {/* Visual compare: pick an approved REFERENCE photo and overlay change regions. */}
          {data?.images && data.images.length > 1 && (
            <div className="compare-bar" aria-label="Visual reference compare">
              <span className="compare-bar-label">
                <Crosshair size={13} /> Reference compare:
              </span>
              <select
                className="filter-select"
                value={compareReferenceId}
                onChange={(e) => setCompareReferenceId(e.target.value)}
                aria-label="Pick an approved reference photo"
              >
                <option value="">— choose approved photo —</option>
                {data.images
                  .filter((img) => img.image_id !== activeImage.image_id)
                  .map((img, idx) => (
                    <option key={img.image_id} value={img.image_id}>
                      Photo {data.images.indexOf(img) + 1} ({img.image_id})
                    </option>
                  ))}
              </select>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                disabled={!compareReferenceId || isComparing}
                onClick={async () => {
                  setIsComparing(true);
                  try {
                    const res = await visualCompareImages(activeImage.image_id, compareReferenceId);
                    setCompareResultByImage((prev) => ({ ...prev, [activeImage.image_id]: res }));
                  } catch (err) {
                    setCompareResultByImage((prev) => ({
                      ...prev,
                      [activeImage.image_id]: { regions: [], diagnostic: 'error', error: err.message },
                    }));
                  } finally {
                    setIsComparing(false);
                  }
                }}
              >
                {isComparing ? 'Comparing…' : 'Run compare'}
              </button>
              {compareResultByImage[activeImage.image_id] && (
                <>
                  <span className="compare-bar-meta">
                    {compareResultByImage[activeImage.image_id].diagnostic === 'ok' &&
                      `${compareResultByImage[activeImage.image_id].regions.length} change region(s), ${compareResultByImage[activeImage.image_id].sift_matches} SIFT matches`}
                    {compareResultByImage[activeImage.image_id].diagnostic === 'no_differences' &&
                      `No change regions — matches the reference (${compareResultByImage[activeImage.image_id].sift_matches} SIFT matches)`}
                    {compareResultByImage[activeImage.image_id].diagnostic === 'poor_alignment' &&
                      `Poor alignment (${compareResultByImage[activeImage.image_id].sift_matches} SIFT matches) — pick a photo taken from the same angle`}
                    {compareResultByImage[activeImage.image_id].diagnostic === 'error' &&
                      `Error: ${compareResultByImage[activeImage.image_id].error}`}
                  </span>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => setCompareResultByImage((prev) => {
                      const next = { ...prev };
                      delete next[activeImage.image_id];
                      return next;
                    })}
                  >
                    Clear
                  </button>
                </>
              )}
            </div>
          )}

          <ImageWithBoxes
            imageUrl={activeImage.url?.startsWith('http') ? activeImage.url : `${API_URL}${activeImage.url || ''}`}
            boxes={boxes}
            ghostBoxes={activeImage.ghost || []}
            missingExpectedBoxes={missingExpectedBoxes}
            alignmentSet={Boolean(activeImage.alignment_set)}
            onOpenAlignment={() => setIsAlignmentModalOpen(true)}
            onResetAlignment={handleResetAlignment}
            highlightedId={selectedFindingId}
            onBoxClick={(boxId) => setSelectedFindingId(boxId)}
            imageDimensions={{
              width: activeImage.width || 1600,
              height: activeImage.height || 1000,
            }}
          />

          {/* Photo Quality Flags */}
          {activeImage.quality_flags && activeImage.quality_flags.length > 0 && (
            <div style={{ marginTop: '8px', fontSize: '11px', color: 'var(--color-text-muted)', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <Info size={12} />
              <span>Image quality observations: {activeImage.quality_flags.join(', ')}</span>
            </div>
          )}
        </div>

        {/* RIGHT COLUMN: Filterable Findings List & Review Controls */}
        <div className="findings-pane">
          {/* Filter Bar */}
          <div className="findings-filter-bar">
            <div className="filter-group">
              <Filter size={14} color="var(--color-navy)" />
              <span>Filter:</span>
              <select
                className="filter-select"
                value={typeFilter}
                onChange={(e) => setTypeFilter(e.target.value)}
                aria-label="Filter by component issue type"
              >
                <option value="all">All Discrepancy Types</option>
                <option value="rating_mismatch">Rating Mismatch</option>
                <option value="missing_component">Missing Component</option>
                <option value="unexpected_component">Unexpected Component</option>
                <option value="uncertain">Uncertain Reading</option>
                <option value="verified">Verified Correct</option>
              </select>
            </div>

            <div className="filter-group">
              <select
                className="filter-select"
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                aria-label="Filter by review status"
              >
                <option value="all">All Review Statuses</option>
                <option value="needs_review">Needs Review</option>
                <option value="potential_mismatch">Potential Mismatch</option>
                <option value="verified">Verified</option>
                <option value="inconclusive">Inconclusive</option>
                <option value="confirmed_by_reviewer">Confirmed</option>
                <option value="rejected_by_reviewer">Rejected</option>
              </select>
            </div>
          </div>

          {/* Findings Cards List */}
          <div className="findings-list" role="listbox" aria-label="Inspection Findings">
            {filteredFindings.length === 0 ? (
              <div className="panel" style={{ textAlign: 'center', padding: '32px 16px', color: 'var(--color-text-muted)' }}>
                No findings match the selected filter criteria.
              </div>
            ) : (
              filteredFindings.map((finding) => {
                const isSelected = finding.finding_id === selectedFindingId;
                const tagLabel = finding.observed_tag || finding.expected_tag || finding.tag || finding.finding_id;
                const expectedRating = finding.expected_rating || finding.expected_value || '—';
                const observedRating = finding.observed_rating || finding.observed_text || '—';

                return (
                  <div
                    key={finding.finding_id}
                    className={`finding-card ${finding.status || ''} ${isSelected ? 'selected' : ''}`}
                    onClick={() => setSelectedFindingId(finding.finding_id)}
                    role="option"
                    aria-selected={isSelected}
                    tabIndex={0}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        setSelectedFindingId(finding.finding_id);
                      }
                    }}
                  >
                    <div className="finding-header">
                      <div className="finding-tags">
                        <span className="finding-tag">{tagLabel}</span>
                        <span className="mono" style={{ fontSize: '11px', color: 'var(--color-text-muted)' }}>
                          {finding.finding_id}
                        </span>
                      </div>
                      <StatusBadge status={finding.status} />
                    </div>

                    {/* Comparison Box */}
                    <div className="finding-comparison">
                      <div>
                        <div className="comp-item-label">Drawing BOM</div>
                        <div className="comp-item-val">{expectedRating}</div>
                      </div>
                      <div>
                        <div className="comp-item-label">Observed Reading</div>
                        <div className="comp-item-val" style={{ color: expectedRating !== observedRating && observedRating !== '—' ? 'var(--color-status-mismatch)' : 'inherit' }}>
                          {observedRating}
                        </div>
                      </div>
                    </div>

                    {/* Reason Text */}
                    {finding.reason && (
                      <div className="finding-reason">{finding.reason}</div>
                    )}

                    {/* Sources & Evidence Score (Milestone 4) */}
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', marginTop: '8px' }}>
                      <div className="source-badges">
                        {(finding.sources && finding.sources.length > 0 ? finding.sources : ['detector', 'ocr']).map((src) => (
                          <span key={src} className={`source-badge source-${src}`}>
                            {src === 'zero_shot' ? 'Zero-shot' : src}
                          </span>
                        ))}
                      </div>

                      {finding.evidence_score != null && (
                        <div
                          className="evidence-score-container"
                          data-pct={`${(finding.evidence_score * 100).toFixed(0)}%`}
                          title={`Evidence agreement score: ${(finding.evidence_score * 100).toFixed(0)}%`}
                        >
                          <span>Score</span>
                          <div className="evidence-bar-track">
                            <div
                              className="evidence-bar-fill"
                              style={{
                                width: `${Math.min(Math.max(finding.evidence_score * 100, 6), 100)}%`,
                                backgroundColor: finding.evidence_score > 0.7 ? 'var(--color-status-approved)' : finding.evidence_score > 0.4 ? 'var(--color-status-review)' : 'var(--color-status-mismatch)',
                              }}
                            />
                          </div>
                          <span style={{ fontWeight: 600 }}>{(finding.evidence_score * 100).toFixed(0)}%</span>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })
            )}
          </div>

          {/* Review Panel for Active Finding */}
          {selectedFinding && (
            <div className="panel" style={{ marginTop: '4px', backgroundColor: '#ffffff' }}>
              <div className="panel-header">
                <div>
                  <h3 className="panel-title">
                    Review Decision: {selectedFinding.observed_tag || selectedFinding.expected_tag || selectedFinding.tag || selectedFinding.finding_id}
                  </h3>
                  <div style={{ fontSize: '11px', color: 'var(--color-text-muted)' }}>
                    Type: <strong style={{ textTransform: 'capitalize' }}>{(selectedFinding.type || '').replace('_', ' ')}</strong>
                  </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={handleNextReview}
                    disabled={unreviewedFindingIds.length === 0}
                    title="Jump to next item needing review (§2.1)"
                  >
                    <span>Next item to review ({unreviewedFindingIds.length})</span>
                    <ChevronRight size={13} />
                  </button>
                  <StatusBadge status={selectedFinding.status} />
                </div>
              </div>

              <div className="form-group" style={{ marginBottom: '10px' }}>
                <label htmlFor="reviewerInput" className="form-label">Reviewer Sign-off</label>
                <input
                  id="reviewerInput"
                  type="text"
                  className="form-input"
                  value={reviewerName}
                  onChange={(e) => setReviewerName(e.target.value)}
                  placeholder="Inspector Name or ID"
                />
              </div>

              <div className="form-group">
                <label htmlFor="reviewNotesInput" className="form-label">Review Notes & Observations</label>
                <textarea
                  id="reviewNotesInput"
                  className="form-textarea"
                  value={reviewNotes}
                  onChange={(e) => setReviewNotes(e.target.value)}
                  placeholder="Provide rationale or visual confirmation notes..."
                  style={{ minHeight: '60px' }}
                />
              </div>

              <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
                <button
                  type="button"
                  className="btn btn-danger"
                  onClick={() => setIsRejectModalOpen(true)}
                  disabled={isSubmittingReview || !reviewerName.trim()}
                >
                  <XCircle size={15} />
                  <span>Reject Finding</span>
                </button>
                <button
                  type="button"
                  className="btn btn-success"
                  onClick={handleApprove}
                  disabled={isSubmittingReview || !reviewerName.trim()}
                >
                  <CheckCircle2 size={15} />
                  <span>Approve / Confirm</span>
                </button>
              </div>

              {/* Review History (§2.1) */}
              {selectedFinding.reviews && selectedFinding.reviews.length > 0 && (
                <div style={{ marginTop: '16px', borderTop: '1px solid var(--color-border-subtle)', paddingTop: '12px' }}>
                  <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase', marginBottom: '8px' }}>
                    Review History
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    {selectedFinding.reviews.map((rev, rIdx) => (
                      <div key={rIdx} style={{ fontSize: '12px', color: 'var(--color-navy)', background: 'var(--color-surface-subtle)', padding: '6px 10px', borderRadius: 'var(--radius-sm)' }}>
                        <strong>{rev.decision === 'confirmed_by_reviewer' ? 'Confirmed' : rev.decision === 'rejected_by_reviewer' ? 'Rejected' : rev.decision}</strong> by {rev.reviewer || 'Inspector'}
                        {rev.created_at && <span> · {new Date(rev.created_at).toLocaleDateString()} {new Date(rev.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>}
                        {rev.note && <span style={{ color: 'var(--color-text-muted)' }}> — &ldquo;{rev.note}&rdquo;</span>}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
      </div>
      </div>

      {/* Component Arrangement / Sequence Section */}
      <ArrangementSection arrangement={data?.arrangement} />

      {/* Reject Modal Confirmation */}
      <Modal
        isOpen={isRejectModalOpen}
        title={`Confirm Rejection: ${selectedFinding?.finding_id}`}
        onClose={() => setIsRejectModalOpen(false)}
        onConfirm={handleConfirmReject}
        confirmText="Confirm Rejection"
        confirmVariant="danger"
        isConfirming={isSubmittingReview}
      >
        <p style={{ marginBottom: '12px', fontSize: '13px' }}>
          Are you sure you wish to reject this finding as a false detection or invalid mismatch?
        </p>
        <div className="notice" style={{ margin: '12px 0' }}>
          <AlertTriangle size={16} />
          <div>
            Rejecting this finding logs an event in the quality passport indicating the observation was inspected and overridden by the reviewer.
          </div>
        </div>
      </Modal>

      {/* Reinspection Modal Confirmation */}
      <Modal
        isOpen={isReinspectModalOpen}
        title="Request Cabinet Reinspection"
        onClose={() => setIsReinspectModalOpen(false)}
        onConfirm={handleConfirmReinspection}
        confirmText="Dispatch Reinspection"
        confirmVariant="accent"
        isConfirming={isSubmittingReview}
      >
        <p style={{ marginBottom: '14px', fontSize: '13px' }}>
          A reinspection request prompts technicians on the assembly line to take fresh photographs or inspect obscured component positions.
        </p>
        <div className="form-group">
          <label htmlFor="reinspectNotesInput" className="form-label">Instructions for Technicians</label>
          <textarea
            id="reinspectNotesInput"
            className="form-textarea"
            placeholder="e.g. Please capture close-up of DIN rail 2 near breaker CB11 with direct lighting..."
            value={reinspectNotes}
            onChange={(e) => setReinspectNotes(e.target.value)}
          />
        </div>
      </Modal>

      {/* 4-Point Corner Alignment Modal (§3.4, contract E) */}
      <AlignmentModal
        isOpen={isAlignmentModalOpen}
        onClose={() => setIsAlignmentModalOpen(false)}
        imageId={activeImage.image_id}
        photoUrl={activeImage.url?.startsWith('http') ? activeImage.url : `${API_URL}${activeImage.url || ''}`}
        drawingUrl={data?.design_revision_internal_id
          ? getDrawingPageUrl(data.design_revision_internal_id, data?.alignment_default_page || 5)
          : ''}
        drawingPage={data?.alignment_default_page || 5}
        imageDimensions={{
          width: activeImage.width || 1600,
          height: activeImage.height || 1000,
        }}
        onSaveSuccess={handleAlignmentSaved}
      />
    </div>
  );
}
