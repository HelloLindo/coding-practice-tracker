// New practice: identify the problem (any platform), then archive the solution.

import {h, readStored, writeStored, problemHref, splitList, DIFFICULTY_LABELS} from '../dom.js';
import {api, requestId} from '../api.js';
import {codeEditor, markdownEditor} from '../editor.js';
import {state, notice, followJob, refreshProblems, setGuard} from '../state.js';
import {knownCompanies} from '../sidebar.js';
import {navigate, flash} from '../router.js';

const STATUS_CHOICES = [
  ['independent', 'Independent', 'Reached the target approach on my own.'],
  ['improved', 'Improved', 'Solved it, then learned an optimization and rewrote it.'],
  ['learned', 'Learned', 'Understood a reference, closed it, then rewrote it.'],
];

function detect(value) {
  value = (value || '').trim();
  let host = '';
  try { if (/^https?:\/\//i.test(value)) host = new URL(value).hostname.toLowerCase(); } catch (_) { host = ''; }
  if (host) {
    for (const provider of state.platforms) {
      if (provider.hosts.some(item => host === item || host.endsWith('.' + item))) return provider;
    }
    return state.byPlatform.other;
  }
  if (/^\d+$/.test(value) || /^[a-z0-9]+(?:-[a-z0-9]+)+$/.test(value)) return state.byPlatform.leetcode;
  return null;
}

function field(label, control, {hint, optional, cls} = {}) {
  return h('label', {class: 'field' + (cls ? ' ' + cls : '')},
    h('span', {class: 'field-label'}, label, optional ? h('span', {class: 'optional-label', text: 'Optional'}) : null),
    control, hint ? h('span', {class: 'field-help', text: hint}) : null);
}

export function newView(root, params) {
  const practiceKey = params.key || '';
  const draftKey = 'practice-form-draft' + (practiceKey ? ':' + practiceKey : '');
  const draft = readStored(draftKey, {}, 'session');
  let request = null;
  let resolved = null;
  let needsIdentity = false;
  let resolveTimer = 0;
  let resolveVersion = 0;
  let submitting = false;
  let existing = null;

  // --- Problem identity --------------------------------------------------
  const platform = h('select', {name: 'platform', 'aria-label': 'Platform'},
    h('option', {value: 'auto', text: 'Detect from link'}),
    state.platforms.map(p => h('option', {value: p.name, text: p.label})));
  const problem = h('input', {name: 'problem', autocomplete: 'off', spellcheck: 'false'});
  const title = h('input', {name: 'title', autocomplete: 'off', maxlength: '200'});
  const displayId = h('input', {name: 'display_id', autocomplete: 'off', maxlength: '40', inputmode: 'text'});
  const companyList = h('datalist', {id: 'company-options'}, knownCompanies().map(c => h('option', {value: c})));
  const companies = h('input', {name: 'companies', autocomplete: 'off', list: 'company-options', placeholder: 'e.g. DoorDash, Databricks'});
  const preview = h('div', {class: 'resolve-preview', role: 'status', 'aria-live': 'polite', hidden: true});
  const help = h('p', {class: 'field-help platform-help'});
  const statement = markdownEditor({name: 'statement', rows: 12, label: 'Problem statement',
    placeholder: '# Problem title\n\nPaste the statement here as Markdown: description, constraints, examples.\nCode fences, tables and $math$ are supported.'});
  const statementHint = h('p', {class: 'field-help'});
  const statementBlock = h('section', {class: 'statement-block'},
    h('div', {class: 'field-label'}, 'Problem statement', h('span', {class: 'optional-label', text: 'Markdown'})),
    statementHint, statement);
  const statementDetails = h('details', {class: 'disclosure'}, h('summary', {text: 'Statement, if the page cannot be read'}));

  const problemField = field('Problem link or LeetCode number', problem);
  const titleField = field('Problem title', title);
  const idField = field('Display number', displayId, {optional: true, cls: 'narrow'});
  const companyField = field('Companies', companies, {optional: true, hint: 'Comma-separated. Used for filtering and review.'});

  // --- The practice ------------------------------------------------------
  const editor = codeEditor({name: 'code', required: true, label: 'Final accepted Python code',
    placeholder: 'Paste the solution you understand and submitted.', minRows: 14});
  const statusCards = h('fieldset', {class: 'status-options'}, h('legend', {text: 'How did you complete it?'}),
    STATUS_CHOICES.map(([value, label, help], i) => h('label', {class: 'choice-card'},
      h('input', {type: 'radio', name: 'status', value, required: i === 0}),
      h('span', {}, h('strong', {text: label}), h('small', {text: help})))));
  const ratings = h('fieldset', {class: 'difficulty-options'},
    h('legend', {}, 'Personal difficulty', h('span', {class: 'required-label', text: 'Required'})),
    h('p', {class: 'field-help', text: 'How hard was this solution to understand and implement?'}),
    h('div', {class: 'rating-row'}, [1, 2, 3, 4, 5].map(n => h('label', {},
      h('input', {type: 'radio', name: 'difficulty', value: String(n), required: n === 1}),
      h('span', {}, h('b', {text: String(n)}), h('small', {text: DIFFICULTY_LABELS[n]}))))));
  const notes = h('textarea', {name: 'notes', rows: 4, placeholder: 'A useful reminder, a tricky detail, or what finally clicked.'});
  const submit = h('button', {class: 'button primary', type: 'submit'}, 'Archive practice ', h('span', {'aria-hidden': 'true', text: '↗'}));
  const clearButton = h('button', {class: 'button secondary', type: 'button', text: 'Clear form'});

  const problemPanel = h('section', {class: 'panel'},
    h('div', {class: 'panel-heading'}, h('div', {}, h('span', {class: 'step-label', text: '01 / THE PROBLEM'}),
      h('h2', {text: practiceKey ? 'Practicing again' : 'Which problem?'}))));
  const practicePanel = h('section', {class: 'panel'},
    h('div', {class: 'panel-heading'}, h('div', {}, h('span', {class: 'step-label', text: '02 / THE PRACTICE'}),
      h('h2', {text: 'Final solution'})), h('span', {class: 'language-chip', text: 'Python 3'})),
    h('div', {class: 'field'}, h('span', {class: 'field-label', text: 'Your final AC code'}), editor),
    statusCards, ratings,
    field('Personal notes', notes, {optional: true}),
    h('div', {class: 'form-footer'}, h('p', {text: 'Code and notes are saved before Quick recall is generated.'}),
      h('div', {class: 'footer-actions'}, clearButton, submit)));

  const form = h('form', {class: 'workspace new-practice', novalidate: true}, problemPanel, practicePanel);

  if (practiceKey) {
    existing = state.problems.find(p => p.key === practiceKey);
    const summary = h('div', {class: 'existing-problem'},
      h('strong', {text: existing ? existing.title : practiceKey}),
      h('small', {text: existing ? `${existing.platform_label} · ${existing.count} practice${existing.count === 1 ? '' : 's'} so far · this adds practice #${existing.count + 1}` : 'Loading…'}),
      h('div', {class: 'inline-links'}, h('a', {href: problemHref(practiceKey), text: 'Open problem'}), h('a', {href: '#/new', text: 'Choose a different problem'})));
    problemPanel.append(summary, h('p', {class: 'field-help', text: 'The statement, title and recall stay as they are; edit them from the problem page.'}));
  } else {
    problemPanel.append(
      h('div', {class: 'field-row'}, field('Platform', platform, {cls: 'platform-field'}), problemField),
      help, preview,
      h('div', {class: 'field-row'}, titleField, idField),
      companyField, companyList, statementBlock, statementDetails);
  }

  root.replaceChildren(
    h('header', {class: 'page-header'}, h('div', {},
      h('div', {class: 'eyebrow', text: 'A LITTLE PRACTICE, KEPT.'}),
      h('h1', {text: practiceKey ? 'Practice again.' : 'Capture your next solution.'}),
      h('p', {text: 'Keep the code. Make the insight your own.'}))),
    form);

  // --- Behaviour ---------------------------------------------------------
  function provider() {
    if (practiceKey) return null;
    if (platform.value !== 'auto') return state.byPlatform[platform.value];
    return detect(problem.value) || null;
  }

  function layout() {
    if (practiceKey) return;
    const current = provider();
    const leet = current?.name === 'leetcode';
    const manualUrl = current?.url === 'none';
    problemField.hidden = manualUrl;
    problem.required = !manualUrl;
    problem.placeholder = current?.placeholder || 'https://… or a LeetCode number such as 0001';
    problemField.querySelector('.field-label').firstChild.textContent =
      platform.value === 'auto' ? 'Problem link or LeetCode number' : (leet ? 'Number, slug or URL' : 'Problem URL');
    const wantsTitle = current && (current.title === 'required' || (leet && needsIdentity));
    titleField.hidden = !wantsTitle;
    title.required = !!wantsTitle && !(resolved?.exists) && (!leet || needsIdentity);
    title.placeholder = resolved?.exists ? resolved.title + ' (leave empty to keep)' : 'Title as shown on the page';
    titleField.querySelector('.field-label').firstChild.textContent = manualUrl ? 'Problem title' : 'Problem title';
    const wantsId = current && (current.display_id === 'optional' || (leet && needsIdentity));
    idField.hidden = !wantsId;
    displayId.required = leet && needsIdentity;
    idField.querySelector('.optional-label').hidden = leet && needsIdentity;
    const manualStatement = !current || current.statement === 'manual';
    if (manualStatement && statement.parentElement !== statementBlock) statementBlock.append(statement);
    if (!manualStatement && statement.parentElement !== statementDetails) statementDetails.append(statement);
    statementBlock.hidden = !manualStatement;
    statementDetails.hidden = manualStatement;
    statementHint.textContent = resolved?.exists && resolved.has_statement
      ? 'A statement is already saved for this problem. Leave this empty to keep it, or paste a replacement.'
      : (current && current.name !== 'leetcode' ? 'Convert the page to Markdown and paste it here. It is saved in the problem README.' : 'Paste the statement as Markdown.');
    companyField.hidden = !current;
    help.textContent = current?.help || 'Paste a problem link, or choose a platform. Use “No link” for questions without a page.';
  }

  function showPreview(content, type = '') {
    preview.hidden = !content;
    preview.className = 'resolve-preview' + (type ? ' ' + type : '');
    if (content) preview.replaceChildren(...[content].flat());
  }

  async function runResolve() {
    clearTimeout(resolveTimer);
    if (practiceKey) return;
    const version = ++resolveVersion;
    const current = provider();
    if (!current || (current.url !== 'none' && !problem.value.trim()) || (current.url === 'none' && !title.value.trim())) {
      resolved = null; showPreview(null); layout(); return;
    }
    showPreview('Checking…', 'progress');
    try {
      const result = await api('/api/resolve', {platform: platform.value, problem: problem.value,
        title: current.name === 'leetcode' && !needsIdentity ? '' : title.value,
        display_id: current.name === 'leetcode' && !needsIdentity ? '' : displayId.value});
      if (version !== resolveVersion) return;
      resolved = result;
      const parts = [h('span', {class: 'pill neutral', text: result.platform_label})];
      if (result.exists) {
        parts.push(h('strong', {text: result.title}),
          h('span', {text: ` · already archived with ${result.count} practice${result.count === 1 ? '' : 's'} — this adds practice #${result.count + 1}.`}),
          ' ', h('a', {href: problemHref(result.key), text: 'Open'}));
      } else if (result.needs_title) {
        parts.push(h('span', {text: 'New problem. Add the title shown on the page.'}));
      } else {
        parts.push(h('strong', {text: (result.id && result.platform === 'leetcode' ? result.id + '. ' : '') + result.title}),
          h('span', {text: ' · new problem'}));
      }
      if (result.companies.length && !companies.value.trim() && !result.exists) companies.placeholder = result.companies.join(', ') + ' (from the link)';
      showPreview(parts, result.exists ? 'exists' : '');
    } catch (error) {
      if (version !== resolveVersion) return;
      resolved = null;
      if (error.details?.needs_identity) {
        needsIdentity = true;
        showPreview('The LeetCode lookup is unavailable. Enter the display number and title from the page.', 'error');
      } else showPreview(error.message, 'error');
    }
    layout();
  }

  function scheduleResolve(delay = 650) {
    clearTimeout(resolveTimer);
    resolveTimer = setTimeout(runResolve, delay);
  }

  function values() {
    const data = Object.fromEntries(new FormData(form));
    data.code = editor.field.value;
    data.statement = statement.field.value;
    return data;
  }

  function saveDraft() {
    writeStored(draftKey, values(), 'session');
    request = null;
  }

  function restore() {
    for (const [name, value] of Object.entries(draft)) {
      if (name === 'code') { editor.field.value = value; editor.refresh(); continue; }
      if (name === 'statement') { statement.field.value = value; continue; }
      const control = form.elements.namedItem(name);
      if (!control) continue;
      if (control instanceof RadioNodeList || control.type === 'radio') {
        for (const radio of form.querySelectorAll(`input[name="${name}"]`)) radio.checked = radio.value === value;
      } else control.value = value;
    }
  }

  clearButton.addEventListener('click', () => {
    if (!window.confirm('Clear this form? Unarchived code and notes will be discarded.')) return;
    writeStored(draftKey, null, 'session');
    form.reset(); editor.field.value = ''; editor.refresh(); statement.field.value = ''; statement.mode(false);
    resolved = null; needsIdentity = false; request = null; showPreview(null); layout();
  });

  platform.addEventListener('change', () => { needsIdentity = false; layout(); runResolve(); });
  problem.addEventListener('input', () => { needsIdentity = false; layout(); scheduleResolve(); });
  problem.addEventListener('change', () => runResolve());
  title.addEventListener('input', () => { if (provider()?.url === 'none' || needsIdentity) scheduleResolve(); });
  displayId.addEventListener('change', () => { if (needsIdentity) runResolve(); });
  form.addEventListener('input', saveDraft);
  form.addEventListener('change', saveDraft);

  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (submitting) return;
    if (!form.reportValidity()) return;
    const data = values();
    if (!data.code.trim()) { notice('Paste your final accepted code.', 'error'); editor.field.focus(); return; }
    const payload = {notes: data.notes || '', code: data.code, status: data.status, difficulty: Number(data.difficulty)};
    if (practiceKey) payload.key = practiceKey;
    else {
      const current = provider();
      const leet = current?.name === 'leetcode';
      Object.assign(payload, {platform: platform.value, problem: data.problem || '', statement: data.statement || '',
        title: !leet || needsIdentity ? (data.title || '') : '', display_id: !leet || needsIdentity ? (data.display_id || '') : '',
        companies: splitList(data.companies)});
    }
    if (!request) request = {...payload, request_id: requestId()};
    submitting = true;
    submit.disabled = true;
    notice('Preparing your practice…', 'progress');
    try {
      const job = await api('/api/archive', request);
      followJob(job.id, {onDone: async finished => {
        submitting = false;
        submit.disabled = false;
        if (finished.state === 'failed' || !finished.key) { request = null; return; }
        writeStored(draftKey, null, 'session');
        await refreshProblems().catch(() => {});
        flash(finished.message, finished.state === 'ready' ? 'success' : 'error');
        navigate(problemHref(finished.key), {force: true, draft: finished.draft});
      }});
    } catch (error) {
      submitting = false;
      submit.disabled = false;
      notice(error.message, 'error');
    }
  });

  restore();
  layout();
  if (!practiceKey && (problem.value || title.value)) runResolve();
  setGuard(null);  // The form is kept as a draft in this tab, so leaving loses nothing.
  if (!practiceKey) setTimeout(() => problem.focus(), 0);
  else setTimeout(() => editor.field.focus(), 0);
  return {
    resume(jobId) {
      submitting = true;
      submit.disabled = true;
      followJob(jobId, {onDone: async finished => {
        submitting = false; submit.disabled = false;
        if (!finished.key) return;
        writeStored(draftKey, null, 'session');
        await refreshProblems().catch(() => {});
        flash(finished.message, finished.state === 'ready' ? 'success' : 'error');
        navigate(problemHref(finished.key), {force: true, draft: finished.draft});
      }});
    },
  };
}
