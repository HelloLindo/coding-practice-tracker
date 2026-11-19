// JSON API client for the local service. The token proves the request comes from this page.

const token = document.querySelector('meta[name="practice-token"]').content;

export class ApiError extends Error {
  constructor(message, status, details) {
    super(message);
    this.status = status;
    this.details = details || {};
  }
}

export async function api(path, data) {
  let response;
  try {
    response = await fetch(path, {
      method: data ? 'POST' : 'GET',
      headers: {'X-Practice-Token': token, ...(data ? {'Content-Type': 'application/json'} : {})},
      ...(data ? {body: JSON.stringify(data)} : {}),
    });
  } catch (_) {
    throw new ApiError('The local service is not reachable. Is web.command still running?', 0);
  }
  let result = {};
  try { result = await response.json(); } catch (_) { /* non-JSON error */ }
  if (!response.ok) throw new ApiError(result.error || 'The request could not be completed.', response.status, result);
  return result;
}

export function requestId() {
  if (crypto.randomUUID) return crypto.randomUUID();
  return Array.from(crypto.getRandomValues(new Uint8Array(16)), b => b.toString(16).padStart(2, '0')).join('');
}
