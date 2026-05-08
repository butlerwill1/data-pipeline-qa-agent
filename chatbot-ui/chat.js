/* Summary: UI state and polling flow for the local phase 1 QA operator console. */

/*
 * chat.js is the browser-side coordinator. It owns transient UI state, reads
 * form values, calls api.js, and passes snapshot data to renderers.js. The
 * backend remains the source of truth for run status and artifacts.
 */

const appState = {
  // Active or replayed run ID. Null means the workspace is on the welcome state.
  currentRunId: null,
  // setInterval handle for polling an active run.
  pollTimer: null,
  // Prevents duplicate status cards when the same status/node pair is polled.
  lastStatusKey: null,
  // Tracks rendered pending-question groups by question IDs.
  renderedQuestionKeys: new Set(),
  // Tracks runs whose final report/findings/query pack have already been shown.
  renderedArtifactsForRun: new Set(),
  // Separate interval for the recent-runs sidebar.
  runsListTimer: null,
};

const NODE_LABELS = {
  // Backend graph node names are implementation-oriented; these labels are
  // operator-facing and reused in status cards and summary fields.
  ask_business_context: 'Waiting for operator context',
  extract_pipeline_logic: 'Extracting pipeline logic',
  generate_qa_checks: 'Generating QA checks',
  identify_knowledge_gaps: 'Looking for missing context',
  interpret_results: 'Interpreting query results',
  load_inputs: 'Loading run inputs',
  persist_run: 'Persisting run state',
  profile_tables: 'Profiling tables and metadata',
  queued: 'Queued for execution',
  retrieve_prior_understanding: 'Retrieving prior table context',
  run_qa_queries: 'Running generated SQL checks',
  update_table_understanding: 'Updating table understanding',
  write_final_report: 'Writing final report',
};

const STATUS_COPY = {
  // Normalised display labels for run lifecycle states.
  awaiting_user: 'Awaiting user',
  complete: 'Complete',
  failed: 'Failed',
  running: 'Running',
  stopped: 'Stopped',
  stopping: 'Stopping',
  submitted: 'Submitted',
};

const refs = {};

function init() {
  /*
   * Cache DOM references once at startup. This avoids repeated lookups during
   * polling and keeps the rest of the file explicit about which elements it
   * mutates.
   */
  refs.runForm = document.getElementById('run-form');
  refs.newRunButton = document.getElementById('new-run-btn');
  refs.startRunButton = document.getElementById('start-run-btn');
  refs.stopRunButton = document.getElementById('stop-run-btn');
  refs.welcome = document.getElementById('welcome');
  refs.chat = document.getElementById('chat');
  refs.messages = document.getElementById('messages');
  refs.workspaceColumn = document.getElementById('workspace-column');
  refs.statusBadge = document.getElementById('status-badge');
  refs.statusText = document.getElementById('status-text');
  refs.summaryStatus = document.getElementById('summary-status');
  refs.summaryNode = document.getElementById('summary-node');
  refs.summaryRunId = document.getElementById('summary-run-id');
  refs.summaryPipeline = document.getElementById('summary-pipeline');
  refs.summaryUpdated = document.getElementById('summary-updated');
  refs.metricPending = document.getElementById('metric-pending');
  refs.metricQueries = document.getElementById('metric-queries');
  refs.metricFindings = document.getElementById('metric-findings');
  refs.artifactSummary = document.getElementById('artifact-summary');
  refs.pipelinePath = document.getElementById('pipeline-path');
  refs.sourceTables = document.getElementById('source-tables');
  refs.destinationTables = document.getElementById('destination-tables');
  refs.businessContext = document.getElementById('business-context');
  refs.runsList = document.getElementById('runs-list');

  refs.runForm.addEventListener('submit', handleRunSubmit);
  refs.newRunButton.addEventListener('click', resetWorkspace);
  refs.stopRunButton.addEventListener('click', handleStopRun);

  window.submitPendingAnswers = submitPendingAnswers;
  window.copyStoredText = copyStoredText;
  window.loadHistoricalRun = loadHistoricalRun;
  window.fillAllAndSubmit = fillAllAndSubmit;

  // The history panel is useful even before a new run is submitted, so it starts
  // polling independently from the active-run poller.
  refreshRunsList();
  appState.runsListTimer = window.setInterval(refreshRunsList, 5000);

  getHealth().catch(() => {
    addBotMessage(
      renderInfoCard(
        'Backend health check failed',
        '<p>The UI loaded, but the API health check did not respond. Start the FastAPI server before running QA jobs.</p>',
        { kicker: 'Startup', tone: 'error' }
      )
    );
  });
}

