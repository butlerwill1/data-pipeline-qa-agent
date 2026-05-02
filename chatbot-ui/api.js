/* Summary: Browser API helpers for the local phase 1 run-oriented QA backend. */

const API = {
  base: '/api',
  defaultHeaders: {
    'Content-Type': 'application/json',
  },
  pollIntervalMs: 2500,
};

async function request(path, options = {}) {
  const response = await fetch(`${API.base}${path}`, {
    headers: API.defaultHeaders,
    ...options,
  });

  const contentType = response.headers.get('content-type') || '';
  const payload = contentType.includes('application/json')
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    const detail = typeof payload === 'string' ? payload : payload.detail;
    throw new Error(detail || `Request failed with status ${response.status}`);
  }

  return payload;
}

async function createRun(payload) {
  return request('/runs', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

async function getRun(runId) {
  return request(`/runs/${encodeURIComponent(runId)}`);
}

async function listRuns(limit = 20) {
  return request(`/runs?limit=${encodeURIComponent(limit)}`);
}

async function submitAnswers(runId, answers) {
  return request(`/runs/${encodeURIComponent(runId)}/answers`, {
    method: 'POST',
    body: JSON.stringify({ answers }),
  });
}

async function stopRun(runId) {
  return request(`/runs/${encodeURIComponent(runId)}/stop`, {
    method: 'POST',
  });
}

async function getHealth() {
  return request('/health');
}
