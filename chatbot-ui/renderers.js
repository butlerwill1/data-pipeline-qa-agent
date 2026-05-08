/* Summary: Rendering helpers for the local phase 1 QA operator console. */

/*
 * renderers.js is deliberately stateless except for storedText, which supports
 * copy buttons for generated SQL. chat.js decides when something should appear;
 * this file only turns structured snapshot data into HTML fragments.
 */

const storedText = {};

function esc(value) {
  // Escape text before inserting it into HTML. Most renderer inputs originate
  // from pipeline files, LLM output, query samples, or persisted run records.
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function escAttr(value) {
  // Attribute values need the normal HTML escaping plus quote protection.
  return esc(value).replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function formatDateTime(value) {
  // Keep all visible timestamps in one locale format so history cards and run
  // summary updates stay consistent.
  if (!value) return 'Not available';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return esc(String(value));
  return date.toLocaleString('en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function formatRuntime(ms) {
  // Query runtimes are stored in milliseconds; show sub-second runs precisely
  // and longer runs in compact seconds.
  if (ms == null) return 'Not timed';
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function statusLabel(status) {
  // Human-readable labels for run statuses and check severities. Unknown values
  // are still displayed after replacing underscores.
  const labels = {
    awaiting_user: 'Awaiting user',
    complete: 'Complete',
    failed: 'Failed',
    ok: 'Passed',
    running: 'Running',
    submitted: 'Submitted',
    timeout: 'Timed out',
  };
  return labels[status] || String(status || 'unknown').replace(/_/g, ' ');
}

function statusClass(status) {
  // Status values become CSS class suffixes, so strip anything unsafe.
  return String(status || 'unknown').replace(/[^a-z0-9_-]/gi, '-').toLowerCase();
}

function inlineFormat(text) {
  // Minimal inline markdown used for short controlled strings. Full report
  // markdown is handled by markdownToHtml().
  let html = esc(text);
  html = html.replace(/`([^`]+)`/g, '<code class="inline">$1</code>');
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');
  return html;
}

function markdownToHtml(markdown) {
  /*
   * Final reports are stored as Markdown. The page loads marked from a CDN for
   * GitHub-flavoured Markdown; if that script is unavailable, the raw report is
   * still shown safely in a preformatted block.
   */
  const text = String(markdown || '').trim();
  if (!text) return '<p>No report content available.</p>';
  if (typeof window.marked !== 'undefined') {
    window.marked.setOptions({ gfm: true, breaks: false, headerIds: false, mangle: false });
    return window.marked.parse(text);
  }
  // Fallback if CDN failed: minimal escape
  return `<pre>${esc(text)}</pre>`;
}

function fmtCell(value) {
  // Normalise table sample values before inserting them into evidence tables.
  if (value == null) return '<span class="empty-cell">null</span>';
  if (typeof value === 'number') return value.toLocaleString('en-GB');
  if (typeof value === 'object') return esc(JSON.stringify(value));
  return esc(String(value));
}

function renderTable(rows, options = {}) {
  // Query result samples are rendered from object arrays. The first row defines
  // the displayed column order, matching the shape returned by the backend.
  if (!rows || !rows.length) {
    return `<div class="table-empty">${esc(options.emptyMessage || 'No sample rows returned.')}</div>`;
  }

  const columns = Object.keys(rows[0]);
  const header = columns.map((column) => `<th>${esc(column)}</th>`).join('');
  const body = rows
    .map((row) => `<tr>${columns.map((column) => `<td>${fmtCell(row[column])}</td>`).join('')}</tr>`)
    .join('');

  return `
    <div class="table-wrap">
      <table class="data-table">
        <thead><tr>${header}</tr></thead>
        <tbody>${body}</tbody>
      </table>
    </div>
  `;
}

function renderInfoCard(title, bodyHtml, options = {}) {
  // Shared card shell for run updates, validation errors, questions, findings,
  // and query result groups. The caller owns bodyHtml and should escape values.
  const kicker = options.kicker
    ? `<div class="message-kicker">${esc(options.kicker)}</div>`
    : '';
  const chips = (options.chips || [])
    .map((chip) => `<span class="run-chip">${esc(chip)}</span>`)
    .join('');

  return `
    <div class="message-card ${options.tone ? `tone-${options.tone}` : ''}">
      ${kicker}
      <h3 class="message-title">${esc(title)}</h3>
      <div class="message-body">${bodyHtml}</div>
      ${chips ? `<div class="run-chip-list">${chips}</div>` : ''}
    </div>
  `;
}

function renderQuestionForm(runId, questions) {
  /*
   * The agent can pause for operator context. Each pending question receives a
   * textarea keyed by question_id so submitPendingAnswers() can send the exact
   * backend IDs back without guessing from visible text.
   */
  const blocks = questions
    .map((question, index) => `
      <div class="question-block">
        <div class="question-index">Question ${index + 1}</div>
        <div class="question-text">${esc(question.question || '')}</div>
        ${question.table_id ? `<div class="question-table">${esc(question.table_id)}</div>` : ''}
        ${
          question.why_it_matters
            ? `<p class="question-why">${esc(question.why_it_matters)}</p>`
            : ''
        }
        <textarea
          class="question-answer"
          data-question-id="${escAttr(question.question_id)}"
          placeholder="Add the operator context needed for the next QA step..."
          rows="4"
          required
        ></textarea>
      </div>
    `)
    .join('');

  const defaultAnswer = 'Standard expectations apply: data should be complete by 9am next day; '
    + 'negative consumption is invalid; expect peak_consumption between 0 and 5000 kWh; '
    + 'expect at least 48 readings per substation per day. Apply your best judgement for anything else.';

  return `
    <form class="question-form" data-run-id="${escAttr(runId)}" onsubmit="submitPendingAnswers(event)">
      <div class="question-default">
        <label class="question-default-label">Default answer (used by "Fill all and submit"):</label>
        <textarea class="question-default-text" rows="2">${esc(defaultAnswer)}</textarea>
      </div>
      ${blocks}
      <div class="question-actions">
        <button class="ghost-btn question-fill-all" type="button" onclick="fillAllAndSubmit(event)">
          Fill all and submit
        </button>
        <button class="primary-btn question-submit" type="submit">Resume QA run</button>
      </div>
    </form>
  `;
}

function renderFindings(findings) {
  // Findings are the high-level quality assessment records written by the graph.
  // Each card is tagged by severity for consistent colour treatment.
  const cards = findings
    .map((finding) => `
      <article class="finding-card severity-${statusClass(finding.severity)}">
        <div class="finding-top">
          <span class="status-pill status-${statusClass(finding.severity)}">${esc(statusLabel(finding.severity))}</span>
          ${finding.related_table ? `<span class="finding-table">${esc(finding.related_table)}</span>` : ''}
        </div>
        <h4>${esc(finding.title || 'Untitled finding')}</h4>
        <p>${esc(finding.evidence || 'No evidence provided.')}</p>
        ${
          finding.recommended_action
            ? `<div class="finding-action"><strong>Action:</strong> ${esc(finding.recommended_action)}</div>`
            : ''
        }
      </article>
    `)
    .join('');

  return renderInfoCard(
    'Findings',
    `<div class="finding-grid">${cards}</div>`,
    { kicker: 'Assessment' }
  );
}

function renderCode(title, sql) {
  // Store raw SQL under an opaque key so the copy button can copy unhighlighted
  // text while the visible code block receives simple syntax highlighting.
  const key = `stored-text-${Object.keys(storedText).length + 1}`;
  storedText[key] = sql;

  return `
    <div class="code-card">
      <div class="code-head">
        <div>
          <div class="code-kicker">${esc(title)}</div>
          <div class="code-label">Athena-compatible SQL</div>
        </div>
        <button class="ghost-btn" type="button" data-copy-key="${escAttr(key)}" onclick="copyStoredText(event)">
          Copy
        </button>
      </div>
      <pre class="code-body"><code>${hlSQL(esc(sql))}</code></pre>
    </div>
  `;
}

function renderQueryResults(queries) {
  /*
   * Executed checks combine metadata, generated SQL, optional errors, and sample
   * rows. This renderer keeps each check self-contained so long reports remain
   * scannable.
   */
  const cards = queries
    .map((query) => {
      const meta = [
        query.category ? `Category: ${query.category}` : null,
        query.target_table ? `Table: ${query.target_table}` : null,
        query.runtime_ms != null ? `Runtime: ${formatRuntime(query.runtime_ms)}` : null,
      ].filter(Boolean);

      let body = '';
      if (query.error) {
        body += `<div class="query-error">${esc(query.error)}</div>`;
      }
      if (query.result_sample && query.result_sample.length) {
        body += renderTable(query.result_sample);
      } else if (!query.error) {
        body += '<div class="table-empty">No sample rows returned.</div>';
      }

      return `
        <article class="query-card">
          <div class="query-head">
            <div>
              <div class="query-title">${esc(query.check_name || 'Unnamed check')}</div>
              <div class="query-purpose">${esc(query.purpose || 'No purpose recorded.')}</div>
            </div>
            <span class="status-pill status-${statusClass(query.status)}">${esc(statusLabel(query.status))}</span>
          </div>
          ${
            meta.length
              ? `<div class="query-meta">${meta.map((item) => `<span>${esc(item)}</span>`).join('')}</div>`
              : ''
          }
          ${renderCode('Generated query', query.sql || '-- No SQL stored')}
          ${body}
        </article>
      `;
    })
    .join('');

  return renderInfoCard(
    'Executed checks',
    `<div class="query-stack">${cards}</div>`,
    { kicker: 'Evidence pack' }
  );
}

function renderMarkdownDocument(title, markdown, downloadUrl) {
  // The final QA report is rendered inside .doc-card. Its visual boundaries are
  // controlled by .doc-card and .markdown-body in style.css.
  const downloadLink = downloadUrl
    ? `<a class="doc-link" href="${escAttr(downloadUrl)}" target="_blank" rel="noreferrer">Open markdown document</a>`
    : '';

  return `
    <article class="doc-card">
      <div class="doc-head">
        <div>
          <div class="message-kicker">Report document</div>
          <h3 class="message-title">${esc(title)}</h3>
        </div>
        ${downloadLink}
      </div>
      <div class="doc-body markdown-body">${markdownToHtml(markdown)}</div>
    </article>
  `;
}

function copyStoredText(event) {
  // Copy button handler shared by every generated SQL block.
  const button = event.currentTarget;
  const key = button.getAttribute('data-copy-key');
  const text = storedText[key] || '';
  navigator.clipboard.writeText(text).then(() => {
    const original = button.textContent;
    button.textContent = 'Copied';
    window.setTimeout(() => {
      button.textContent = original;
    }, 1200);
  });
}

function hlSQL(sql) {
  // Lightweight client-side SQL highlighting. This is cosmetic only; it never
  // changes the stored SQL copied by renderCode().
  const keywords = [
    'SELECT', 'FROM', 'WHERE', 'GROUP BY', 'ORDER BY', 'PARTITION BY', 'LIMIT',
    'LEFT JOIN', 'INNER JOIN', 'JOIN', 'ON', 'AS', 'AND', 'OR', 'NOT',
    'IN', 'IS', 'NULL', 'COUNT', 'SUM', 'AVG', 'MAX', 'MIN', 'DISTINCT',
    'HAVING', 'WITH', 'DESC', 'ASC', 'BETWEEN', 'LIKE', 'CAST', 'COALESCE',
    'ROUND', 'CASE', 'WHEN', 'THEN', 'ELSE', 'END', 'BY'
  ];

  let highlighted = sql;
  keywords
    .sort((left, right) => right.length - left.length)
    .forEach((keyword) => {
      highlighted = highlighted.replace(
        new RegExp(`\\b(${keyword})\\b`, 'g'),
        '<span class="sql-keyword">$1</span>'
      );
    });

  highlighted = highlighted.replace(/'([^']*)'/g, '<span class="sql-string">\'$1\'</span>');
  highlighted = highlighted.replace(/(--[^\n]*)/g, '<span class="sql-comment">$1</span>');
  highlighted = highlighted.replace(/\b(\d+(?:\.\d+)?)\b/g, '<span class="sql-number">$1</span>');
  return highlighted;
}