function parseTableList(rawValue) {
  // Accept comma-separated, semicolon-separated, or whitespace-separated table
  // lists so operators can paste values from several common sources.
  return rawValue
    .split(/[\s,;]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function showChat() {
  // Swap the empty welcome panel for the live conversation area.
  refs.welcome.style.display = 'none';
  refs.chat.style.display = 'block';
}

function scrollToBottom() {
  // The workspace column owns scrolling; chat is kept visible so long cards can
  // expand without introducing nested scroll traps.
  refs.chat.scrollTop = refs.chat.scrollHeight;
  refs.workspaceColumn.scrollTop = refs.workspaceColumn.scrollHeight;
}

function resetWorkspace() {
  /*
   * Clears only browser state. Saved Mongo records and historical runs remain
   * available through the sidebar.
   */
  window.clearInterval(appState.pollTimer);
  appState.pollTimer = null;
  appState.currentRunId = null;
  appState.lastStatusKey = null;
  appState.renderedQuestionKeys = new Set();
  appState.renderedArtifactsForRun = new Set();
  refs.messages.innerHTML = '';
  refs.welcome.style.display = 'flex';
  refs.chat.style.display = 'none';
  setStatus('idle');
  setFormBusy(false);
  refs.stopRunButton.disabled = true;
  updateSummary(null);
  refs.artifactSummary.className = 'artifact-summary empty';
  refs.artifactSummary.textContent = 'No report yet.';
  refreshRunsList();
}

function setFormBusy(isBusy) {
  // Prevent duplicate submissions while the backend is creating a run.
  refs.startRunButton.disabled = isBusy;
}

function setStatus(status) {
  // Updates both visible text and data-state so CSS can recolour the status dot.
  const normalized = status || 'idle';
  refs.statusBadge.dataset.state = normalized;
  refs.statusText.textContent = STATUS_COPY[normalized] || normalized.replace(/_/g, ' ');
}

function friendlyNode(node) {
  // Fall back to a readable version of unknown node names instead of hiding them.
  return NODE_LABELS[node] || (node ? node.replace(/_/g, ' ') : 'None');
}

function updateSummary(snapshot) {
  /*
   * The left sidebar mirrors the latest snapshot. It is called for active polls,
   * historical runs, answers, stop requests, and resets.
   */
  if (!snapshot) {
    refs.summaryStatus.textContent = 'Idle';
    refs.summaryNode.textContent = 'None';
    refs.summaryRunId.textContent = 'Not started';
    refs.summaryPipeline.textContent = 'Not selected';
    refs.summaryUpdated.textContent = 'No run activity yet.';
    refs.metricPending.textContent = '0';
    refs.metricQueries.textContent = '0';
    refs.metricFindings.textContent = '0';
    refs.stopRunButton.disabled = true;
    return;
  }

  const run = snapshot.run || {};
  const summary = snapshot.summary || {};

  refs.summaryStatus.textContent = STATUS_COPY[run.status] || run.status || 'Unknown';
  refs.summaryNode.textContent = friendlyNode(run.current_node);
  refs.summaryRunId.textContent = run.run_id || 'Not started';
  refs.summaryPipeline.textContent = run.pipeline_path || 'Not selected';
  refs.summaryUpdated.textContent = run.updated_at
    ? `Last update ${formatDateTime(run.updated_at)}`
    : 'Waiting for first update.';
  refs.metricPending.textContent = String(summary.pending_questions || 0);
  refs.metricQueries.textContent = String(summary.executed_queries || 0);
  refs.metricFindings.textContent = String(summary.findings || 0);
  refs.stopRunButton.disabled = !['submitted', 'running', 'awaiting_user', 'stopping'].includes(run.status);

  const severity = summary.severity_summary || { pass: 0, warn: 0, fail: 0 };
  const documents = snapshot.documents || [];
  if (documents.length) {
    // The artifact panel shows the first generated document and aggregate
    // severities. Full document content is rendered in the chat stream.
    const report = documents[0];
    refs.artifactSummary.className = 'artifact-summary';
    refs.artifactSummary.innerHTML = `
      <div class="artifact-line"><span>Pass</span><strong>${severity.pass || 0}</strong></div>
      <div class="artifact-line"><span>Warn</span><strong>${severity.warn || 0}</strong></div>
      <div class="artifact-line"><span>Fail</span><strong>${severity.fail || 0}</strong></div>
      <a class="doc-link" href="${escAttr(report.download_url)}" target="_blank" rel="noreferrer">
        Open report markdown
      </a>
    `;
  } else {
    refs.artifactSummary.className = 'artifact-summary empty';
    refs.artifactSummary.textContent = 'No report yet.';
  }
}

function addMessage(innerHtml, role = 'bot') {
  // Appends a single chat message shell. innerHtml is expected to come from a
  // renderer helper or from already-escaped local strings.
  const wrapper = document.createElement('div');
  wrapper.className = `msg ${role}`;
  wrapper.innerHTML = `
    <div class="avatar ${role}">${role === 'bot' ? 'QA' : 'OP'}</div>
    <div class="msg-body">${innerHtml}</div>
  `;
  refs.messages.appendChild(wrapper);
  scrollToBottom();
}

function addBotMessage(innerHtml) {
  // Bot messages are the primary way status cards, reports, and evidence packs
  // enter the workspace.
  showChat();
  addMessage(innerHtml, 'bot');
}

function addUserMessage(text, chips = []) {
  // Operator actions are reflected as compact right-aligned bubbles.
  const chipHtml = chips.length
    ? `<div class="run-chip-list">${chips.map((chip) => `<span class="run-chip">${esc(chip)}</span>`).join('')}</div>`
    : '';
  addMessage(
    `
      <div class="user-bubble">
        <div class="message-title">${esc(text)}</div>
        ${chipHtml}
      </div>
    `,
    'user'
  );
}

function announceStatus(snapshot) {
  /*
   * Render a status card only when the run status or current graph node changes.
   * Polling can return the same snapshot many times while a node is working.
   */
  const run = snapshot.run || {};
  const statusKey = `${run.status || 'unknown'}:${run.current_node || 'none'}`;
  if (appState.lastStatusKey === statusKey) {
    return;
  }
  appState.lastStatusKey = statusKey;

  const details = [];
  if (run.pipeline_path) details.push(`<p><strong>Pipeline:</strong> ${esc(run.pipeline_path)}</p>`);
  if (run.error) details.push(`<p><strong>Error:</strong> ${esc(run.error)}</p>`);
  if (!details.length) {
    details.push('<p>The run is progressing through the graph nodes stored in Mongo-backed state.</p>');
  }

  addBotMessage(
    renderInfoCard(
      STATUS_COPY[run.status] || 'Run update',
      details.join(''),
      {
        kicker: friendlyNode(run.current_node),
        tone: run.status === 'failed' ? 'error' : run.status === 'awaiting_user' ? 'warn' : 'default',
        chips: [
          `Status: ${STATUS_COPY[run.status] || run.status || 'unknown'}`,
          `Node: ${friendlyNode(run.current_node)}`,
        ],
      }
    )
  );
}

function syncQuestions(snapshot) {
  /*
   * When the backend pauses with awaiting_user, render unanswered questions once.
   * The question IDs form a stable key so repeat polls do not duplicate the form.
   */
  if (snapshot.run?.status !== 'awaiting_user') {
    return;
  }
  const pendingQuestions = snapshot.pending_questions || [];
  if (!pendingQuestions.length) {
    return;
  }

  const questionKey = pendingQuestions.map((question) => question.question_id).join(':');
  if (appState.renderedQuestionKeys.has(questionKey)) {
    return;
  }
  appState.renderedQuestionKeys.add(questionKey);

  addBotMessage(
    renderInfoCard(
      'Operator input required',
      renderQuestionForm(snapshot.run.run_id, pendingQuestions),
      {
        kicker: 'Follow-up questions',
        tone: 'warn',
      }
    )
  );
}

function syncArtifacts(snapshot) {
  /*
   * Final artifacts are shown once per run. A completed snapshot can be seen by
   * the active poller and again through history replay, so this guard prevents
   * duplicate report, findings, and query cards in the same workspace view.
   */
  const runId = snapshot.run?.run_id;
  if (!runId || !snapshot.report || appState.renderedArtifactsForRun.has(runId)) {
    return;
  }

  appState.renderedArtifactsForRun.add(runId);

  addBotMessage(
    renderMarkdownDocument(
      'Final QA report',
      snapshot.report.markdown || '',
      snapshot.documents?.[0]?.download_url
    )
  );

  if (snapshot.findings?.length) {
    addBotMessage(renderFindings(snapshot.findings));
  }

  if (snapshot.executed_queries?.length) {
    addBotMessage(renderQueryResults(snapshot.executed_queries));
  }
}

function syncSnapshot(snapshot) {
  /*
   * Central reconciliation point. Every backend response that contains a full
   * snapshot flows through here so status, sidebar summary, questions, and
   * artifacts stay in sync.
   */
  setStatus(snapshot.run?.status || 'idle');
  updateSummary(snapshot);
  announceStatus(snapshot);
  syncQuestions(snapshot);
  syncArtifacts(snapshot);

  const isFinished = ['complete', 'failed'].includes(snapshot.run?.status || '');
  if (snapshot.run?.status === 'stopped') {
    setFormBusy(false);
  }
  if (isFinished) {
    window.clearInterval(appState.pollTimer);
    appState.pollTimer = null;
    setFormBusy(false);
  }
  if (snapshot.run?.status === 'stopped') {
    window.clearInterval(appState.pollTimer);
    appState.pollTimer = null;
  }
}

async function pollCurrentRun() {
  // Poll only when a run is selected. Failures stop the active poller and render
  // an error card instead of silently leaving stale state on screen.
  if (!appState.currentRunId) return;

  try {
    const snapshot = await getRun(appState.currentRunId);
    syncSnapshot(snapshot);
  } catch (error) {
    addBotMessage(
      renderInfoCard(
        'Polling failed',
        `<p>${esc(error.message)}</p>`,
        { kicker: 'Network', tone: 'error' }
      )
    );
    window.clearInterval(appState.pollTimer);
    appState.pollTimer = null;
    setFormBusy(false);
  }
}

function startPolling() {
  // Restarting clears any older interval so answer submission, history loading,
  // or run creation never leaves multiple active pollers.
  window.clearInterval(appState.pollTimer);
  appState.pollTimer = window.setInterval(pollCurrentRun, API.pollIntervalMs);
}

async function handleRunSubmit(event) {
  /*
   * Form submission path:
   * 1. Build the create-run payload from form fields.
   * 2. Reset the local workspace.
   * 3. POST to the backend.
   * 4. Render the returned snapshot and begin polling.
   */
  event.preventDefault();

  const payload = {
    pipeline_path: refs.pipelinePath.value.trim(),
    source_tables: parseTableList(refs.sourceTables.value),
    destination_tables: parseTableList(refs.destinationTables.value),
    business_context_seed: refs.businessContext.value.trim() || null,
  };

  if (!payload.pipeline_path) {
    addBotMessage(
      renderInfoCard(
        'Pipeline path required',
        '<p>Choose a local pipeline file before starting a QA run.</p>',
        { kicker: 'Validation', tone: 'error' }
      )
    );
    return;
  }

  resetWorkspace();
  setFormBusy(true);

  addUserMessage('Started a new QA run', [
    payload.pipeline_path,
    `${payload.source_tables.length} source table${payload.source_tables.length === 1 ? '' : 's'}`,
    `${payload.destination_tables.length} destination table${payload.destination_tables.length === 1 ? '' : 's'}`,
  ]);

  try {
    const snapshot = await createRun(payload);
    appState.currentRunId = snapshot.run.run_id;
    syncSnapshot(snapshot);
    refreshRunsList();
    startPolling();
  } catch (error) {
    setFormBusy(false);
    addBotMessage(
      renderInfoCard(
        'Run submission failed',
        `<p>${esc(error.message)}</p>`,
        { kicker: 'API', tone: 'error' }
      )
    );
  }
}

async function submitPendingAnswers(event) {
  /*
   * Reads all question textareas generated by renderQuestionForm(). The backend
   * receives exact question IDs with operator-provided answer text.
   */
  event.preventDefault();
  const form = event.target;
  const runId = form.getAttribute('data-run-id');
  const textareas = Array.from(form.querySelectorAll('.question-answer'));

  const answers = textareas.map((textarea) => ({
    question_id: textarea.getAttribute('data-question-id'),
    answer: textarea.value.trim(),
  }));

  if (answers.some((answer) => !answer.answer)) {
    addBotMessage(
      renderInfoCard(
        'Answers missing',
        '<p>Complete every follow-up question before resuming the run.</p>',
        { kicker: 'Validation', tone: 'error' }
      )
    );
    return;
  }

  const submitButton = form.querySelector('.question-submit');
  submitButton.disabled = true;
  submitButton.textContent = 'Submitting answers...';

  try {
    const snapshot = await submitAnswers(runId, answers);
    addUserMessage(`Submitted ${answers.length} follow-up answer${answers.length === 1 ? '' : 's'}`, []);
    syncSnapshot(snapshot);
    startPolling();
  } catch (error) {
    submitButton.disabled = false;
    submitButton.textContent = 'Resume QA run';
    addBotMessage(
      renderInfoCard(
        'Answer submission failed',
        `<p>${esc(error.message)}</p>`,
        { kicker: 'API', tone: 'error' }
      )
    );
  }
}

async function handleStopRun() {
  // Stop is cooperative. The backend marks the run as stopping/stopped and the
  // poller keeps watching if more state changes are expected.
  if (!appState.currentRunId) return;

  refs.stopRunButton.disabled = true;

  try {
    const snapshot = await stopRun(appState.currentRunId);
    addUserMessage('Requested agent stop');
    syncSnapshot(snapshot);
    if (snapshot.run?.status === 'stopping') {
      startPolling();
    }
  } catch (error) {
    refs.stopRunButton.disabled = false;
    addBotMessage(
      renderInfoCard(
        'Stop request failed',
        `<p>${esc(error.message)}</p>`,
        { kicker: 'API', tone: 'error' }
      )
    );
  }
}

function fillAllAndSubmit(event) {
  /*
   * Convenience path for local testing and repeatable demos. It copies the
   * default answer into every generated question textarea, then submits the form.
   */
  const form = event.target.closest('form.question-form');
  if (!form) return;
  const defaultText = (form.querySelector('.question-default-text')?.value || '').trim();
  if (!defaultText) {
    addBotMessage(
      renderInfoCard(
        'Default answer empty',
        '<p>Provide a default answer in the textarea before using "Fill all and submit".</p>',
        { kicker: 'Validation', tone: 'error' }
      )
    );
    return;
  }
  form.querySelectorAll('textarea.question-answer').forEach((ta) => {
    ta.value = defaultText;
  });
  form.requestSubmit();
}

async function refreshRunsList() {
  // Runs independently of the active run poller so completed work appears in
  // history even after the main run loop stops.
  if (!refs.runsList) return;
  try {
    const payload = await listRuns(20);
    const runs = (payload && payload.runs) || [];
    renderRunsList(runs);
  } catch (error) {
    refs.runsList.innerHTML = `<div class="runs-empty">Could not load runs.</div>`;
  }
}

function renderRunsList(runs) {
  // The recent-runs sidebar is rebuilt from scratch on each refresh because it
  // is small and avoids manual diffing of active/history state.
  if (!runs.length) {
    refs.runsList.innerHTML = '<div class="runs-empty">No runs yet.</div>';
    return;
  }
  refs.runsList.innerHTML = runs
    .map((run) => {
      const isActive = run.run_id === appState.currentRunId;
      const ts = run.started_at ? formatDateTime(run.started_at) : '';
      const pipelineLabel = (run.pipeline_path || '')
        .split('/').pop() || 'pipeline';
      const sev = run.severity_summary || {};
      const sevChips = (sev.pass || sev.warn || sev.fail)
        ? `<span class="run-sev-pass">${sev.pass || 0}</span>
           <span class="run-sev-warn">${sev.warn || 0}</span>
           <span class="run-sev-fail">${sev.fail || 0}</span>`
        : '';
      return `
        <button
          type="button"
          class="run-item ${isActive ? 'active' : ''}"
          data-run-id="${escAttr(run.run_id)}"
          onclick="loadHistoricalRun('${escAttr(run.run_id)}')"
        >
          <div class="run-item-row">
            <span class="status-pill status-${statusClass(run.status)}">${esc(statusLabel(run.status))}</span>
            ${sevChips ? `<span class="run-sev">${sevChips}</span>` : ''}
          </div>
          <div class="run-item-pipeline" title="${escAttr(run.pipeline_path || '')}">${esc(pipelineLabel)}</div>
          <div class="run-item-meta">
            <span class="run-item-id">${esc(run.run_id.slice(0, 8))}</span>
            ${ts ? `<span class="run-item-time">${esc(ts)}</span>` : ''}
          </div>
        </button>
      `;
    })
    .join('');
}

async function loadHistoricalRun(runId) {
  /*
   * History replay clears the chat stream, loads one saved snapshot, and renders
   * it through the same sync path as an active run. If the selected run is still
   * active, polling resumes from that point.
   */
  if (!runId) return;
  if (appState.currentRunId === runId && appState.pollTimer) return;

  window.clearInterval(appState.pollTimer);
  appState.pollTimer = null;
  appState.currentRunId = runId;
  appState.lastStatusKey = null;
  appState.renderedQuestionKeys = new Set();
  appState.renderedArtifactsForRun = new Set();

  refs.messages.innerHTML = '';
  refs.welcome.style.display = 'none';
  refs.chat.style.display = 'block';
  refs.artifactSummary.className = 'artifact-summary empty';
  refs.artifactSummary.textContent = 'Loading...';
  setFormBusy(false);

  try {
    const snapshot = await getRun(runId);
    addBotMessage(
      renderInfoCard(
        'Loaded historical run',
        `<p>Replaying the recorded state for run <code>${esc(runId.slice(0, 8))}</code>. The findings, queries, and report below were produced during the original execution.</p>`,
        { kicker: 'History', tone: 'default' }
      )
    );
    syncSnapshot(snapshot);
    refreshRunsList();
    if (['running', 'awaiting_user', 'submitted'].includes(snapshot.run?.status)) {
      startPolling();
    }
  } catch (error) {
    addBotMessage(
      renderInfoCard(
        'Could not load run',
        `<p>${esc(error.message)}</p>`,
        { kicker: 'History', tone: 'error' }
      )
    );
  }
}

window.addEventListener('DOMContentLoaded', init);
