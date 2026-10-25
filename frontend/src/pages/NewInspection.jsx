import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  FileText,
  Upload,
  CheckCircle2,
  AlertCircle,
  ArrowRight,
  ArrowLeft,
  Trash2,
  Server,
  Image as ImageIcon,
  Info,
} from 'lucide-react';
import {
  getCabinets,
  getCabinet,
  createCabinet,
  createDesignRevision,
  parseDrawingForRevision,
  getExpectedItems,
  createInspection,
  runInspection,
} from '../api.js';

export default function NewInspection() {
  const navigate = useNavigate();

  // Step state (1: Cabinet, 2: Drawing PDF, 3: Photos)
  const [currentStep, setCurrentStep] = useState(1);

  // Cabinet state
  const [cabinetMode, setCabinetMode] = useState('existing'); // 'existing' | 'new'
  const [availableCabinets, setAvailableCabinets] = useState([]);
  const [selectedCabinetId, setSelectedCabinetId] = useState('');
  const [newCabinetName, setNewCabinetName] = useState('');
  const [newCabinetSerial, setNewCabinetSerial] = useState('');

  // Drawing state
  const [cabinetRevisions, setCabinetRevisions] = useState([]);
  const [revisionMode, setRevisionMode] = useState('new'); // 'existing' | 'new'
  const [drawingFile, setDrawingFile] = useState(null);
  const [drawingUploadId, setDrawingUploadId] = useState(null);
  const [drawingRevisionId, setDrawingRevisionId] = useState(null);
  const [extractedBOM, setExtractedBOM] = useState(null);
  const [loadingBOM, setLoadingBOM] = useState(false);

  // Photos state
  const [photoFiles, setPhotoFiles] = useState([]);
  const [photoPreviews, setPhotoPreviews] = useState([]);
  const [photoUploadIds, setPhotoUploadIds] = useState([]);

  // Execution & UI state
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const [statusFeedback, setStatusFeedback] = useState('');
  const [isDragActive, setIsDragActive] = useState(false);

  // Load existing cabinets on mount
  useEffect(() => {
    async function fetchCabinets() {
      try {
        const list = await getCabinets();
        if (Array.isArray(list) && list.length > 0) {
          setAvailableCabinets(list);
          setSelectedCabinetId(list[0].cabinet_id);
          setCabinetMode('existing');
        } else {
          setAvailableCabinets([]);
          setSelectedCabinetId('');
          setCabinetMode('new');
        }
      } catch {
        setAvailableCabinets([]);
        setSelectedCabinetId('');
        setCabinetMode('new');
      }
    }
    fetchCabinets();
  }, []);

  // Format file size
  const formatSize = (bytes) => {
    if (!bytes) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
  };

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

  // Load expected items for an existing revision
  const loadBOMForRevision = async (revId) => {
    if (!revId) {
      setExtractedBOM(null);
      return;
    }
    setLoadingBOM(true);
    try {
      const res = await getExpectedItems(revId);
      if (res && Array.isArray(res.items)) {
        setExtractedBOM(res);
      } else {
        setExtractedBOM(null);
      }
    } catch (e) {
      console.warn('Could not load BOM for revision:', e);
      setExtractedBOM(null);
    } finally {
      setLoadingBOM(false);
    }
  };

  // Step 1: Handle Cabinet Selection or Creation
  const handleProceedFromStep1 = async (e) => {
    e.preventDefault();
    setErrorMessage('');

    if (cabinetMode === 'new') {
      if (!newCabinetName.trim() || !newCabinetSerial.trim()) {
        setErrorMessage('Please provide both cabinet name and serial number.');
        return;
      }

      setIsSubmitting(true);
      setStatusFeedback('Registering new cabinet…');
      try {
        // Build a URL-safe cabinet_id from the serial (letters, digits, . _ -, up to 40).
        const safeSerial = newCabinetSerial.trim().replace(/[^A-Za-z0-9._-]+/g, '-').slice(0, 40);
        const cabinet_id = safeSerial || `CAB-${Date.now().toString().slice(-6)}`;
        const res = await createCabinet({ cabinet_id, name: newCabinetName.trim() });
        const createdId = res?.cabinet_id || cabinet_id;
        const newCab = {
          cabinet_id: createdId,
          name: newCabinetName.trim(),
          serial: newCabinetSerial.trim(),
          status: 'pending',
          inspections_count: 0,
        };
        setAvailableCabinets((prev) => [newCab, ...prev]);
        setSelectedCabinetId(createdId);
        setExtractedBOM(null);
        setCurrentStep(2);
      } catch (err) {
        setErrorMessage(err.message || 'Error configuring cabinet.');
      } finally {
        setIsSubmitting(false);
        setStatusFeedback('');
      }
    } else {
      if (!selectedCabinetId) {
        setErrorMessage('Please select a cabinet to inspect.');
        return;
      }
      setIsSubmitting(true);
      setStatusFeedback('Checking cabinet design revisions…');
      try {
        const cabDetail = await getCabinet(selectedCabinetId);
        const revs = cabDetail?.design_revisions || [];
        setCabinetRevisions(revs);
        if (revs.length > 0) {
          setRevisionMode('existing');
          const latestRev = revs[revs.length - 1];
          setDrawingRevisionId(latestRev.design_revision_id);
          loadBOMForRevision(latestRev.design_revision_id);
        } else {
          setRevisionMode('new');
          setExtractedBOM(null);
        }
        setCurrentStep(2);
      } catch {
        setRevisionMode('new');
        setExtractedBOM(null);
        setCurrentStep(2);
      } finally {
        setIsSubmitting(false);
        setStatusFeedback('');
      }
    }
  };

  // Step 2: Handle Drawing PDF Upload
  const handleDrawingSelect = (file) => {
    if (!file) return;
    if (file.type !== 'application/pdf' && !file.name.toLowerCase().endsWith('.pdf')) {
      setErrorMessage('Engineering drawing must be a PDF document.');
      return;
    }
    setDrawingFile(file);
    setExtractedBOM(null); // Reset previously extracted BOM if selecting new file
    setErrorMessage('');
  };

  // Step 2: Extract components from the uploaded PDF
  const handleExtractBOMFromPDF = async () => {
    if (!drawingFile) {
      setErrorMessage('Please select the approved engineering drawing PDF first.');
      return;
    }

    setIsSubmitting(true);
    setStatusFeedback('Uploading drawing and extracting expected components via ML schematic parser…');
    setErrorMessage('');

    try {
      const label = `REV-${new Date().toISOString().slice(0, 10)}`;
      const revisionRes = await createDesignRevision(selectedCabinetId, {
        label,
        drawing: drawingFile,
      });
      if (!revisionRes?.design_revision_id) {
        throw new Error('Backend did not return a design_revision_id.');
      }
      setDrawingRevisionId(revisionRes.design_revision_id);
      setDrawingUploadId(revisionRes.design_revision_id);

      setStatusFeedback('Parsing component tags, ratings, and layout positions from PDF…');
      const parsed = await parseDrawingForRevision(revisionRes.design_revision_id);
      setExtractedBOM(parsed);
      const count = parsed?.items?.length || 0;
      setStatusFeedback(`Successfully extracted ${count} expected components from drawing.`);
    } catch (err) {
      setErrorMessage(err.message || 'Failed to extract drawing BOM.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleProceedFromStep2 = async () => {
    if (revisionMode === 'existing') {
      if (!drawingRevisionId) {
        setErrorMessage('Please select an approved engineering design revision.');
        return;
      }
      setCurrentStep(3);
      return;
    }

    // In new revision mode: if BOM has not been extracted yet, trigger extraction
    if (!extractedBOM?.items?.length) {
      await handleExtractBOMFromPDF();
      return;
    }

    // BOM is extracted and reviewed: advance to photo upload
    setCurrentStep(3);
  };

  // Step 3: Handle Photos Upload
  const handlePhotosSelect = (fileList) => {
    if (!fileList || fileList.length === 0) return;
    const newFiles = Array.from(fileList);
    setPhotoFiles((prev) => [...prev, ...newFiles]);

    // Generate local previews for thumbnails
    const newPreviews = newFiles.map((file) => ({
      file,
      url: URL.createObjectURL(file),
      name: file.name,
      size: file.size,
    }));
    setPhotoPreviews((prev) => [...prev, ...newPreviews]);
    setErrorMessage('');
  };

  const removePhoto = (index) => {
    setPhotoFiles((prev) => prev.filter((_, i) => i !== index));
    setPhotoPreviews((prev) => {
      URL.revokeObjectURL(prev[index].url);
      return prev.filter((_, i) => i !== index);
    });
  };

  // Final Submit: Upload Photos & Run Inspection
  const handleFinalSubmit = async () => {
    if (photoFiles.length === 0) {
      setErrorMessage('Please upload at least one cabinet installation photograph.');
      return;
    }

    if (!drawingRevisionId) {
      setErrorMessage('Design revision was not registered. Please re-upload the drawing in step 2.');
      return;
    }

    setIsSubmitting(true);
    setStatusFeedback('Uploading photographs and creating the inspection…');
    setErrorMessage('');

    try {
      // Backend takes photos directly as multipart (design_revision_id + photos files).
      const inspRes = await createInspection(selectedCabinetId, {
        designRevisionId: drawingRevisionId,
        photos: photoFiles,
      });
      const inspectionId = inspRes?.inspection_id;
      if (!inspectionId) throw new Error('Backend did not return an inspection_id.');

      // Kick off the comparison engine so Results has findings when the user arrives.
      try {
        await runInspection(inspectionId);
      } catch (runErr) {
        console.warn('Inspection run request failed; results may stay empty:', runErr.message);
      }

      navigate(`/inspections/${inspectionId}`);
    } catch (err) {
      setErrorMessage(err.message || 'Inspection pipeline launch failed.');
      setIsSubmitting(false);
    }
  };

  return (
    <div>
      {/* Page Header */}
      <div className="page-header">
        <div>
          <div className="eyebrow">NEW INSPECTION WORKFLOW</div>
          <h1 className="page-title">Prepare Cabinet Inspection</h1>
          <p className="page-desc">
            Complete the 3-step setup to correlate installation photographs with the approved schematic drawing.
          </p>
        </div>
      </div>

      {/* Stepper Progress Bar */}
      <div className="wizard-steps">
        <div className={`wizard-step ${currentStep === 1 ? 'active' : ''} ${currentStep > 1 ? 'completed' : ''}`}>
          <span className="step-num">{currentStep > 1 ? '✓' : '1'}</span>
          <span>Target Cabinet</span>
        </div>
        <ArrowRight size={14} color="var(--color-border)" />
        <div className={`wizard-step ${currentStep === 2 ? 'active' : ''} ${currentStep > 2 ? 'completed' : ''}`}>
          <span className="step-num">{currentStep > 2 ? '✓' : '2'}</span>
          <span>Engineering Drawing</span>
        </div>
        <ArrowRight size={14} color="var(--color-border)" />
        <div className={`wizard-step ${currentStep === 3 ? 'active' : ''}`}>
          <span className="step-num">3</span>
          <span>Cabinet Photographs</span>
        </div>
      </div>

      {/* Error Message */}
      {errorMessage && (
        <div className="error-card">
          <div>
            <div className="error-title">Validation Warning</div>
            <div className="error-desc">{errorMessage}</div>
          </div>
        </div>
      )}

      {/* Status Banner */}
      {statusFeedback && (
        <div className="notice" style={{ backgroundColor: 'var(--color-surface-subtle)', borderColor: 'var(--color-navy)' }}>
          <Info size={18} className="notice-icon" color="var(--color-navy)" />
          <div style={{ color: 'var(--color-navy)', fontWeight: 600 }}>{statusFeedback}</div>
        </div>
      )}

      {/* STEP 1: Cabinet Selection or Creation */}
      {currentStep === 1 && (
        <div className="panel" style={{ maxWidth: '680px' }}>
          <h2 className="panel-title" style={{ marginBottom: '16px' }}>
            Step 1: Select or Create Cabinet
          </h2>

          <div style={{ display: 'flex', gap: '16px', marginBottom: '20px' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontWeight: 600 }}>
              <input
                type="radio"
                name="cabinetMode"
                value="existing"
                checked={cabinetMode === 'existing'}
                onChange={() => setCabinetMode('existing')}
              />
              <span>Select Existing Cabinet</span>
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontWeight: 600 }}>
              <input
                type="radio"
                name="cabinetMode"
                value="new"
                checked={cabinetMode === 'new'}
                onChange={() => setCabinetMode('new')}
              />
              <span>Register New Cabinet</span>
            </label>
          </div>

          {cabinetMode === 'existing' ? (
            <div className="form-group">
              <label htmlFor="cabinetSelect" className="form-label">
                Cabinet Registry
              </label>
              <select
                id="cabinetSelect"
                className="form-select"
                value={selectedCabinetId}
                onChange={(e) => setSelectedCabinetId(e.target.value)}
              >
                {availableCabinets.map((cab) => (
                  <option key={cab.cabinet_id} value={cab.cabinet_id}>
                    {cab.name} — {cab.serial} ({cab.cabinet_id})
                  </option>
                ))}
              </select>
            </div>
          ) : (
            <div>
              <div className="form-group">
                <label htmlFor="cabName" className="form-label">Cabinet Unit Name</label>
                <input
                  id="cabName"
                  type="text"
                  className="form-input"
                  placeholder="e.g. Distribution Panel Delta 4"
                  value={newCabinetName}
                  onChange={(e) => setNewCabinetName(e.target.value)}
                />
              </div>
              <div className="form-group">
                <label htmlFor="cabSerial" className="form-label">Serial Number</label>
                <input
                  id="cabSerial"
                  type="text"
                  className="form-input mono"
                  placeholder="e.g. SN-88392-2026"
                  value={newCabinetSerial}
                  onChange={(e) => setNewCabinetSerial(e.target.value)}
                />
              </div>
            </div>
          )}

          <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '24px' }}>
            <button
              type="button"
              className="btn btn-primary"
              onClick={handleProceedFromStep1}
              disabled={isSubmitting}
            >
              <span>Continue to Drawing Upload</span>
              <ArrowRight size={14} />
            </button>
          </div>
        </div>
      )}

      {/* STEP 2: Drawing PDF Upload or Existing Revision Selection */}
      {currentStep === 2 && (
        <div className="panel" style={{ maxWidth: extractedBOM?.items?.length ? '920px' : '680px', transition: 'max-width 0.2s ease' }}>
          <h2 className="panel-title" style={{ marginBottom: '6px' }}>
            Step 2: Approved Engineering Drawing & BOM Review
          </h2>
          <p className="page-desc" style={{ marginBottom: '20px' }}>
            Select an existing approved revision from this cabinet or upload a single-line schematic PDF to extract the expected components bill of materials (BOM).
          </p>

          {cabinetRevisions.length > 0 && (
            <div style={{ display: 'flex', gap: '16px', marginBottom: '20px' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontWeight: 600 }}>
                <input
                  type="radio"
                  name="revisionMode"
                  value="existing"
                  checked={revisionMode === 'existing'}
                  onChange={() => {
                    setRevisionMode('existing');
                    if (drawingRevisionId) {
                      loadBOMForRevision(drawingRevisionId);
                    }
                  }}
                />
                <span>Use Existing Approved Revision</span>
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontWeight: 600 }}>
                <input
                  type="radio"
                  name="revisionMode"
                  value="new"
                  checked={revisionMode === 'new'}
                  onChange={() => {
                    setRevisionMode('new');
                    setExtractedBOM(null);
                  }}
                />
                <span>Upload New Drawing (PDF)</span>
              </label>
            </div>
          )}

          {revisionMode === 'existing' && cabinetRevisions.length > 0 ? (
            <div className="form-group" style={{ marginBottom: '24px' }}>
              <label htmlFor="revisionSelect" className="form-label">
                Approved Design Revision
              </label>
              <select
                id="revisionSelect"
                className="form-select"
                value={drawingRevisionId || ''}
                onChange={(e) => {
                  const revId = e.target.value;
                  setDrawingRevisionId(revId);
                  loadBOMForRevision(revId);
                }}
              >
                {cabinetRevisions.map((rev) => (
                  <option key={rev.design_revision_id} value={rev.design_revision_id}>
                    {rev.label} ({rev.design_revision_id}) — registered {new Date(rev.created_at).toLocaleDateString()}
                  </option>
                ))}
              </select>
            </div>
          ) : (
            <div>
              <div
                className={`dropzone ${isDragActive ? 'drag-active' : ''}`}
                onDragOver={(e) => {
                  e.preventDefault();
                  setIsDragActive(true);
                }}
                onDragLeave={() => setIsDragActive(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setIsDragActive(false);
                  if (e.dataTransfer.files?.[0]) {
                    handleDrawingSelect(e.dataTransfer.files[0]);
                  }
                }}
                onClick={() => document.getElementById('drawingFileInput')?.click()}
              >
                <input
                  id="drawingFileInput"
                  type="file"
                  accept=".pdf,application/pdf"
                  style={{ display: 'none' }}
                  onChange={(e) => handleDrawingSelect(e.target.files?.[0])}
                />
                <FileText className="dropzone-icon" />
                <div className="dropzone-title">
                  {drawingFile ? drawingFile.name : 'Click to browse or drop drawing PDF here'}
                </div>
                <div className="dropzone-sub">
                  {drawingFile
                    ? `Ready for parsing · ${formatSize(drawingFile.size)}`
                    : 'PDF format · Must contain cabinet component schedule & ratings'}
                </div>
              </div>

              {drawingFile && !extractedBOM && (
                <div style={{ marginTop: '12px', display: 'flex', justifyContent: 'center' }}>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={handleExtractBOMFromPDF}
                    disabled={isSubmitting}
                  >
                    <FileText size={14} />
                    <span>{isSubmitting ? 'Extracting Drawing BOM…' : 'Extract Components from Drawing PDF'}</span>
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Loading Indicator for BOM */}
          {loadingBOM && (
            <div style={{ padding: '24px', textAlign: 'center', color: 'var(--color-navy)', fontSize: '13px' }}>
              Loading expected items for design revision…
            </div>
          )}

          {/* Extracted BOM Review Table & Metric Cards */}
          {extractedBOM && extractedBOM.items && (
            <div style={{ marginTop: '24px', borderTop: '1px solid var(--color-border-subtle)', paddingTop: '16px' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '14px', flexWrap: 'wrap', gap: '8px' }}>
                <div>
                  <h3 style={{ fontSize: '15px', fontWeight: 600, color: 'var(--color-navy)', display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <CheckCircle2 size={16} color="var(--color-status-approved)" />
                    <span>Extracted Drawing Bill of Materials (BOM)</span>
                  </h3>
                  <div style={{ fontSize: '12px', color: 'var(--color-text-muted)' }}>
                    Extracted via ML drawing parser ({extractedBOM.parser_version || 'drawing-parser-v1'}) · Review before photo comparison
                  </div>
                </div>
                {revisionMode === 'new' && (
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => {
                      setExtractedBOM(null);
                      setDrawingFile(null);
                    }}
                    title="Choose a different PDF drawing"
                  >
                    Change Drawing
                  </button>
                )}
              </div>

              {/* Summary Metrics */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: '10px', marginBottom: '16px' }}>
                <div style={{ background: 'var(--color-surface-subtle)', border: '1px solid var(--color-border)', borderRadius: '6px', padding: '10px 14px' }}>
                  <div style={{ fontSize: '11px', color: 'var(--color-text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>Total Components</div>
                  <div style={{ fontSize: '20px', fontWeight: 700, color: 'var(--color-navy)' }}>{extractedBOM.items.length}</div>
                </div>
                <div style={{ background: 'var(--color-surface-subtle)', border: '1px solid var(--color-border)', borderRadius: '6px', padding: '10px 14px' }}>
                  <div style={{ fontSize: '11px', color: 'var(--color-text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>Ratings Parsed</div>
                  <div style={{ fontSize: '20px', fontWeight: 700, color: 'var(--color-status-approved)' }}>
                    {extractedBOM.items.filter((it) => it.rating && (it.rating.current_a || it.rating.voltage_v || it.rating.raw)).length}
                  </div>
                </div>
                <div style={{ background: 'var(--color-surface-subtle)', border: '1px solid var(--color-border)', borderRadius: '6px', padding: '10px 14px' }}>
                  <div style={{ fontSize: '11px', color: 'var(--color-text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>Tagged Items</div>
                  <div style={{ fontSize: '20px', fontWeight: 700, color: 'var(--color-navy)' }}>
                    {extractedBOM.items.filter((it) => Boolean(it.tag)).length}
                  </div>
                </div>
                <div style={{ background: 'var(--color-surface-subtle)', border: '1px solid var(--color-border)', borderRadius: '6px', padding: '10px 14px' }}>
                  <div style={{ fontSize: '11px', color: 'var(--color-text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>Layout Projected</div>
                  <div style={{ fontSize: '20px', fontWeight: 700, color: '#0969da' }}>
                    {extractedBOM.items.filter((it) => it.layout?.bbox).length}
                  </div>
                </div>
              </div>

              {/* BOM Table */}
              <div className="table-container" style={{ maxHeight: '280px', overflowY: 'auto' }}>
                <table className="table">
                  <thead>
                    <tr>
                      <th style={{ width: '80px' }}>Tag</th>
                      <th>Part Number</th>
                      <th>Description / Type</th>
                      <th>Expected Rating</th>
                      <th style={{ textAlign: 'center', width: '50px' }}>Qty</th>
                      <th>Drawing Location</th>
                      <th style={{ textAlign: 'center', width: '90px' }}>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {extractedBOM.items.map((item, idx) => (
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
                        <td style={{ textAlign: 'center' }}>
                          <span style={{ fontSize: '11px', padding: '2px 6px', borderRadius: '4px', background: 'var(--color-status-approved-bg)', color: 'var(--color-status-approved)', fontWeight: 600 }}>
                            ✓ Extracted
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '24px' }}>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => setCurrentStep(1)}
              disabled={isSubmitting}
            >
              <ArrowLeft size={14} />
              <span>Back</span>
            </button>
            <button
              type="button"
              className="btn btn-primary"
              onClick={handleProceedFromStep2}
              disabled={
                revisionMode === 'existing'
                  ? (!drawingRevisionId || isSubmitting)
                  : (!drawingFile || isSubmitting)
              }
            >
              <span>
                {isSubmitting
                  ? 'Processing…'
                  : extractedBOM?.items?.length
                  ? 'Continue to Photo Upload'
                  : 'Extract BOM & Continue'}
              </span>
              <ArrowRight size={14} />
            </button>
          </div>
        </div>
      )}

      {/* STEP 3: Photographs Upload & Launch */}
      {currentStep === 3 && (
        <div className="panel" style={{ maxWidth: '780px' }}>
          <h2 className="panel-title" style={{ marginBottom: '6px' }}>
            Step 3: Upload Cabinet Installation Photographs
          </h2>
          <p className="page-desc" style={{ marginBottom: '20px' }}>
            Capture a full front view of the assembled cabinet enclosure, plus any close-up photos of circuit breaker rails or I/O racks.
          </p>

          <div
            className={`dropzone ${isDragActive ? 'drag-active' : ''}`}
            onDragOver={(e) => {
              e.preventDefault();
              setIsDragActive(true);
            }}
            onDragLeave={() => setIsDragActive(false)}
            onDrop={(e) => {
              e.preventDefault();
              setIsDragActive(false);
              if (e.dataTransfer.files) {
                handlePhotosSelect(e.dataTransfer.files);
              }
            }}
            onClick={() => document.getElementById('photoFileInput')?.click()}
          >
            <input
              id="photoFileInput"
              type="file"
              accept="image/jpeg,image/png,image/webp"
              multiple
              style={{ display: 'none' }}
              onChange={(e) => handlePhotosSelect(e.target.files)}
            />
            <Upload className="dropzone-icon" />
            <div className="dropzone-title">
              Drag photos here or click to select files
            </div>
            <div className="dropzone-sub">
              Supported: JPEG, PNG · High resolution and even lighting recommended
            </div>
          </div>

          {/* Photo Previews Grid */}
          {photoPreviews.length > 0 && (
            <div>
              <div style={{ fontSize: '12px', fontWeight: 600, marginTop: '20px', color: 'var(--color-navy)' }}>
                Selected Images ({photoPreviews.length})
              </div>
              <div className="photo-grid">
                {photoPreviews.map((preview, index) => (
                  <div key={index} className="photo-thumb-card">
                    <img src={preview.url} alt={`Upload preview ${index + 1}`} className="photo-thumb-img" />
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        removePhoto(index);
                      }}
                      title="Remove photo"
                      style={{
                        position: 'absolute',
                        top: '4px',
                        right: '4px',
                        background: 'rgba(207, 34, 46, 0.9)',
                        color: '#fff',
                        border: 'none',
                        borderRadius: '2px',
                        padding: '2px 4px',
                        cursor: 'pointer',
                      }}
                    >
                      <Trash2 size={12} />
                    </button>
                    <div className="photo-thumb-meta">
                      {preview.name} ({formatSize(preview.size)})
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Human Review Reminder */}
          <div className="notice" style={{ marginTop: '20px' }}>
            <Info size={18} className="notice-icon" />
            <div>
              <strong>Human-in-the-loop QA:</strong> Parts occluded or with low label confidence are marked as <code>inconclusive</code> or <code>needs_review</code>. Inspection decisions require reviewer approval.
            </div>
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '24px' }}>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => setCurrentStep(2)}
              disabled={isSubmitting}
            >
              <ArrowLeft size={14} />
              <span>Back</span>
            </button>
            <button
              type="button"
              className="btn btn-accent"
              onClick={handleFinalSubmit}
              disabled={photoFiles.length === 0 || isSubmitting}
            >
              <span>{isSubmitting ? 'Running Automated Inspection…' : 'Run Inspection'}</span>
              <ArrowRight size={14} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
