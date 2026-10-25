// All backend calls go through here. Base URL comes from VITE_API_URL.
import syntheticData from './mocks/inspection.synthetic.json';

export const API_URL = import.meta.env.VITE_API_URL || '';

class ApiError extends Error {
  constructor(message, status = 0, isUnavailable = false) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.isUnavailable = isUnavailable;
  }
}

async function request(path, options = {}) {
  let response;
  const targetUrl = API_URL ? `${API_URL}${path}` : path;
  try {
    response = await fetch(targetUrl, options);
  } catch {
    const backendHint = API_URL || 'http://127.0.0.1:8000';
    throw new ApiError(
      `Cannot reach the backend server at ${backendHint}. Ensure the API is running (start with: uvicorn backend.app.main:app --host 127.0.0.1 --port 8000).`,
      0,
      true
    );
  }

  let body = null;
  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    body = await response.json().catch(() => null);
  } else {
    body = await response.text().catch(() => null);
  }

  if (!response.ok) {
    const detail = typeof body?.detail === 'string'
      ? body.detail
      : body?.detail ? JSON.stringify(body.detail) : (typeof body === 'string' && body.length < 200 ? body : null);
    
    const message = detail || `Request failed with status ${response.status} (${response.statusText})`;
    throw new ApiError(message, response.status, response.status === 404 || response.status === 502 || response.status === 503);
  }

  return body;
}

// System & Model Status
export const getHealth = () => request('/api/health');
export const getModelStatus = () => request('/api/model/status');

// File Uploads
export async function uploadFile(file) {
  const form = new FormData();
  form.append('file', file);
  return request('/api/uploads', {
    method: 'POST',
    body: form,
  });
}

// Cabinets
export const getCabinets = () => request('/api/cabinets');
export const getCabinet = (cabinetId) => request(`/api/cabinets/${encodeURIComponent(cabinetId)}`);
// Backend accepts {cabinet_id, name}; cabinet_id is URL-safe (letters, digits, . _ -, up to 40 chars).
export const createCabinet = ({ cabinet_id, name }) =>
  request('/api/cabinets', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ cabinet_id, name }),
  });

// Design Revisions — the backend takes the PDF file directly (multipart) with a label.
export function createDesignRevision(cabinetId, { label, drawing }) {
  const form = new FormData();
  form.append('label', label);
  form.append('drawing', drawing, drawing.name || 'drawing.pdf');
  return request(`/api/cabinets/${encodeURIComponent(cabinetId)}/design-revisions`, {
    method: 'POST',
    body: form,
  });
}

// Submit a pre-parsed expected-items list for a design revision (Contract A).
export const submitExpectedItems = (revisionId, submission) =>
  request(`/api/design-revisions/${encodeURIComponent(revisionId)}/expected-items`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(submission),
  });

// Trigger the server-side drawing parser on an already-uploaded PDF; auto-populates expected items.
export const parseDrawingForRevision = (revisionId) =>
  request(`/api/design-revisions/${encodeURIComponent(revisionId)}/parse-drawing`, {
    method: 'POST',
  });

// Read back expected items (Contract A BOM) for a design revision.
export const getExpectedItems = (revisionId) =>
  request(`/api/design-revisions/${encodeURIComponent(revisionId)}/expected-items`);

// Visual compare: SIFT + homography + per-pixel diff between an approved REFERENCE photo
// and the current CANDIDATE photo. Returns regions-of-change in candidate pixel coordinates.
export const visualCompareImages = (candidateImageId, referenceImageId) =>
  request(
    `/api/images/${encodeURIComponent(candidateImageId)}/visual-compare?reference=${encodeURIComponent(referenceImageId)}`,
  );

// Reference / baseline photo per cabinet (optional, used as the default compare target).
export const getCabinetReferenceImage = (cabinetId) =>
  request(`/api/cabinets/${encodeURIComponent(cabinetId)}/reference-image`);

export const setCabinetReferenceImage = (cabinetId, imageId) =>
  request(`/api/cabinets/${encodeURIComponent(cabinetId)}/reference-image/${encodeURIComponent(imageId)}`, {
    method: 'POST',
  });

export const clearCabinetReferenceImage = (cabinetId) =>
  request(`/api/cabinets/${encodeURIComponent(cabinetId)}/reference-image`, { method: 'DELETE' });

// Inspections — backend takes photos directly (multipart) with the design_revision_id.
export function createInspection(cabinetId, { designRevisionId, photos }) {
  const form = new FormData();
  form.append('design_revision_id', designRevisionId);
  for (const p of photos) form.append('photos', p, p.name || 'photo.jpg');
  return request(`/api/cabinets/${encodeURIComponent(cabinetId)}/inspections`, {
    method: 'POST',
    body: form,
  });
}

// Trigger the inspection run (observations + comparison).
export const runInspection = (inspectionId) =>
  request(`/api/inspections/${encodeURIComponent(inspectionId)}/run`, { method: 'POST' });

export async function getInspection(inspectionId) {
  if (inspectionId === 'synthetic' || inspectionId === 'INS-SYNTH-849') {
    return syntheticData.inspection;
  }
  return request(`/api/inspections/${encodeURIComponent(inspectionId)}`);
}

// Read raw Contract B observations across all images for an inspection
export const getInspectionObservations = (inspectionId) =>
  request(`/api/inspections/${encodeURIComponent(inspectionId)}/observations`);

// Reviews & Reinspections
export const reviewFinding = (findingId, reviewPayload) =>
  request(`/api/findings/${encodeURIComponent(findingId)}/review`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(reviewPayload),
  });

export const requestReinspection = (inspectionId, notes = '') =>
  request(`/api/inspections/${encodeURIComponent(inspectionId)}/reinspection`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ notes }),
  });

