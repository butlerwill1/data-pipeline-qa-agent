/* Summary: Browser API helpers for the local phase 1 run-oriented QA backend. */

/*
 * This file is the frontend's only direct dependency on the FastAPI route
 * contract. Keeping fetch details here means the rest of the UI can work with
 * small domain functions such as createRun() or submitAnswers() instead of
 * repeating URL construction, JSON headers, and error parsing.
 */

const API = {
  // The FastAPI app serves the static UI and API from the same origin, so a
  // relative base path works both on localhost and wherever the app is mounted.
  base: '/api',
  defaultHeaders: {
    'Content-Type': 'application/json',
  },
  // chat.js uses this cadence while a run is active. It is intentionally slow
  // enough to avoid hammering Mongo-backed state while still feeling live.
  pollIntervalMs: 2500,
};

async function request(path, options = {}) {
  /*
   * Shared fetch wrapper:
   * 1. Prefixes all requests with /api.
   * 2. Sends JSON headers by default.
   * 3. Parses JSON responses when present, otherwise falls back to text.
   * 4. Raises an Error with the backend's detail message for UI cards.
   */
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
  // Starts a new graph run. The response is already a full run snapshot, so
  // chat.js can render immediately before starting the polling loop.
  return request('/runs', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

async function getRun(runId) {
  // Polls or loads a single run snapshot. Historical run replay uses the same
  // endpoint as active polling.
  return request(`/runs/${encodeURIComponent(runId)}`);
}

async function listRuns(limit = 20) {
  // Feeds the sidebar history list. The backend clamps the final limit.
  return request(`/runs?limit=${encodeURIComponent(limit)}`);
}

async function submitAnswers(runId, answers) {
  // Sends operator answers for pending questions and lets the backend resume
  // the paused graph run.
  return request(`/runs/${encodeURIComponent(runId)}/answers`, {
    method: 'POST',
    body: JSON.stringify({ answers }),
  });
}

async function stopRun(runId) {
  // Requests a cooperative stop. The backend returns the latest run snapshot so
  // the UI can update status immediately.
  return request(`/runs/${encodeURIComponent(runId)}/stop`, {
    method: 'POST',
  });
}

async function getHealth() {
  // Startup probe used to show a helpful message if the static UI loads without
  // a reachable FastAPI backend.
  return request('/health');
}
