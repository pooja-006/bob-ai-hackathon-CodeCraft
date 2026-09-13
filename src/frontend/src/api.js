// Shared API fetch helper
const BASE = typeof import.meta !== 'undefined' ? '' : 'http://localhost:8000';

export async function apiFetch(path, options = {}) {
  const res = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export function yieldClass(y) {
  if (y >= 88) return 'good';
  if (y >= 82) return 'warn';
  return 'danger';
}

export function riskClass(label) {
  if (label === 'HIGH')   return 'HIGH';
  if (label === 'MEDIUM') return 'MEDIUM';
  return 'LOW';
}
