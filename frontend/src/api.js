// All backend calls go through here. Base URL comes from VITE_API_URL (see .env.example).
export const API_URL = import.meta.env.VITE_API_URL ?? 'http://127.0.0.1:8000';

async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(`${API_URL}${path}`, options);
  } catch {
    throw new Error(`Cannot reach the backend at ${API_URL}. Is it running?`);
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    // FastAPI puts the reason in "detail"; show it instead of failing silently.
    const detail = typeof body?.detail === 'string' ? body.detail : JSON.stringify(body?.detail ?? body);
    throw new Error(detail || `Request failed with status ${response.status}`);
  }
  return body;
}

export const getHealth = () => request('/api/health');
export const getModelStatus = () => request('/api/model/status');

export function uploadFile(file) {
  const form = new FormData();
  form.append('file', file);
  return request('/api/uploads', { method: 'POST', body: form });
}

// Planned endpoints (docs/api-contract.md). They return 404 until Part 3 adds them.
export const getInspection = (id) => request(`/api/inspections/${encodeURIComponent(id)}`);
export const listCabinets = () => request('/api/cabinets');
export const getPassport = (cabinetId) =>
  request(`/api/cabinets/${encodeURIComponent(cabinetId)}/quality-passport`);
export const reviewFinding = (findingId, decision) =>
  request(`/api/findings/${encodeURIComponent(findingId)}/review`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(decision),
  });
