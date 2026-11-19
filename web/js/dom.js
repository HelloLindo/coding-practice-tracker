// Small DOM helpers. Text is always inserted as text nodes, never as HTML.

export const $ = id => document.getElementById(id);

export function h(tag, attrs, ...children) {
  const element = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === undefined || value === null || value === false) continue;
    if (key === 'class') element.className = value;
    else if (key === 'dataset') Object.assign(element.dataset, value);
    else if (key.startsWith('on') && typeof value === 'function') element.addEventListener(key.slice(2), value);
    else if (key === 'text') element.textContent = value;
    else if (value === true) element.setAttribute(key, '');
    else element.setAttribute(key, value);
  }
  append(element, children);
  return element;
}

export function append(parent, children) {
  for (const child of children.flat(Infinity)) {
    if (child === undefined || child === null || child === false) continue;
    parent.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return parent;
}

export function clear(element) { element.replaceChildren(); return element; }

export function storage(kind = 'local') {
  try { return kind === 'session' ? window.sessionStorage : window.localStorage; } catch (_) { return null; }
}

export function readStored(key, fallback, kind = 'local') {
  try { const raw = storage(kind)?.getItem(key); return raw ? JSON.parse(raw) : fallback; } catch (_) { return fallback; }
}

export function writeStored(key, value, kind = 'local') {
  try {
    if (value === null || value === undefined) storage(kind)?.removeItem(key);
    else storage(kind)?.setItem(key, JSON.stringify(value));
  } catch (_) { /* storage unavailable */ }
}

export function formatDate(value) {
  if (!value) return '';
  const text = String(value);
  const iso = /^\d{8}$/.test(text) ? `${text.slice(0, 4)}-${text.slice(4, 6)}-${text.slice(6)}` : text;
  const date = new Date(iso + 'T12:00:00');
  if (Number.isNaN(date.getTime())) return text;
  return date.toLocaleDateString('en-US', {month: 'short', day: 'numeric', year: 'numeric'});
}

export const STATUS_LABELS = {independent: 'Independent', improved: 'Improved', learned: 'Learned', unknown: 'Unknown'};
export const DIFFICULTY_LABELS = {1: 'Easy', 2: 'Fairly easy', 3: 'Moderate', 4: 'Hard', 5: 'Very hard'};

export function statusPill(status) {
  return h('span', {class: 'pill status-' + (status || 'unknown'), text: STATUS_LABELS[status] || status});
}

export function difficultyPill(value) {
  return h('span', {class: 'pill neutral', title: value ? DIFFICULTY_LABELS[value] : 'Recorded before ratings existed',
    text: value ? `Difficulty ${value}/5` : 'Unrated'});
}

export function problemHref(key) { return '#/p/' + key.split('/').map(encodeURIComponent).join('/'); }

export function splitList(value) {
  return String(value || '').split(',').map(item => item.trim()).filter(Boolean);
}

export function copyButton(getText, label = 'Copy') {
  const button = h('button', {class: 'text-button', type: 'button', text: label});
  button.addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(getText()); button.textContent = 'Copied'; }
    catch (_) { button.textContent = 'Copy failed'; }
    setTimeout(() => { button.textContent = label; }, 1400);
  });
  return button;
}
