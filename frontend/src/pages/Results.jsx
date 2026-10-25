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
  getExpectedItems,
  getInspectionObservations,
  reviewFinding,
  requestReinspection,
  syntheticData,
  getReportUrl,
  getExportCsvUrl,
  downloadFindingsCsv,
  deleteAlignment,
  getDrawingPageUrl,
  visualCompareImages,
  setCabinetReferenceImage,
  clearCabinetReferenceImage,
  getFitFeasibility,
} from '../api.js';
import { Star } from 'lucide-react';
import ImageWithBoxes from '../components/ImageWithBoxes.jsx';
import StatusBadge from '../components/StatusBadge.jsx';
import SyntheticBanner from '../components/SyntheticBanner.jsx';
import Modal from '../components/Modal.jsx';
import { SkeletonCard, SkeletonRow } from '../components/Skeleton.jsx';
import ArrangementSection from '../components/ArrangementSection.jsx';
import AlignmentModal from '../components/AlignmentModal.jsx';
import FitFeasibilityPanel from '../components/FitFeasibilityPanel.jsx';

export default function Results() {
  const { inspectionId } = useParams();
  const isExplicitSynthetic = inspectionId === 'synthetic' || inspectionId?.includes('SYNTH');

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [data, setData] = useState(null);
  const [selectedImageIndex, setSelectedImageIndex] = useState(0);
  const [selectedFindingId, setSelectedFindingId] = useState(null);
  const [activeDetailTab, setActiveDetailTab] = useState('bom'); // 'bom' | 'observations' | 'findings'
  const [expectedItems, setExpectedItems] = useState([]);
  const [observations, setObservations] = useState([]);

  const effectiveExpectedItems = useMemo(
    () => (expectedItems.length > 0 ? expectedItems : data?.expected_items || []),
    [expectedItems, data?.expected_items]
  );
  const effectiveObservations = useMemo(
    () => (observations.length > 0 ? observations : data?.observations || []),
    [observations, data?.observations]
  );

  // Format rating helper
  const formatRating = (rating) => {
    if (!rating) return '—';
    if (typeof rating === 'string') return rating;
    if (rating.raw) return rating.raw;
    const parts = [];
    if (rating.current_a) parts.push(`${rating.current_a}A`);
    if (rating.voltage_v) parts.push(`${rating.voltage_v}V`);
    if (rating.poles) parts.push(`${rating.poles}P`);
    if (rating.curve) parts.push(`Curve ${rating.curve}`);
    return parts.length > 0 ? parts.join(' ') : '—';
  };

  // Fit Feasibility State
  const [fitReport, setFitReport] = useState(null);
  const [loadingFitReport, setLoadingFitReport] = useState(false);
  const [fitReportError, setFitReportError] = useState(null);

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

  // Mark-as-reference flow — the cabinet's chosen baseline photo, if any.
  const referenceImage = useMemo(() => data?.images?.find((i) => i.is_reference) || null, [data]);

  const toggleReference = async (imageId) => {
    if (!data?.cabinet_id) return;
    try {
      if (referenceImage?.image_id === imageId) {
        await clearCabinetReferenceImage(data.cabinet_id);
        setActionFeedback({ type: 'success', message: 'Reference photo unmarked.' });
      } else {
        await setCabinetReferenceImage(data.cabinet_id, imageId);
        setActionFeedback({ type: 'success', message: `Photo ${imageId} set as approved baseline reference.` });
      }
      setCompareResultByImage({});
      await loadInspection();
    } catch (err) {
      setActionFeedback({ type: 'error', message: `Could not update reference photo: ${err.message}` });
    }
  };

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

      // Fetch Contract A BOM expected items
      if (res?.design_revision_internal_id) {
        getExpectedItems(res.design_revision_internal_id)
          .then((bom) => setExpectedItems(bom?.items || []))
          .catch((e) => console.warn('Could not fetch expected items:', e));
      }

      // Fetch Contract B observations
      getInspectionObservations(inspectionId)
        .then((imageObsList) => {
          const allObs = [];
          (imageObsList || []).forEach((io) => {
            (io.observations || []).forEach((o) => allObs.push({ ...o, image_id: io.image_id }));
          });
          setObservations(allObs);
        })
        .catch((e) => console.warn('Could not fetch observations:', e));
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

  // Poll while background inspection pipeline (RF-DETR, OWLv2, RapidOCR) is executing
  useEffect(() => {
    if (data?.state === 'running' || data?.state === 'queued') {
      const interval = setInterval(async () => {
        try {
          const res = await getInspection(inspectionId);
          setData(res);
          if (res?.state !== 'running' && res?.state !== 'queued') {
            clearInterval(interval);
            if (res?.findings?.length > 0 && !selectedFindingId) {
              setSelectedFindingId(res.findings[0].finding_id);
            }
            // Re-fetch observations after pipeline run completes
            getInspectionObservations(inspectionId)
              .then((imageObsList) => {
                const allObs = [];
                (imageObsList || []).forEach((io) => {
                  (io.observations || []).forEach((o) => allObs.push({ ...o, image_id: io.image_id }));
                });
                setObservations(allObs);
              })
              .catch(() => {});
          }
        } catch {
          // ignore transient poll error
        }
      }, 2000);
      return () => clearInterval(interval);
    }
  }, [data?.state, inspectionId, selectedFindingId]);

  // Load Fit Feasibility for currently selected finding
  useEffect(() => {
    if (!selectedFindingId) {
      setFitReport(null);
      return;
    }
    let isCurrent = true;
    setLoadingFitReport(true);
    setFitReportError(null);
    getFitFeasibility(data?.inspection_id || inspectionId, selectedFindingId)
      .then((report) => {
        if (isCurrent) setFitReport(report);
      })
      .catch((err) => {
        if (isCurrent) setFitReportError(err.message || 'Could not evaluate fit feasibility.');
      })
      .finally(() => {
        if (isCurrent) setLoadingFitReport(false);
      });
    return () => {
      isCurrent = false;
    };
  }, [selectedFindingId, data?.inspection_id, inspectionId]);

  // Normalize findings list
  const findings = useMemo(() => data?.findings || [], [data]);

  // Filter findings
  const filteredFindings = useMemo(() => {
    return findings.filter((f) => {
      const matchesType =
        typeFilter === 'all' ||
        f.type === typeFilter ||
        (typeFilter === 'missing' && (f.type === 'missing' || f.type === 'missing_component')) ||
        (typeFilter === 'missing_component' && (f.type === 'missing' || f.type === 'missing_component')) ||
        (typeFilter === 'unexpected' && (f.type === 'unexpected' || f.type === 'unexpected_component')) ||
        (typeFilter === 'unexpected_component' && (f.type === 'unexpected' || f.type === 'unexpected_component'));
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

  // Preselect the reference as the compare target the first time it appears (needs activeImage).
  useEffect(() => {
    if (referenceImage && !compareReferenceId && referenceImage.image_id !== activeImage?.image_id) {
      setCompareReferenceId(referenceImage.image_id);
    }
  }, [referenceImage, activeImage, compareReferenceId]);

  // Map findings and observations into SVG bounding boxes for ImageWithBoxes
  const boxes = useMemo(() => {
    const list = [];
    const seenBoxes = new Set();

    const addBox = (box) => {
      if (!box.bbox || box.bbox.length < 4) return;
      const key = `${Math.round(box.bbox[0])}_${Math.round(box.bbox[1])}_${Math.round(box.bbox[2])}_${Math.round(box.bbox[3])}`;
      if (seenBoxes.has(key)) return;
      seenBoxes.add(key);
      list.push(box);
    };

    for (const f of findings) {
      const tagLabel = f.observed_tag || f.expected_tag || f.tag || f.finding_id;

      // 1. Primary observation bbox
      let primaryBbox = null;
      let primaryImgId = null;
      if (f.observation?.bbox) {
        primaryBbox = f.observation.bbox;
        primaryImgId = f.observation.image_id;
      } else if (f.evidence && f.evidence.length > 0 && f.evidence[0].bbox) {
        primaryBbox = f.evidence[0].bbox;
        primaryImgId = f.evidence[0].image_id;
      }

      if (primaryBbox && (!primaryImgId || primaryImgId === activeImage.image_id || data?.images?.length <= 1)) {
        let className = f.observation?.class_name || f.component_type;
        if (!className) {
          const tag = (f.expected_tag || f.observed_tag || f.tag || '').toUpperCase();
          if (tag.startsWith('CB') || tag.startsWith('DS')) className = 'mcb';
          else if (tag.startsWith('PS')) className = 'power_supply';
          else if (tag.startsWith('IO')) className = 'io_module';
          else className = 'mcb';
        }

        let boxLabel = tagLabel;
        if (f.type === 'rating_mismatch') {
          boxLabel = `WRONG RATING: ${tagLabel}`;
        } else if (f.status === 'verified' || f.type === 'verified') {
          boxLabel = `VERIFIED: ${tagLabel}`;
        } else if (f.type === 'unexpected' || f.type === 'unexpected_component') {
          boxLabel = `UNEXPECTED: ${tagLabel}`;
        }

        addBox({
          id: f.finding_id,
          bbox: primaryBbox,
          label: boxLabel,
          className,
          status: f.status,
          issue_type: f.type,
          sources: f.sources || ['detector'],
          confidence: f.observation?.detector_confidence ?? f.detector_confidence,
          ocr_confidence: f.observation?.ocr_confidence ?? f.ocr_confidence,
        });
      }

      // 2. All secondary evidence bboxes (e.g. OCR text labels, tag labels)
      if (f.evidence && Array.isArray(f.evidence)) {
        f.evidence.forEach((ev, evIdx) => {
          if (!ev?.bbox) return;
          const evImgId = ev.image_id;
          if (!evImgId || evImgId === activeImage.image_id || data?.images?.length <= 1) {
            let className = 'mcb';
            let label = tagLabel;
            if (ev.source === 'ocr') {
              label = ev.text ? `OCR: ${ev.text}` : `[TAG] ${tagLabel}`;
            } else if (ev.source === 'zero_shot') {
              label = `ZERO-SHOT: ${tagLabel}`;
              className = 'power_supply';
            } else {
              label = f.status === 'verified' ? `VERIFIED: ${tagLabel}` : tagLabel;
            }

            addBox({
              id: `${f.finding_id}-ev-${evIdx}`,
              bbox: ev.bbox,
              label,
              className,
              status: f.status,
              issue_type: f.type,
              sources: [ev.source || 'detector'],
              confidence: f.detector_confidence,
              ocr_confidence: f.ocr_confidence,
            });
          }
        });
      }
    }

    // 3. Raw detections from RF-DETR / OWLv2 / RapidOCR on activeImage that have not been assigned to a finding
    if (effectiveObservations && Array.isArray(effectiveObservations)) {
      effectiveObservations.forEach((obs) => {
        if (!obs?.bbox) return;
        if (!obs.image_id || obs.image_id === activeImage.image_id || data?.images?.length <= 1) {
          const className = obs.class_name || (obs.kind === 'tag_label' ? 'tag_label' : 'mcb');
          const label = obs.text
            ? `${obs.text}`
            : obs.class_name
            ? `${obs.class_name.toUpperCase()}`
            : `DET ${obs.observation_id}`;

          addBox({
            id: obs.observation_id,
            bbox: obs.bbox,
            label,
            className,
            status: 'detected',
            issue_type: obs.kind,
            sources: [obs.source],
            confidence: obs.confidence,
            ocr_confidence: obs.text_confidence,
          });
        }
      });
    }

    // Append visual-compare change regions (if any) for the active image.
    const compare = compareResultByImage[activeImage.image_id];
    if (compare?.diagnostic === 'ok' && compare.regions?.length) {
      compare.regions.forEach((reg, i) => {
        addBox({
          id: `CHG-${activeImage.image_id}-${i}`,
          bbox: reg.bbox,
          label: `CHG ${(reg.change_score * 100).toFixed(0)}%`,
          className: 'change_region',
          status: 'needs_review',
          issue_type: 'change_region',
          sources: ['visual_compare'],
          confidence: reg.change_score,
        });
      });
    }
    return list;
  }, [findings, activeImage, data, compareResultByImage, effectiveObservations]);

  // Missing components expected positions (§3.4, contract E)
  const missingExpectedBoxes = useMemo(() => {
    return findings
      .filter(
        (f) =>
          (f.type === 'missing' || f.type === 'missing_component') &&
          (f.expected_bbox || f.observation?.expected_bbox)
      )
      .map((f) => ({
        id: f.finding_id,
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
          {/* Counts summary — comprehensive status & inspection statistics */}
          <div className="counts-pills" aria-label="Inspection counts" style={{ marginTop: '8px' }}>
            {effectiveExpectedItems.length > 0 && (
              <span className="counts-pill" style={{ background: 'var(--color-blue-50)', color: 'var(--color-navy)', borderColor: 'var(--color-blue-100)' }}>
                <strong>{effectiveExpectedItems.length}</strong>
                <span>Expected BOM</span>
              </span>
            )}
            {effectiveObservations.length > 0 && (
              <span className="counts-pill" style={{ background: '#f6f8fa', color: '#24292f', borderColor: '#d0d7de' }}>
                <strong>{effectiveObservations.length}</strong>
                <span>Visual Detections</span>
              </span>
            )}
            {['verified', 'potential_mismatch', 'needs_review', 'inconclusive', 'confirmed_by_reviewer', 'rejected_by_reviewer'].map((k) => (
              data?.counts?.[k] ? (
                <span key={k} className={`counts-pill cp-${k}`}>
                  <strong>{data.counts[k]}</strong>
                  <span>{k.replace(/_/g, ' ')}</span>
                </span>
              ) : null
            ))}
          </div>
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
        <div
          className="notice"
          style={{
            backgroundColor:
              typeof actionFeedback === 'object' && actionFeedback.type === 'error'
                ? '#ffebe9'
                : 'var(--color-status-approved-bg)',
            borderColor:
              typeof actionFeedback === 'object' && actionFeedback.type === 'error'
                ? '#ff8182'
                : '#a3e3af',
            color:
              typeof actionFeedback === 'object' && actionFeedback.type === 'error'
                ? '#cf222e'
                : 'var(--color-status-approved)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '8px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            {typeof actionFeedback === 'object' && actionFeedback.type === 'error' ? (
              <XCircle size={16} color="#cf222e" />
            ) : (
              <CheckCircle2 size={16} />
            )}
            <div>{typeof actionFeedback === 'object' ? actionFeedback.message : actionFeedback}</div>
          </div>
          <button
            type="button"
            onClick={() => setActionFeedback(null)}
            style={{
              background: 'transparent',
              border: 'none',
              cursor: 'pointer',
              color: 'inherit',
              padding: '2px 6px',
              fontSize: '12px',
              fontWeight: 600,
            }}
            title="Dismiss message"
          >
            ✕
          </button>
        </div>
      )}

      {/* Live Pipeline Status Banner */}
      {(data?.state === 'running' || data?.state === 'queued') && (
        <div
          className="notice"
          style={{
            backgroundColor: '#ddf4ff',
            borderColor: '#54aeff',
            color: '#0969da',
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
            padding: '12px 16px',
            marginBottom: '16px',
            borderRadius: '6px',
          }}
        >
          <RotateCcw className="spin" size={18} />
          <div>
            <strong>ML Inspection in progress ({data.state})…</strong>
            <div style={{ fontSize: '12px', marginTop: '2px', color: '#0550ae' }}>
              Running trained RF-DETR object detector, OWLv2 zero-shot, and RapidOCR on the uploaded cabinet photograph(s). Findings and bounding boxes will refresh automatically.
            </div>
          </div>
        </div>
      )}

      {data?.state === 'failed' && (
        <div
          className="notice"
          style={{
            backgroundColor: '#ffebe9',
            borderColor: '#ff8182',
            color: '#cf222e',
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
            padding: '12px 16px',
            marginBottom: '16px',
            borderRadius: '6px',
          }}
        >
          <XCircle size={18} />
          <div>
            <strong>Inspection pipeline failed</strong>
            <div style={{ fontSize: '12px', marginTop: '2px' }}>
              {data.error || 'The model detector or OCR pipeline reported a failure. Check server logs for details.'}
            </div>
          </div>
        </div>
      )}

      {/* Dual Column Workspace */}
      <div className="results-workspace">
        {/* LEFT COLUMN: Image with Boxes Viewer */}
        <div>
          {/* Multiple Photos Selector Tab if more than 1 image */}
          {data?.images && data.images.length > 1 && (
            <div style={{ display: 'flex', gap: '8px', marginBottom: '10px', flexWrap: 'wrap' }}>
              {data.images.map((img, idx) => (
                <button
                  key={img.image_id}
                  type="button"
                  className={`btn btn-sm ${selectedImageIndex === idx ? 'btn-primary' : 'btn-secondary'} ${img.is_reference ? 'has-reference' : ''}`}
                  onClick={() => setSelectedImageIndex(idx)}
                  title={img.is_reference ? 'Approved reference / baseline photo' : ''}
                >
                  {img.is_reference ? <Star size={13} fill="currentColor" /> : <Layers size={13} />}
                  <span>Photo {idx + 1} ({img.image_id})</span>
                </button>
              ))}
              {/* Toggle this photo as the cabinet's reference baseline. */}
              {activeImage?.image_id && data?.cabinet_id && (
                <button
                  type="button"
                  className={`btn btn-sm ${referenceImage?.image_id === activeImage.image_id ? 'btn-accent' : 'btn-secondary'}`}
                  onClick={() => toggleReference(activeImage.image_id)}
                  title={referenceImage?.image_id === activeImage.image_id
                    ? 'This is the cabinet’s approved reference. Click to unmark.'
                    : 'Mark this photo as the cabinet’s approved reference / baseline.'}
                >
                  <Star size={13} fill={referenceImage?.image_id === activeImage.image_id ? 'currentColor' : 'none'} />
                  <span>{referenceImage?.image_id === activeImage.image_id ? 'Reference' : 'Mark as reference'}</span>
                </button>
              )}
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
                <option value="missing">Missing Component</option>
                <option value="unexpected">Unexpected Component</option>
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
                      <div className="finding-tags" style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
                        <span className="finding-tag">{tagLabel}</span>
                        <span className="mono" style={{ fontSize: '11px', color: 'var(--color-text-muted)' }}>
                          {finding.finding_id}
                        </span>
                        {finding.type === 'missing' || finding.type === 'missing_component' ? (
                          finding.expected_bbox || finding.observation?.expected_bbox ? (
                            <span
                              style={{
                                fontSize: '10px',
                                padding: '1px 6px',
                                borderRadius: '4px',
                                backgroundColor: '#e1f0ff',
                                color: '#0969da',
                                border: '1px solid #b6d3f2',
                                fontWeight: 600,
                              }}
                              title="Component expected location mapped from schematic layout and homography"
                            >
                              Expected Position Mapped
                            </span>
                          ) : (
                            <span
                              style={{
                                fontSize: '10px',
                                padding: '1px 6px',
                                borderRadius: '4px',
                                backgroundColor: '#fff8c5',
                                color: '#9a6700',
                                border: '1px solid #eed07d',
                                fontWeight: 600,
                              }}
                              title="Corner alignment required to project drawing coordinates to photo pixels"
                            >
                              POSITION UNRESOLVED (Corner Alignment Required)
                            </span>
                          )
                        ) : finding.observation?.bbox || (finding.evidence && finding.evidence[0]?.bbox) ? (
                          <span
                            style={{
                              fontSize: '10px',
                              padding: '1px 6px',
                              borderRadius: '4px',
                              backgroundColor: '#f6f8fa',
                              color: '#57606a',
                              border: '1px solid #d0d7de',
                              fontWeight: 500,
                            }}
                          >
                            Observed Position
                          </span>
                        ) : null}
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

          {/* Fit Feasibility & Replacement Options for Active Finding */}
          {selectedFinding && (
            <FitFeasibilityPanel
              report={fitReport}
              loading={loadingFitReport}
              error={fitReportError}
              tag={selectedFinding.observed_tag || selectedFinding.expected_tag || selectedFinding.tag || selectedFinding.finding_id}
            />
          )}
      </div>
      </div>

      {/* Tabbed Detailed Data Inspector (Contract A, B, and C) */}
      <div className="panel" style={{ marginTop: '24px', backgroundColor: '#ffffff' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px', flexWrap: 'wrap', gap: '12px' }}>
          <div>
            <h2 className="panel-title" style={{ fontSize: '18px', color: 'var(--color-navy)' }}>
              Detailed Inspection Data Inspector
            </h2>
            <p className="page-desc" style={{ marginTop: '2px' }}>
              Inspect the extracted drawing components (Contract A), visual AI detections (Contract B), and comparison verification matrix (Contract C).
            </p>
          </div>
          <div style={{ display: 'flex', gap: '8px', background: 'var(--color-surface-subtle)', padding: '4px', borderRadius: '6px', border: '1px solid var(--color-border-subtle)' }}>
            <button
              type="button"
              className={`btn btn-sm ${activeDetailTab === 'bom' ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setActiveDetailTab('bom')}
              style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
            >
              <FileText size={13} />
              <span>Extracted Drawing BOM ({effectiveExpectedItems.length})</span>
            </button>
            <button
              type="button"
              className={`btn btn-sm ${activeDetailTab === 'observations' ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setActiveDetailTab('observations')}
              style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
            >
              <Crosshair size={13} />
              <span>Observed Visual Detections ({effectiveObservations.length})</span>
            </button>
            <button
              type="button"
              className={`btn btn-sm ${activeDetailTab === 'findings' ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setActiveDetailTab('findings')}
              style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
            >
              <Layers size={13} />
              <span>Comparison Findings Matrix ({findings.length})</span>
            </button>
          </div>
        </div>

        {/* TAB 1: Extracted Drawing BOM (Contract A) */}
        {activeDetailTab === 'bom' && (
          <div>
            {effectiveExpectedItems.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '32px 16px', color: 'var(--color-text-muted)' }}>
                No expected BOM items available for this design revision.
              </div>
            ) : (
              <div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: '10px', marginBottom: '16px' }}>
                  <div style={{ background: 'var(--color-surface-subtle)', border: '1px solid var(--color-border)', borderRadius: '6px', padding: '10px 14px' }}>
                    <div style={{ fontSize: '11px', color: 'var(--color-text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>Total Components</div>
                    <div style={{ fontSize: '20px', fontWeight: 700, color: 'var(--color-navy)' }}>{effectiveExpectedItems.length}</div>
                  </div>
                  <div style={{ background: 'var(--color-surface-subtle)', border: '1px solid var(--color-border)', borderRadius: '6px', padding: '10px 14px' }}>
                    <div style={{ fontSize: '11px', color: 'var(--color-text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>Ratings Parsed</div>
                    <div style={{ fontSize: '20px', fontWeight: 700, color: 'var(--color-status-approved)' }}>
                      {effectiveExpectedItems.filter((it) => it.rating && (it.rating.current_a || it.rating.voltage_v || it.rating.raw)).length}
                    </div>
                  </div>
                  <div style={{ background: 'var(--color-surface-subtle)', border: '1px solid var(--color-border)', borderRadius: '6px', padding: '10px 14px' }}>
                    <div style={{ fontSize: '11px', color: 'var(--color-text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>Distinct Tags</div>
                    <div style={{ fontSize: '20px', fontWeight: 700, color: 'var(--color-navy)' }}>
                      {new Set(effectiveExpectedItems.map((it) => it.tag).filter(Boolean)).size}
                    </div>
                  </div>
                  <div style={{ background: 'var(--color-surface-subtle)', border: '1px solid var(--color-border)', borderRadius: '6px', padding: '10px 14px' }}>
                    <div style={{ fontSize: '11px', color: 'var(--color-text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>Mapped Layouts</div>
                    <div style={{ fontSize: '20px', fontWeight: 700, color: '#0969da' }}>
                      {effectiveExpectedItems.filter((it) => it.layout?.bbox).length}
                    </div>
                  </div>
                </div>

                <div className="table-container" style={{ maxHeight: '360px', overflowY: 'auto' }}>
                  <table className="table">
                    <thead>
                      <tr>
                        <th style={{ width: '80px' }}>Tag</th>
                        <th>Part Number</th>
                        <th>Description / Type</th>
                        <th>Expected Rating</th>
                        <th style={{ textAlign: 'center', width: '60px' }}>Qty</th>
                        <th>Drawing Page</th>
                        <th>Schematic Coordinates</th>
                      </tr>
                    </thead>
                    <tbody>
                      {effectiveExpectedItems.map((item, idx) => (
                        <tr key={idx}>
                          <td>
                            <span className="mono" style={{ fontWeight: 700, color: 'var(--color-navy)', background: 'var(--color-blue-50)', padding: '2px 6px', borderRadius: '4px', fontSize: '12px' }}>
                              {item.tag || `[Item ${idx + 1}]`}
                            </span>
                          </td>
                          <td className="mono" style={{ fontSize: '12px' }}>
                            {item.part_number || '—'}
                          </td>
                          <td>
                            <span style={{ fontWeight: 500 }}>{item.description || 'Component'}</span>
                          </td>
                          <td>
                            <span className="mono" style={{ fontWeight: 600, color: item.rating ? 'var(--color-status-approved)' : 'var(--color-text-muted)', fontSize: '12px' }}>
                              {formatRating(item.rating)}
                            </span>
                          </td>
                          <td style={{ textAlign: 'center', fontWeight: 600 }}>
                            {item.quantity ?? 1}
                          </td>
                          <td style={{ fontSize: '12px', color: 'var(--color-text-muted)' }}>
                            {item.source_page ? `Page ${item.source_page}` : item.layout?.page ? `Page ${item.layout.page}` : '—'}
                          </td>
                          <td className="mono" style={{ fontSize: '11px', color: 'var(--color-text-muted)' }}>
                            {item.layout?.bbox ? `[${item.layout.bbox.map((v) => Math.round(v)).join(', ')}]` : '—'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}

        {/* TAB 2: Observed Visual Detections (Contract B) */}
        {activeDetailTab === 'observations' && (
          <div>
            {effectiveObservations.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '32px 16px', color: 'var(--color-text-muted)' }}>
                No visual observations recorded for this inspection yet.
              </div>
            ) : (
              <div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: '10px', marginBottom: '16px' }}>
                  <div style={{ background: 'var(--color-surface-subtle)', border: '1px solid var(--color-border)', borderRadius: '6px', padding: '10px 14px' }}>
                    <div style={{ fontSize: '11px', color: 'var(--color-text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>Total Detections</div>
                    <div style={{ fontSize: '20px', fontWeight: 700, color: 'var(--color-navy)' }}>{effectiveObservations.length}</div>
                  </div>
                  <div style={{ background: 'var(--color-surface-subtle)', border: '1px solid var(--color-border)', borderRadius: '6px', padding: '10px 14px' }}>
                    <div style={{ fontSize: '11px', color: 'var(--color-text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>RF-DETR (Detector)</div>
                    <div style={{ fontSize: '20px', fontWeight: 700, color: 'var(--color-status-approved)' }}>
                      {effectiveObservations.filter((o) => o.source === 'detector').length}
                    </div>
                  </div>
                  <div style={{ background: 'var(--color-surface-subtle)', border: '1px solid var(--color-border)', borderRadius: '6px', padding: '10px 14px' }}>
                    <div style={{ fontSize: '11px', color: 'var(--color-text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>OWLv2 (Zero-shot)</div>
                    <div style={{ fontSize: '20px', fontWeight: 700, color: '#0969da' }}>
                      {effectiveObservations.filter((o) => o.source === 'zero_shot').length}
                    </div>
                  </div>
                  <div style={{ background: 'var(--color-surface-subtle)', border: '1px solid var(--color-border)', borderRadius: '6px', padding: '10px 14px' }}>
                    <div style={{ fontSize: '11px', color: 'var(--color-text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>RapidOCR (Text)</div>
                    <div style={{ fontSize: '20px', fontWeight: 700, color: 'var(--color-navy)' }}>
                      {effectiveObservations.filter((o) => o.source === 'ocr').length}
                    </div>
                  </div>
                </div>

                <div className="table-container" style={{ maxHeight: '360px', overflowY: 'auto' }}>
                  <table className="table">
                    <thead>
                      <tr>
                        <th>Observation ID</th>
                        <th>Source</th>
                        <th>Kind</th>
                        <th>Class / Component</th>
                        <th>Detected Value / Text</th>
                        <th style={{ textAlign: 'center' }}>Detector Conf</th>
                        <th style={{ textAlign: 'center' }}>OCR Conf</th>
                        <th>Bounding Box [x1, y1, x2, y2]</th>
                      </tr>
                    </thead>
                    <tbody>
                      {effectiveObservations.map((obs, idx) => (
                        <tr key={idx}>
                          <td className="mono" style={{ fontSize: '12px', fontWeight: 600, color: 'var(--color-navy)' }}>
                            {obs.observation_id}
                          </td>
                          <td>
                            <span className={`source-badge source-${obs.source}`}>
                              {obs.source === 'zero_shot' ? 'Zero-shot' : obs.source === 'detector' ? 'RF-DETR' : obs.source === 'ocr' ? 'RapidOCR' : obs.source}
                            </span>
                          </td>
                          <td style={{ fontSize: '12px', textTransform: 'capitalize' }}>
                            {obs.kind.replace('_', ' ')}
                          </td>
                          <td>
                            <strong style={{ fontSize: '12px' }}>{obs.class_name}</strong>
                          </td>
                          <td>
                            {obs.text ? (
                              <span className="mono" style={{ fontWeight: 600, color: 'var(--color-navy)', background: '#f6f8fa', padding: '2px 6px', borderRadius: '4px', fontSize: '12px' }}>
                                {obs.text}
                              </span>
                            ) : (
                              <span style={{ color: 'var(--color-text-muted)' }}>—</span>
                            )}
                          </td>
                          <td style={{ textAlign: 'center', fontSize: '12px', fontWeight: 600 }}>
                            {obs.confidence != null ? `${(obs.confidence * 100).toFixed(0)}%` : '—'}
                          </td>
                          <td style={{ textAlign: 'center', fontSize: '12px', fontWeight: 600 }}>
                            {obs.text_confidence != null ? `${(obs.text_confidence * 100).toFixed(0)}%` : '—'}
                          </td>
                          <td className="mono" style={{ fontSize: '11px', color: 'var(--color-text-muted)' }}>
                            {obs.bbox ? `[${obs.bbox.map((v) => Math.round(v)).join(', ')}]` : '—'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}

        {/* TAB 3: Comparison Findings Matrix (Contract C) */}
        {activeDetailTab === 'findings' && (
          <div>
            {findings.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '32px 16px', color: 'var(--color-text-muted)' }}>
                No findings generated for this inspection.
              </div>
            ) : (
              <div className="table-container" style={{ maxHeight: '360px', overflowY: 'auto' }}>
                <table className="table">
                  <thead>
                    <tr>
                      <th>Finding ID</th>
                      <th>Tag</th>
                      <th>Issue / Type</th>
                      <th>Expected Value</th>
                      <th>Observed Reading</th>
                      <th style={{ textAlign: 'center' }}>Status</th>
                      <th style={{ textAlign: 'center' }}>Evidence Score</th>
                      <th>Sources</th>
                      <th>Reason</th>
                      <th style={{ textAlign: 'center' }}>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {findings.map((f) => {
                      const tagLabel = f.observed_tag || f.expected_tag || f.tag || f.finding_id;
                      const isSelected = f.finding_id === selectedFindingId;
                      return (
                        <tr
                          key={f.finding_id}
                          style={{
                            backgroundColor: isSelected ? 'var(--color-blue-50)' : undefined,
                            cursor: 'pointer',
                          }}
                          onClick={() => setSelectedFindingId(f.finding_id)}
                        >
                          <td className="mono" style={{ fontSize: '12px', fontWeight: 600 }}>
                            {f.finding_id}
                          </td>
                          <td>
                            <span className="mono" style={{ fontWeight: 700, color: 'var(--color-navy)', background: 'var(--color-blue-50)', padding: '2px 6px', borderRadius: '4px', fontSize: '12px' }}>
                              {tagLabel}
                            </span>
                          </td>
                          <td style={{ fontSize: '12px', textTransform: 'capitalize' }}>
                            {(f.type || '').replace(/_/g, ' ')}
                          </td>
                          <td className="mono" style={{ fontSize: '12px', fontWeight: 500 }}>
                            {f.expected_value || '—'}
                          </td>
                          <td className="mono" style={{ fontSize: '12px', fontWeight: 600, color: f.type === 'rating_mismatch' ? 'var(--color-status-mismatch)' : 'inherit' }}>
                            {f.observed_text || f.observed_rating || '—'}
                          </td>
                          <td style={{ textAlign: 'center' }}>
                            <StatusBadge status={f.status} />
                          </td>
                          <td style={{ textAlign: 'center', fontWeight: 600, fontSize: '12px' }}>
                            {f.evidence_score != null ? `${(f.evidence_score * 100).toFixed(0)}%` : '—'}
                          </td>
                          <td>
                            <div className="source-badges" style={{ gap: '4px' }}>
                              {(f.sources && f.sources.length > 0 ? f.sources : ['detector']).map((src) => (
                                <span key={src} className={`source-badge source-${src}`} style={{ fontSize: '10px', padding: '1px 5px' }}>
                                  {src === 'zero_shot' ? 'Zero-shot' : src}
                                </span>
                              ))}
                            </div>
                          </td>
                          <td style={{ fontSize: '12px', color: 'var(--color-text-muted)', maxWidth: '200px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }} title={f.reason || ''}>
                            {f.reason || '—'}
                          </td>
                          <td style={{ textAlign: 'center' }}>
                            <button
                              type="button"
                              className="btn btn-secondary btn-sm"
                              onClick={(e) => {
                                e.stopPropagation();
                                setSelectedFindingId(f.finding_id);
                              }}
                            >
                              Inspect
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
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