// Fit Feasibility & Replacement Assessment
export async function getFitFeasibility(inspectionId, findingId) {
  if (inspectionId === 'synthetic' || inspectionId?.includes('SYNTH')) {
    return {
      finding_id: findingId || 'F-004',
      tag: 'IO21',
      component_type: 'io_module',
      expected_part_number: 'VE4001S2T2B1',
      slot_status: 'unoccupied_verified',
      available_width_mm: 36.0,
      available_height_mm: 110.0,
      available_depth_mm: 75.0,
      mounting_type: 'DIN-rail 35mm',
      scale_calibration: 'reference_drawing_bom',
      candidates: [
        {
          candidate_part_number: 'VE4001S2T2B1',
          manufacturer: 'Emerson',
          model_name: 'DeltaV 16-Channel DI Card',
          classification: 'Compatible',
          reasons: ['Candidate satisfies all evaluated physical, mounting, and specification constraints.'],
          evaluated_constraints: {
            mounting: 'OK: DIN-rail 35mm',
            width: 'OK: 36.0mm fits within available 36.0mm',
            height: 'OK: 110.0mm within vertical envelope',
            depth: 'OK: 75.0mm standard DIN clearance',
          },
          reference_values: { candidate_width_mm: 36.0, candidate_mounting: 'DIN-rail 35mm' },
          measured_values: { available_width_mm: 36.0 },
          uncertainty_notes: [],
          safety_disclaimer:
            'Physical fit feasibility check only. Physical fit does NOT imply electrical safety, thermal suitability, or protection coordination. Verify electrical specifications with a qualified engineer before installation.',
        },
        {
          candidate_part_number: 'A9N2P16C',
          manufacturer: 'Schneider Electric',
          model_name: 'Acti9 C60H-DC',
          classification: 'Potentially compatible',
          reasons: ['Candidate fits mechanical envelope but has component type difference requiring engineering approval.'],
          evaluated_constraints: {
            mounting: 'OK: DIN-rail 35mm',
            width: 'OK: 36.0mm fits within available 36.0mm',
            depth: 'OK: standard clearance',
            type: 'POTENTIAL_MISMATCH: Candidate is mcb; expected io_module',
          },
          reference_values: { candidate_width_mm: 36.0, candidate_mounting: 'DIN-rail 35mm' },
          measured_values: { available_width_mm: 36.0 },
          uncertainty_notes: ['Image uncalibrated: dimensions derived from reference drawing specifications.'],
          safety_disclaimer:
            'Physical fit feasibility check only. Physical fit does NOT imply electrical safety, thermal suitability, or protection coordination. Verify electrical specifications with a qualified engineer before installation.',
        },
      ],
    };
  }
  return request(`/api/inspections/${encodeURIComponent(inspectionId)}/findings/${encodeURIComponent(findingId)}/fit-feasibility`);
}

// Quality Passport
export async function getQualityPassport(cabinetId) {
  if (cabinetId === 'CAB-2024-X401' || cabinetId === 'CAB-SYNTHETIC') {
    return syntheticData.passport;
  }
  return request(`/api/cabinets/${encodeURIComponent(cabinetId)}/quality-passport`);
}

// Report and Export (§2.5)
export const getReportUrl = (inspectionId) =>
  `${API_URL}/api/inspections/${encodeURIComponent(inspectionId)}/report`;

export const getExportCsvUrl = (inspectionId) =>
  `${API_URL}/api/inspections/${encodeURIComponent(inspectionId)}/export.csv`;

export function downloadFindingsCsv(inspectionId, findings = []) {
  const headers = ['Finding ID', 'Type', 'Tag', 'Status', 'Expected Rating', 'Observed Reading', 'Reason'];
  const rows = findings.map((f) => [
    f.finding_id,
    f.type || '',
    f.tag || f.observed_tag || f.expected_tag || '',
    f.status || '',
    `"${(f.expected_rating || f.expected_value || '').replace(/"/g, '""')}"`,
    `"${(f.observed_rating || f.observed_text || '').replace(/"/g, '""')}"`,
    `"${(f.reason || '').replace(/"/g, '""')}"`,
  ]);
  const csvContent = 'data:text/csv;charset=utf-8,' + [headers.join(','), ...rows.map((r) => r.join(','))].join('\n');
  const encodedUri = encodeURI(csvContent);
  const link = document.createElement('a');
  link.setAttribute('href', encodedUri);
  link.setAttribute('download', `inspection-${inspectionId}-findings.csv`);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

// Analytics (§3.1, contract D)
export async function getAnalytics(from, to) {
  const params = new URLSearchParams();
  if (from) params.set('from', from);
  if (to) params.set('to', to);
  const query = params.toString() ? `?${params.toString()}` : '';
  return request(`/api/analytics${query}`);
}

// QR Traceability (§3.2)
export const getCabinetQrUrl = (cabinetId) =>
  `${API_URL}/api/cabinets/${encodeURIComponent(cabinetId)}/qr`;

// Ghost Overlay & 4-Point Alignment (§3.4, contract E)
export const saveAlignment = (imageId, payload) =>
  request(`/api/images/${encodeURIComponent(imageId)}/alignment`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

export const getAlignment = (imageId) =>
  request(`/api/images/${encodeURIComponent(imageId)}/alignment`);

export const deleteAlignment = (imageId) =>
  request(`/api/images/${encodeURIComponent(imageId)}/alignment`, {
    method: 'DELETE',
  });

export const getDrawingPageUrl = (revisionId, page = 1, width = 2000) =>
  `${API_URL}/api/design-revisions/${encodeURIComponent(revisionId)}/drawing-pages/${encodeURIComponent(page)}.png?width=${width}`;

// Helper to provide synthetic fallbacks when backend endpoints return 404 or are unreachable
export { syntheticData };

