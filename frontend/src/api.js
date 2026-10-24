// All backend calls go through here. Base URL comes from VITE_API_URL.
import syntheticData from './mocks/inspection.synthetic.json';

export const API_URL = import.meta.env.VITE_API_URL ?? 'http://127.0.0.1:8000';

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
  try {
    response = await fetch(`${API_URL}${path}`, options);
  } catch {
    throw new ApiError(
      `Cannot reach the backend server at ${API_URL}. Please ensure the API is running or switch to synthetic mode.`,
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
  try {
    return await request(`/api/analytics${query}`);
  } catch (err) {
    if (err.isUnavailable || err.status === 404) {
      return syntheticData.analytics;
    }
    throw err;
  }
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

