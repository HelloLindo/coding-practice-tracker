'use strict';
const $ = id => document.getElementById(id);
const token = document.querySelector('meta[name="practice-token"]').content;
const form = $('archive-form');
const terminalStates = new Set(['ready', 'partial', 'failed', 'conflict']);
let current = null;
let busy = false;
let saving = false;
let editing = false;
let initialRecall = {zh: '', en: ''};
let request = null;
let pollTimer = null;

async function api(path, data) {
  const response = await fetch(path, {method: data ? 'POST' : 'GET', headers: {
    'X-Practice-Token': token, ...(data ? {'Content-Type': 'application/json'} : {})
  }, ...(data ? {body: JSON.stringify(data)} : {})});
  const result = await response.json();
  if (!response.ok) { const error = new Error(result.error || 'The request could not be completed.'); error.status = response.status; throw error; }
  return result;
}
function notice(message, type = '') {
  $('notice').textContent = message;
  $('notice').className = 'notice' + (type ? ' ' + type : '');
  $('notice').hidden = !message;
}
function dirty() { return current && ($('recall-zh').value !== initialRecall.zh || $('recall-en').value !== initialRecall.en); }
function allowNavigation() { return !dirty() || window.confirm('Leave without saving your recall changes?'); }
function setBusy(value) {
  busy = value;
  document.body.classList.toggle('busy', value);
  $('archive-button').disabled = value || saving;
  $('new-practice').disabled = value || saving;
  $('generate-button').disabled = value || saving;
  $('reload-recall').disabled = saving;
  form.querySelectorAll('input, select, textarea').forEach(field => { field.disabled = value; });
  document.querySelectorAll('.recent-item').forEach(button => { button.disabled = value || saving; });
}
function editState() {
  const changed = dirty();
  const complete = !!$('recall-zh').value.trim() && !!$('recall-en').value.trim();
  $('save-recall').disabled = saving || !current || !changed || !complete;
  $('recall-state').textContent = changed ? 'Unsaved changes' : (complete ? 'Saved' : 'Incomplete');
  $('recall-state').className = 'pill' + (changed ? ' unsaved' : (complete ? '' : ' neutral'));
  preview();
}
function inline(parent, text) {
  const pieces = text.split(/(`[^`]+`)/g);
  for (const piece of pieces) {
    if (piece.startsWith('`') && piece.endsWith('`')) { const code = document.createElement('code'); code.textContent = piece.slice(1, -1); parent.append(code); }
    else parent.append(document.createTextNode(piece));
  }
}
function markdown(target, text) {
  target.replaceChildren();
  let list = null;
  for (const line of text.split('\n')) {
    if (!line.trim()) { list = null; continue; }
    if (/^\s*[-*] /.test(line)) {
      if (!list) { list = document.createElement('ul'); target.append(list); }
      const li = document.createElement('li'); inline(li, line.replace(/^\s*[-*] /, '')); list.append(li);
    } else {
      list = null;
      const heading = /^#{1,6} /.test(line);
      const element = document.createElement(heading ? 'h4' : 'p');
      inline(element, heading ? line.replace(/^#{1,6} /, '') : line); target.append(element);
    }
  }
  if (!text.trim()) { const p = document.createElement('p'); p.className = 'muted'; p.textContent = 'No recall text yet.'; target.append(p); }
}
function preview() { markdown($('preview-zh'), $('recall-zh').value); markdown($('preview-en'), $('recall-en').value); }
function view(mode) {
  editing = mode === 'edit';
  $('recall-editors').hidden = !editing;
  $('recall-preview').hidden = editing;
  for (const name of ['edit', 'preview']) { $(name + '-tab').classList.toggle('active', mode === name); $(name + '-tab').setAttribute('aria-pressed', String(mode === name)); }
  preview();
}
async function listing() {
  const data = await api('/api/problems');
  $('problem-count').textContent = data.problems.length;
  const nav = $('recent-problems'); nav.replaceChildren();
  for (const problem of data.problems) {
    const button = document.createElement('button'); button.className = 'recent-item'; button.type = 'button'; button.dataset.key = problem.key;
    button.classList.toggle('selected', current?.key === problem.key); button.disabled = busy || saving;
    const title = document.createElement('strong'); title.textContent = problem.title;
    const meta = document.createElement('small'); meta.textContent = `${problem.platform === 'leetcode' ? 'LeetCode' : 'Hack2Hire'} · ${problem.status} · ${problem.difficulty ? problem.difficulty + '/5' : 'Unrated'}`;
    button.append(title, meta); button.addEventListener('click', async () => { if (allowNavigation()) { try { await load(problem.key); notice(''); } catch (error) { notice(error.message, 'error'); } } }); nav.append(button);
  }
  if (!data.problems.length) { const p = document.createElement('p'); p.className = 'muted sidebar-empty'; p.textContent = 'Your saved problems will appear here.'; nav.append(p); }
}
function display(data) {
  current = data;
  initialRecall = {zh: data.recall.zh, en: data.recall.en};
  $('recall-zh').value = data.recall.zh; $('recall-en').value = data.recall.en;
  $('recall-source').value = '';
  $('recall-empty').hidden = true; $('recall-content').hidden = false;
  $('page-title').textContent = data.title;
  $('page-subtitle').textContent = 'Practice saved. Keep your recall clear and personal.';
  $('solution-title').textContent = 'Archived solution';
  form.hidden = true; $('saved-practice').hidden = false;
  $('saved-status').textContent = data.status;
  $('saved-difficulty').textContent = data.difficulty ? `Difficulty ${data.difficulty}/5` : 'Difficulty unrated';
  $('saved-filename').textContent = data.filename;
  $('saved-code').textContent = data.code; $('saved-notes').textContent = data.notes;
  $('source-link').href = data.source;
  $('readme-location').textContent = data.readme_path;
  document.querySelectorAll('.recent-item').forEach(button => button.classList.toggle('selected', button.dataset.key === data.key));
  sessionStorage.setItem('practice-selected', data.key);
  view('edit'); editState();
}
async function load(key) { display(await api('/api/problem?key=' + encodeURIComponent(key))); }
function saveFormDraft() {
  const values = Object.fromEntries(new FormData(form));
  sessionStorage.setItem('practice-form-draft', JSON.stringify(values)); request = null;
}
function restoreDraft() {
  try {
    const draft = JSON.parse(sessionStorage.getItem('practice-form-draft') || '{}');
    for (const [key, value] of Object.entries(draft)) { const field = form.elements.namedItem(key); if (field) field.value = value; }
  } catch (_) { sessionStorage.removeItem('practice-form-draft'); }
}
function newPractice() {
  if (!allowNavigation()) return;
  current = null; request = null; form.reset();
  sessionStorage.removeItem('practice-selected'); sessionStorage.removeItem('practice-form-draft');
  form.hidden = false; $('saved-practice').hidden = true;
  $('solution-title').textContent = 'Final solution';
  $('page-title').textContent = 'Capture your next solution.'; $('page-subtitle').textContent = 'Keep the code. Make the insight your own.';
  $('recall-content').hidden = true; $('recall-empty').hidden = false;
  $('recall-state').textContent = 'Awaiting a practice'; $('recall-state').className = 'pill neutral';
  document.querySelectorAll('.recent-item').forEach(button => button.classList.remove('selected'));
  notice(''); $('problem').focus();
}
async function poll(id) {
  clearTimeout(pollTimer);
  try {
    const job = await api('/api/job?id=' + encodeURIComponent(id));
    notice(job.message, terminalStates.has(job.state) ? (job.state === 'ready' ? '' : 'error') : 'progress');
    if (!terminalStates.has(job.state)) { pollTimer = setTimeout(() => poll(id), 900); return; }
    setBusy(false); sessionStorage.removeItem('practice-job');
    if (job.state === 'failed') request = null;
    if (job.key) {
      const unsaved = current?.key === job.key && dirty() ? {zh: $('recall-zh').value, en: $('recall-en').value} : null;
      await load(job.key); sessionStorage.removeItem('practice-form-draft');
      if (unsaved || job.draft) {
        const draft = unsaved || job.draft;
        $('recall-zh').value = draft.zh; $('recall-en').value = draft.en; editState();
        if (unsaved) notice(job.message + ' Your unsaved editor changes were kept.');
      }
      await listing();
    }
  } catch (error) {
    setBusy(false);
    notice(error.message + (error.status === 404 ? '' : ' Reconnecting shortly…'), 'error');
    if (error.status !== 404 && error.status !== 403) { setBusy(true); pollTimer = setTimeout(() => poll(id), 2500); }
    else sessionStorage.removeItem('practice-job');
  }
}
form.addEventListener('input', saveFormDraft);
form.addEventListener('submit', async event => {
  event.preventDefault(); if (busy || !form.reportValidity()) return;
  const data = Object.fromEntries(new FormData(form)); data.difficulty = Number(data.difficulty);
  if (!request) request = {...data, request_id: crypto.randomUUID()};
  setBusy(true); notice('Preparing your practice…', 'progress');
  try {
    const job = await api('/api/archive', request);
    sessionStorage.setItem('practice-job', job.id); poll(job.id);
  } catch (error) { setBusy(false); notice(error.message, 'error'); }
});
for (const id of ['recall-zh', 'recall-en']) $(id).addEventListener('input', editState);
$('edit-tab').addEventListener('click', () => view('edit'));
$('preview-tab').addEventListener('click', () => view('preview'));
$('new-practice').addEventListener('click', newPractice);
$('save-recall').addEventListener('click', async () => {
  if (!current || $('save-recall').disabled) return;
  saving = true; setBusy(busy);
  $('recall-zh').disabled = true; $('recall-en').disabled = true;
  $('save-recall').disabled = true;
  const mode = editing ? 'edit' : 'preview';
  try {
    const result = await api('/api/recall', {key: current.key, revision: current.recall.revision, zh: $('recall-zh').value, en: $('recall-en').value});
    display(result); view(mode); notice('Quick recall saved to the local README. Code and personal notes were kept.');
  } catch (error) { notice(error.message, 'error'); }
  finally {
    saving = false; setBusy(busy);
    $('recall-zh').disabled = false; $('recall-en').disabled = false; editState();
  }
});
$('reload-recall').addEventListener('click', async () => {
  if (current && allowNavigation()) { try { await load(current.key); notice('Saved recall loaded.'); } catch (error) { notice(error.message, 'error'); } }
});
$('generate-button').addEventListener('click', async () => {
  if (!current || busy || !allowNavigation()) return;
  const key = current.key;
  const statement = $('recall-source').value;
  if (dirty()) { try { await load(key); } catch (error) { notice(error.message, 'error'); return; } }
  setBusy(true); notice('Preparing a new bilingual recall…', 'progress');
  try {
    const job = await api('/api/generate', {key, statement, request_id: crypto.randomUUID()});
    sessionStorage.setItem('practice-job', job.id); poll(job.id);
  } catch (error) { setBusy(false); notice(error.message, 'error'); }
});
$('code').addEventListener('keydown', event => {
  if (event.key === 'Tab') { event.preventDefault(); const field = event.target; field.setRangeText('    ', field.selectionStart, field.selectionEnd, 'end'); saveFormDraft(); }
});
window.addEventListener('keydown', event => {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 's' && current) { event.preventDefault(); $('save-recall').click(); }
});
window.addEventListener('beforeunload', event => { if (dirty()) { event.preventDefault(); event.returnValue = ''; } });
(async () => {
  restoreDraft();
  try {
    await listing();
    const job = sessionStorage.getItem('practice-job');
    if (job) { setBusy(true); poll(job); }
    else { const selected = sessionStorage.getItem('practice-selected'); if (selected) await load(selected); }
  } catch (error) { notice(error.message, 'error'); }
})();
