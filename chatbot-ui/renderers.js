/* Summary: Rendering helpers for the local phase 1 QA operator console. */

const storedText = {};

function esc(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function escAttr(value) {
  return esc(value).replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function formatDateTime(value) {
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
  if (ms == null) return 'Not timed';
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function statusLabel(status) {
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
  return String(status || 'unknown').replace(/[^a-z0-9_-]/gi, '-').toLowerCase();
}

function inlineFormat(text) {
  let html = esc(text);
  html = html.replace(/`([^`]+)`/g, '<code class="inline">$1</code>');
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');
  return html;
}

function markdownToHtml(markdown) {
  const lines = String(markdown || '').split('\n');
  let html = '';
  let paragraph = [];
  let inList = false;

  function closeParagraph() {
    if (!paragraph.length) return;
    html += `<p>${inlineFormat(paragraph.join(' '))}</p>`;
    paragraph = [];
  }

  function closeList() {
    if (!inList) return;
    html += '</ul>';
    inList = false;
  }

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line) {
      closeParagraph();
      closeList();
      continue;
    }

    const headingMatch = line.match(/^(#{1,3})\s+(.*)$/);
    if (headingMatch) {
      closeParagraph();
      closeList();
      const level = Math.min(4, headingMatch[1].length + 1);
      html += `<h${level}>${inlineFormat(headingMatch[2])}</h${level}>`;
      continue;
    }

    const listMatch = line.match(/^[-*]\s+(.*)$/) || line.match(/^\d+\.\s+(.*)$/);
    if (listMatch) {
      closeParagraph();
      if (!inList) {
        html += '<ul>';
        inList = true;
      }
      html += `<li>${inlineFormat(listMatch[1])}</li>`;
      continue;
    }

    closeList();
    paragraph.push(line);
  }

  closeParagraph();
  closeList();
  return html || '<p>No report content available.</p>';
}

function fmtCell(value) {
  if (value == null) return '<span class="empty-cell">null</span>';
  if (typeof value === 'number') return value.toLocaleString('en-GB');
  if (typeof value === 'object') return esc(JSON.stringify(value));
  return esc(String(value));
}

function renderTable(rows, options = {}) {
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

  return `
    <form class="question-form" data-run-id="${escAttr(runId)}" onsubmit="submitPendingAnswers(event)">
      ${blocks}
      <button class="primary-btn question-submit" type="submit">Resume QA run</button>
    </form>
  `;
}

function renderFindings(findings) {
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
      <div class="doc-body">${markdownToHtml(markdown)}</div>
    </article>
  `;
}

function copyStoredText(event) {
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
