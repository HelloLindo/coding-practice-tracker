// Problem page: identity, statement, every practice, Quick recall and related problems.

import {h, clear, problemHref, splitList, statusPill, difficultyPill, formatDate, copyButton, STATUS_LABELS} from '../dom.js';
import {api, requestId} from '../api.js';
import {codeBlock} from '../highlight.js';
import {renderMarkdown} from '../markdown.js';
import {markdownEditor} from '../editor.js';
import {state, notice, followJob, refreshProblems, setGuard} from '../state.js';
import {knownCompanies, knownTags} from '../sidebar.js';

function panel(step, title, ...children) {
  return h('section', {class: 'panel'},
    h('div', {class: 'panel-heading'}, h('div', {}, h('span', {class: 'step-label', text: step}), h('h2', {text: title}))),
    ...children);
}

export async function problemView(root, params, options = {}) {
  let data = await api('/api/problem?key=' + encodeURIComponent(params.key));
  let initialRecall = {zh: '', en: ''};
  let recallMode = 'edit';
  let selected = data.practices.length - 1;
  let editingStatement = false;
  let editingMeta = false;
  let metaSnapshot = '';
  let busy = false;
  let saving = false;

  // --- Header ------------------------------------------------------------
  const eyebrow = h('div', {class: 'eyebrow'});
  const heading = h('h1');
  const chips = h('div', {class: 'chips'});
  const actions = h('div', {class: 'header-actions'});
  const header = h('header', {class: 'page-header problem-header'}, h('div', {class: 'header-main'}, eyebrow, heading, chips), actions);

  // --- Details editor ----------------------------------------------------
  const metaTitle = h('input', {maxlength: '200', required: true});
  const metaId = h('input', {maxlength: '40'});
  const metaCompanies = h('input', {list: 'meta-companies', autocomplete: 'off'});
  const metaTags = h('input', {list: 'meta-tags', autocomplete: 'off'});
  const relatedList = h('div', {class: 'related-edit'});
  const relatedInput = h('input', {list: 'meta-problems', placeholder: 'Search saved problems…', autocomplete: 'off'});
  let relatedKeys = [];
  const problemsList = h('datalist', {id: 'meta-problems'});
  const metaIdField = h('label', {class: 'field narrow'}, h('span', {class: 'field-label', text: 'Display number'}), metaId);
  const metaForm = h('form', {class: 'panel meta-editor', hidden: true},
    h('div', {class: 'panel-heading'}, h('div', {}, h('span', {class: 'step-label', text: 'DETAILS'}), h('h2', {text: 'Edit problem details'}))),
    h('div', {class: 'field-row'}, h('label', {class: 'field grow'}, h('span', {class: 'field-label', text: 'Title'}), metaTitle), metaIdField),
    h('div', {class: 'field-row'},
      h('label', {class: 'field grow'}, h('span', {class: 'field-label', text: 'Companies'}), metaCompanies, h('span', {class: 'field-help', text: 'Comma-separated.'})),
      h('label', {class: 'field grow'}, h('span', {class: 'field-label', text: 'Tags'}), metaTags, h('span', {class: 'field-help', text: 'Comma-separated algorithm patterns.'}))),
    h('div', {class: 'field'}, h('span', {class: 'field-label', text: 'Related problems'}), relatedList,
      h('div', {class: 'inline-add'}, relatedInput, h('button', {class: 'button secondary', type: 'button', text: 'Add', onclick: addRelated})),
      h('span', {class: 'field-help', text: 'Links are kept on both problems, e.g. Part 1 / Part 2 of one question.'})),
    h('datalist', {id: 'meta-companies'}, knownCompanies().map(c => h('option', {value: c}))),
    h('datalist', {id: 'meta-tags'}, knownTags().map(t => h('option', {value: t}))),
    problemsList,
    h('div', {class: 'form-footer'}, h('p', {text: 'Saved to problem.json and the README title. Practices are unchanged.'}),
      h('div', {class: 'footer-actions'},
        h('button', {class: 'button secondary', type: 'button', text: 'Cancel', onclick: () => toggleMeta(false)}),
        h('button', {class: 'button primary', type: 'submit', text: 'Save details'}))));

  // --- Statement ---------------------------------------------------------
  const statementTabs = h('div', {class: 'segmented small', role: 'group', 'aria-label': 'Statement view'});
  const statementBody = h('div', {class: 'statement-body'});
  const statementEditor = markdownEditor({name: 'statement', rows: 16, label: 'Problem statement',
    placeholder: 'Paste the full statement as Markdown.'});
  const statementEdit = h('div', {class: 'statement-edit', hidden: true}, statementEditor,
    h('div', {class: 'recall-actions'},
      h('button', {class: 'button secondary', type: 'button', text: 'Cancel', onclick: () => toggleStatement(false)}),
      h('button', {class: 'button primary', type: 'button', text: 'Save statement', onclick: saveStatement})));
  const statementButton = h('button', {class: 'text-button', type: 'button', onclick: () => toggleStatement(true)});
  let statementTab = 'full';
  const statementPanel = h('section', {class: 'panel statement-panel'},
    h('div', {class: 'panel-heading'}, h('div', {}, h('span', {class: 'step-label', text: '01 / THE PROBLEM'}), h('h2', {text: 'Problem statement'})),
      h('div', {class: 'heading-tools'}, statementTabs, statementButton)),
    statementBody, statementEdit);

  // --- Practices ---------------------------------------------------------
  const timeline = h('ol', {class: 'timeline'});
  const practiceDetail = h('div', {class: 'practice-detail'});
  const practicePanel = panel('02 / THE PRACTICE', 'Practice history', timeline, practiceDetail);

  // --- Recall ------------------------------------------------------------
  const recallState = h('span', {class: 'pill neutral'});
  const editTab = h('button', {type: 'button', class: 'active', 'aria-pressed': 'true', text: 'Edit', onclick: () => recallView('edit')});
  const previewTab = h('button', {type: 'button', 'aria-pressed': 'false', text: 'Preview', onclick: () => recallView('preview')});
  const generateButton = h('button', {class: 'text-button', type: 'button', text: 'Regenerate', onclick: regenerate});
  const zh = h('textarea', {rows: 7, spellcheck: 'false', placeholder: '用你自己的话记住思路、关键条件和容易遗漏的细节。'});
  const en = h('textarea', {rows: 7, placeholder: 'Capture the approach, invariant, and details worth remembering.'});
  const editors = h('div', {},
    h('label', {class: 'recall-language'}, h('span', {class: 'language-heading'}, h('strong', {text: '中文'}), h('span', {text: 'SIMPLIFIED CHINESE'})), zh),
    h('label', {class: 'recall-language'}, h('span', {class: 'language-heading'}, h('strong', {text: 'English'}), h('span', {text: 'THE SAME IDEAS'})), en));
  const previewZh = h('div');
  const previewEn = h('div');
  const recallPreview = h('div', {class: 'recall-preview', hidden: true}, h('h3', {text: '中文'}), previewZh, h('h3', {text: 'English'}), previewEn);
  const sourceText = h('textarea', {rows: 4, 'aria-label': 'Statement for regeneration', placeholder: 'Optional: paste the statement (Markdown). It is saved to the README before regenerating.'});
  const saveRecallButton = h('button', {class: 'button primary', type: 'button', text: 'Save recall', disabled: true, onclick: saveRecall});
  const reloadButton = h('button', {class: 'button secondary', type: 'button', text: 'Reload saved', onclick: reloadRecall});
  const readmePath = h('p', {class: 'mono muted'});
  const recallPanel = h('section', {class: 'panel recall-panel'},
    h('div', {class: 'panel-heading'}, h('div', {}, h('span', {class: 'step-label', text: '03 / THE INSIGHT'}), h('h2', {text: 'Quick recall'})), recallState),
    h('p', {class: 'panel-description', text: 'A short reminder in Chinese, then English. Edit it until it sounds like you.'}),
    h('div', {class: 'editor-toolbar'}, h('div', {class: 'segmented', role: 'group', 'aria-label': 'Recall view'}, editTab, previewTab), generateButton),
    editors, recallPreview,
    h('details', {class: 'disclosure'}, h('summary', {text: 'Statement for regeneration'}),
      h('p', {class: 'field-help', text: 'If problem facts are pending, paste the statement before regenerating.'}), sourceText),
    h('div', {class: 'recall-footer'}, readmePath,
      h('div', {class: 'recall-actions'}, reloadButton, saveRecallButton),
      h('p', {class: 'save-hint'}, 'Saves only Quick recall to the README. ', h('kbd', {text: '⌘/Ctrl'}), ' ', h('kbd', {text: 'S'}))));
  const relatedPanel = h('section', {class: 'panel related-panel'});

  root.replaceChildren(header, metaForm,
    h('div', {class: 'workspace problem-workspace'},
      h('div', {class: 'column'}, statementPanel, practicePanel),
      h('div', {class: 'column'}, recallPanel, relatedPanel)));

  // --- Rendering ---------------------------------------------------------
  function renderHeader() {
    const parts = [data.platform_label];
    if (data.id) parts.push('#' + data.id);
    if (data.created) parts.push('since ' + formatDate(data.created));
    eyebrow.textContent = parts.join(' · ').toUpperCase();
    heading.textContent = (data.platform === 'leetcode' && data.id ? data.id + '. ' : '') + data.title;
    clear(chips);
    data.companies.forEach(c => chips.append(h('span', {class: 'chip company', text: c})));
    data.tags.forEach(t => chips.append(h('span', {class: 'chip', text: t})));
    clear(actions);
    if (data.source) actions.append(h('a', {class: 'button secondary', href: data.source, target: '_blank', rel: 'noopener noreferrer'}, 'Open original ', h('span', {'aria-hidden': 'true', text: '↗'})));
    actions.append(h('button', {class: 'button secondary', type: 'button', text: 'Edit details', onclick: () => toggleMeta(true)}),
      h('a', {class: 'button primary', href: '#/new/' + data.key.split('/').map(encodeURIComponent).join('/')}, h('span', {'aria-hidden': 'true', text: '＋'}), ' Practice again'));
  }

  function renderStatement() {
    clear(statementTabs);
    const hasFull = !!data.full_statement;
    const hasSummary = !!data.summary && !/^Source summary pending\./.test(data.summary);
    if (!hasFull) statementTab = 'summary';
    if (hasFull && hasSummary) {
      for (const [name, label] of [['full', 'Full'], ['summary', 'Summary']]) {
        statementTabs.append(h('button', {type: 'button', class: statementTab === name ? 'active' : '', 'aria-pressed': String(statementTab === name),
          text: label, onclick: () => { statementTab = name; renderStatement(); }}));
      }
    }
    statementTabs.hidden = !(hasFull && hasSummary);
    statementButton.textContent = hasFull ? 'Edit statement' : 'Add full statement';
    statementButton.hidden = editingStatement;
    statementBody.hidden = editingStatement;
    statementEdit.hidden = !editingStatement;
    const text = statementTab === 'full' && hasFull ? data.full_statement : data.summary;
    renderMarkdown(statementBody, text || '', {emptyText: 'No statement saved yet.'});
    if (statementTab === 'summary' && !hasFull) {
      statementBody.append(h('p', {class: 'field-help', text: data.statement_mode === 'manual'
        ? 'Only a summary is saved. Add the full statement in Markdown so it travels with your repository.'
        : 'This is the saved summary. You can add the full statement in Markdown.'}));
    }
  }

  function renderPractices() {
    clear(timeline);
    [...data.practices].reverse().forEach(practice => {
      const index = data.practices.indexOf(practice);
      const active = index === selected;
      timeline.append(h('li', {}, h('button', {type: 'button', class: 'timeline-item' + (active ? ' active' : ''),
        'aria-pressed': String(active), onclick: () => { selected = index; renderPractices(); }},
      h('span', {class: 'timeline-date', text: formatDate(practice.date)}),
      h('span', {class: 'timeline-meta'}, statusPill(practice.status), difficultyPill(practice.difficulty)),
      h('span', {class: 'mono muted', text: practice.filename}))));
    });
    const practice = data.practices[selected];
    clear(practiceDetail);
    if (!practice) return;
    const notesBox = h('div', {class: 'practice-notes'});
    if (practice.notes) renderMarkdown(notesBox, practice.notes);
    else notesBox.append(h('p', {class: 'muted', text: 'No personal notes recorded.'}));
    practiceDetail.append(
      h('div', {class: 'detail-heading'},
        h('strong', {text: `Practice ${selected + 1} of ${data.practices.length} · ${STATUS_LABELS[practice.status] || practice.status}`}),
        copyButton(() => practice.code, 'Copy code')),
      codeBlock(practice.code, 'python'),
      h('h3', {class: 'subheading', text: 'My notes'}), notesBox);
  }

  function renderRelated() {
    clear(relatedPanel);
    relatedPanel.hidden = !data.related.length;
    if (!data.related.length) return;
    relatedPanel.append(h('div', {class: 'panel-heading'}, h('div', {}, h('span', {class: 'step-label', text: 'CONNECTED'}), h('h2', {text: 'Related problems'}))),
      h('ul', {class: 'related-list'}, data.related.map(r => h('li', {}, h('a', {href: problemHref(r.key)}, h('strong', {text: r.title}), h('small', {text: r.platform_label}))))));
  }

  function renderRelatedEdit() {
    clear(relatedList);
    if (!relatedKeys.length) relatedList.append(h('span', {class: 'muted', text: 'None yet.'}));
    for (const key of relatedKeys) {
      const info = state.problems.find(p => p.key === key);
      relatedList.append(h('span', {class: 'chip removable'}, info ? info.title : key,
        h('button', {type: 'button', 'aria-label': 'Remove ' + (info ? info.title : key), text: '×',
          onclick: () => { relatedKeys = relatedKeys.filter(k => k !== key); renderRelatedEdit(); }})));
    }
    clear(problemsList);
    state.problems.filter(p => p.key !== data.key && !relatedKeys.includes(p.key))
      .forEach(p => problemsList.append(h('option', {value: `${p.title} — ${p.key}`})));
  }

  function addRelated() {
    const value = relatedInput.value.trim();
    if (!value) return;
    const match = state.problems.find(p => value.endsWith('— ' + p.key) || p.key === value || p.title.toLowerCase() === value.toLowerCase());
    if (!match || match.key === data.key) { notice('Choose a saved problem from the list.', 'error'); return; }
    if (!relatedKeys.includes(match.key)) relatedKeys.push(match.key);
    relatedInput.value = '';
    renderRelatedEdit();
  }
  relatedInput.addEventListener('keydown', event => { if (event.key === 'Enter') { event.preventDefault(); addRelated(); } });

  function metaValues() {
    return JSON.stringify([metaTitle.value.trim(), metaId.value.trim(), splitList(metaCompanies.value), splitList(metaTags.value), [...relatedKeys].sort()]);
  }

  function toggleMeta(open) {
    if (!open && editingMeta && metaValues() !== metaSnapshot && !window.confirm('Discard changes to the details?')) return;
    editingMeta = open;
    metaForm.hidden = !open;
    if (open) {
      metaTitle.value = data.title;
      metaId.value = data.id;
      metaIdField.hidden = data.platform === 'leetcode';
      metaCompanies.value = data.companies.join(', ');
      metaTags.value = data.tags.join(', ');
      relatedKeys = data.related.map(r => r.key);
      renderRelatedEdit();
      metaSnapshot = metaValues();
      metaTitle.focus();
    }
  }

  metaForm.addEventListener('submit', async event => {
    event.preventDefault();
    if (!metaForm.reportValidity()) return;
    const payload = {key: data.key, revision: data.meta_revision, title: metaTitle.value.trim(),
      companies: splitList(metaCompanies.value), tags: splitList(metaTags.value), related: relatedKeys};
    if (data.platform !== 'leetcode') payload.id = metaId.value.trim();
    try {
      data = await api('/api/meta', payload);
      editingMeta = false;
      metaForm.hidden = true;
      renderAll();
      await refreshProblems();
      notice('Problem details saved.', 'success');
    } catch (error) { notice(error.message, 'error'); }
  });

  function toggleStatement(open) {
    if (!open && editingStatement && statementEditor.field.value !== data.full_statement && !window.confirm('Discard statement changes?')) return;
    editingStatement = open;
    if (open) { statementEditor.field.value = data.full_statement; statementEditor.mode(false); setTimeout(() => statementEditor.field.focus(), 0); }
    renderStatement();
  }

  async function saveStatement() {
    try {
      data = await api('/api/statement', {key: data.key, revision: data.statement_revision, statement: statementEditor.field.value});
      editingStatement = false;
      statementTab = 'full';
      renderStatement();
      notice('Statement saved to the README.', 'success');
    } catch (error) { notice(error.message, 'error'); }
  }

  // --- Recall behaviour ---------------------------------------------------
  function recallDirty() { return zh.value !== initialRecall.zh || en.value !== initialRecall.en; }

  function autosize() {
    for (const area of [zh, en]) { area.style.height = 'auto'; area.style.height = area.scrollHeight + 2 + 'px'; }
  }

  function recallStatus() {
    if (recallMode === 'edit') requestAnimationFrame(autosize);
    const changed = recallDirty();
    const complete = !!zh.value.trim() && !!en.value.trim();
    saveRecallButton.disabled = saving || busy || !changed || !complete;
    generateButton.disabled = busy || saving;
    reloadButton.disabled = saving;
    recallState.textContent = busy ? 'Generating…' : changed ? 'Unsaved changes' : (complete ? 'Saved' : 'Incomplete');
    recallState.className = 'pill' + (changed ? ' unsaved' : (complete && !busy ? '' : ' neutral'));
    if (recallMode === 'preview') { renderMarkdown(previewZh, zh.value, {emptyText: 'No recall text yet.'}); renderMarkdown(previewEn, en.value, {emptyText: 'No recall text yet.'}); }
  }

  function recallView(mode) {
    recallMode = mode;
    editors.hidden = mode !== 'edit';
    recallPreview.hidden = mode === 'edit';
    editTab.classList.toggle('active', mode === 'edit'); editTab.setAttribute('aria-pressed', String(mode === 'edit'));
    previewTab.classList.toggle('active', mode !== 'edit'); previewTab.setAttribute('aria-pressed', String(mode !== 'edit'));
    recallStatus();
  }

  function loadRecall(recall) {
    initialRecall = {zh: recall.zh, en: recall.en};
    zh.value = recall.zh; en.value = recall.en;
    readmePath.textContent = data.readme_path;
    recallStatus();
  }

  async function saveRecall() {
    if (saveRecallButton.disabled) return;
    saving = true; recallStatus();
    zh.disabled = en.disabled = true;
    try {
      data = await api('/api/recall', {key: data.key, revision: data.recall.revision, zh: zh.value, en: en.value});
      loadRecall(data.recall);
      notice('Quick recall saved to the README. Code and personal notes were kept.', 'success');
    } catch (error) { notice(error.message, 'error'); }
    finally { saving = false; zh.disabled = en.disabled = false; recallStatus(); }
  }

  async function reloadRecall() {
    if (recallDirty() && !window.confirm('Discard your unsaved recall changes?')) return;
    try { data = await api('/api/problem?key=' + encodeURIComponent(data.key)); renderAll(); notice('Saved recall loaded.'); }
    catch (error) { notice(error.message, 'error'); }
  }

  async function regenerate() {
    if (busy) return;
    if (recallDirty() && !window.confirm('Regenerate and discard your unsaved recall changes?')) return;
    busy = true; recallStatus();
    notice('Preparing a new bilingual recall…', 'progress');
    try {
      const job = await api('/api/generate', {key: data.key, statement: sourceText.value, request_id: requestId()});
      follow(job.id);
    } catch (error) { busy = false; recallStatus(); notice(error.message, 'error'); }
  }

  function follow(id) {
    busy = true; recallStatus();
    followJob(id, {onDone: async job => {
      busy = false;
      const unsaved = recallDirty() ? {zh: zh.value, en: en.value} : null;
      try {
        data = await api('/api/problem?key=' + encodeURIComponent(data.key));
        renderAll();
        sourceText.value = '';
        const draft = unsaved || job.draft;
        if (draft) { zh.value = draft.zh; en.value = draft.en; recallStatus(); }
      } catch (error) { notice(error.message, 'error'); }
      recallStatus();
    }});
  }

  zh.addEventListener('input', recallStatus);
  en.addEventListener('input', recallStatus);
  const onKey = event => {
    if (!(event.metaKey || event.ctrlKey) || event.key.toLowerCase() !== 's') return;
    if (!document.body.contains(recallPanel)) { window.removeEventListener('keydown', onKey); return; }
    event.preventDefault();
    if (editingStatement) saveStatement();
    else saveRecall();
  };
  window.addEventListener('keydown', onKey);

  function renderAll() {
    selected = Math.min(selected, data.practices.length - 1);
    renderHeader(); renderStatement(); renderPractices(); renderRelated(); loadRecall(data.recall);
  }

  renderAll();
  recallView('edit');
  if (options.draft) { zh.value = options.draft.zh; en.value = options.draft.en; recallStatus(); }
  setGuard(() => recallDirty() || (editingStatement && statementEditor.field.value !== data.full_statement)
    || (editingMeta && metaValues() !== metaSnapshot));
  return {follow};
}
