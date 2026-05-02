/* Summary: UI state and polling flow for the local phase 1 QA operator console. */

const appState = {
  currentRunId: null,
  pollTimer: null,
  lastStatusKey: null,
  renderedQuestionKeys: new Set(),
  renderedArtifactsForRun: new Set(),
  runsListTimer: null,
};

const NODE_LABELS = {
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
  return rawValue
    .split(/[\s,;]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function showChat() {
  refs.welcome.style.display = 'none';
  refs.chat.style.display = 'block';
}

function scrollToBottom() {
  refs.chat.scrollTop = refs.chat.scrollHeight;
  refs.workspaceColumn.scrollTop = refs.workspaceColumn.scrollHeight;
}

function resetWorkspace() {
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
  refs.startRunButton.disabled = isBusy;
}

function setStatus(status) {
  const normalized = status || 'idle';
  refs.statusBadge.dataset.state = normalized;
  refs.statusText.textContent = STATUS_COPY[normalized] || normalized.replace(/_/g, ' ');
}

function friendlyNode(node) {
  return NODE_LABELS[node] || (node ? node.replace(/_/g, ' ') : 'None');
}

function updateSummary(snapshot) {
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
  showChat();
  addMessage(innerHtml, 'bot');
}

function addUserMessage(text, chips = []) {
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
  window.clearInterval(appState.pollTimer);
  appState.pollTimer = window.setInterval(pollCurrentRun, API.pollIntervalMs);
}

async function handleRunSubmit(event) {
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

async function refreshRunsList() {
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
