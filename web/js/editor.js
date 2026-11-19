// Code editor: a textarea over a highlighted <pre>, with Python-friendly keys.
// Tab/Shift-Tab indent, Enter keeps indentation (and adds a level after ':'),
// Backspace removes a soft tab, Cmd/Ctrl-/ toggles comments, Esc releases Tab.

import {h} from './dom.js';
import {highlightInto} from './highlight.js';
import {renderMarkdown} from './markdown.js';

const INDENT = '    ';

function insert(field, text) {
  field.focus();
  // execCommand keeps the browser's undo history; fall back where unsupported.
  if (!document.execCommand || !document.execCommand('insertText', false, text)) {
    field.setRangeText(text, field.selectionStart, field.selectionEnd, 'end');
    field.dispatchEvent(new Event('input', {bubbles: true}));
  }
}

function lineBounds(value, start, end) {
  const from = value.lastIndexOf('\n', start - 1) + 1;
  let to = value.indexOf('\n', end > start && value[end - 1] === '\n' ? end - 1 : end);
  if (to === -1) to = value.length;
  return [from, to];
}

function replaceLines(field, transform) {
  const {value, selectionStart, selectionEnd} = field;
  const [from, to] = lineBounds(value, selectionStart, selectionEnd);
  const lines = value.slice(from, to).split('\n');
  const changed = transform(lines);
  field.setSelectionRange(from, to);
  insert(field, changed.join('\n'));
  const length = changed.join('\n').length;
  if (selectionStart === selectionEnd && lines.length === 1) {
    const delta = changed[0].length - lines[0].length;
    const caret = Math.max(from, selectionStart + delta);
    field.setSelectionRange(caret, caret);
  } else field.setSelectionRange(from, from + length);
}

function handleKey(event, field, state) {
  const {value, selectionStart: start, selectionEnd: end} = field;
  if (event.key === 'Escape') { state.released = true; return; }
  if (event.key === 'Tab') {
    if (state.released) { state.released = false; return; }
    event.preventDefault();
    const multiline = value.slice(start, end).includes('\n');
    if (event.shiftKey) replaceLines(field, lines => lines.map(line => line.replace(/^( {1,4}|\t)/, '')));
    else if (multiline) replaceLines(field, lines => lines.map(line => line.trim() ? INDENT + line : line));
    else {
      const column = start - (value.lastIndexOf('\n', start - 1) + 1);
      insert(field, ' '.repeat(4 - (column % 4)));
    }
    return;
  }
  state.released = false;
  if (event.key === 'Enter' && !event.metaKey && !event.ctrlKey && !event.altKey && !event.isComposing) {
    event.preventDefault();
    const lineStart = value.lastIndexOf('\n', start - 1) + 1;
    const before = value.slice(lineStart, start);
    let indent = /^[ \t]*/.exec(before)[0];
    if (/:\s*(#.*)?$/.test(before)) indent += INDENT;
    else if (/^\s*(return|pass|break|continue|raise)\b/.test(before) && indent.length >= 4) indent = indent.slice(4);
    insert(field, '\n' + indent);
    return;
  }
  if (event.key === 'Backspace' && start === end && start > 0) {
    const lineStart = value.lastIndexOf('\n', start - 1) + 1;
    const before = value.slice(lineStart, start);
    if (before.length && /^ +$/.test(before)) {
      event.preventDefault();
      const remove = before.length % 4 || 4;
      field.setSelectionRange(start - remove, start);
      insert(field, '');
    }
    return;
  }
  if (event.key === '/' && (event.metaKey || event.ctrlKey)) {
    event.preventDefault();
    replaceLines(field, lines => {
      const active = lines.filter(line => line.trim());
      const commented = active.length && active.every(line => /^\s*#/.test(line));
      const indent = Math.min(...active.map(line => /^\s*/.exec(line)[0].length));
      return lines.map(line => {
        if (!line.trim()) return line;
        return commented ? line.replace(/^(\s*)# ?/, '$1') : line.slice(0, indent) + '# ' + line.slice(indent);
      });
    });
  }
}

export function codeEditor({name = 'code', value = '', placeholder = '', required = false, label = 'Code', minRows = 14} = {}) {
  const code = h('code');
  const pre = h('pre', {class: 'code-highlight', 'aria-hidden': 'true'}, code);
  const field = h('textarea', {class: 'code-input', name, placeholder, spellcheck: 'false', autocapitalize: 'off',
    autocomplete: 'off', autocorrect: 'off', wrap: 'off', required, 'aria-label': label, rows: minRows});
  field.value = value;
  const wrapper = h('div', {class: 'code-editor'}, pre, field);
  const state = {released: false, frame: 0};
  const render = () => {
    state.frame = 0;
    highlightInto(code, field.value + (field.value.endsWith('\n') || !field.value ? ' ' : ''));
    field.style.height = 'auto';
    field.style.height = Math.max(field.scrollHeight, minRows * 22) + 'px';
    pre.scrollLeft = field.scrollLeft;
  };
  const schedule = () => { if (!state.frame) state.frame = requestAnimationFrame(render); };
  field.addEventListener('input', schedule);
  field.addEventListener('scroll', () => { pre.scrollLeft = field.scrollLeft; pre.scrollTop = field.scrollTop; });
  field.addEventListener('keydown', event => handleKey(event, field, state));
  wrapper.refresh = render;
  wrapper.field = field;
  requestAnimationFrame(render);
  return wrapper;
}

// Markdown text area with Write / Preview tabs.
export function markdownEditor({name, value = '', placeholder = '', rows = 10, label = 'Markdown', required = false} = {}) {
  const field = h('textarea', {name, placeholder, rows, class: 'markdown-input', spellcheck: 'true', required, 'aria-label': label});
  field.value = value;
  const preview = h('div', {class: 'markdown-preview', hidden: true});
  const write = h('button', {type: 'button', class: 'active', 'aria-pressed': 'true', text: 'Write'});
  const show = h('button', {type: 'button', 'aria-pressed': 'false', text: 'Preview'});
  const mode = preview_ => {
    field.hidden = preview_;
    preview.hidden = !preview_;
    write.classList.toggle('active', !preview_); show.classList.toggle('active', preview_);
    write.setAttribute('aria-pressed', String(!preview_)); show.setAttribute('aria-pressed', String(preview_));
    if (preview_) renderMarkdown(preview, field.value, {emptyText: 'Nothing to preview yet.'});
  };
  write.addEventListener('click', () => mode(false));
  show.addEventListener('click', () => mode(true));
  field.addEventListener('keydown', event => {
    if (event.key === 'Tab' && !event.shiftKey && field.value.slice(0, field.selectionStart).split('\n').pop().startsWith('    ')) {
      event.preventDefault(); insert(field, '    ');
    }
  });
  const element = h('div', {class: 'markdown-editor'},
    h('div', {class: 'segmented small', role: 'group', 'aria-label': label + ' view'}, write, show), field, preview);
  element.field = field;
  element.mode = mode;
  return element;
}
