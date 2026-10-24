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
export const createCabinet = (data) =>
  request('/api/cabinets', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });

// Design Revisions
export const createDesignRevision = (cabinetId, drawingUploadId) =>
  request(`/api/cabinets/${encodeURIComponent(cabinetId)}/design-revisions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ drawing_upload_id: drawingUploadId }),
  });

// Inspections
export const createInspection = (cabinetId, photoUploadIds) =>
  request(`/api/cabinets/${encodeURIComponent(cabinetId)}/inspections`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ photo_upload_ids: photoUploadIds }),
  });

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

// Helper to provide synthetic fallbacks when backend endpoints return 404 or are unreachable
export { syntheticData };

