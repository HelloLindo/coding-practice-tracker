// Shared application state, notices, navigation guard and background jobs.

import {$} from './dom.js';
import {api} from './api.js';

export const state = {
  platforms: [],
  byPlatform: {},
  problems: [],          // listing from the server for the current search query
  query: '',
  route: {name: '', params: {}},
};

const listeners = new Set();
export function onProblems(listener) { listeners.add(listener); }

let listingVersion = 0;
export async function refreshProblems() {
  const version = ++listingVersion;
  const data = await api('/api/problems?q=' + encodeURIComponent(state.query));
  if (version !== listingVersion) return state.problems;
  state.problems = data.problems;
  listeners.forEach(listener => listener(state.problems));
  return state.problems;
}

export async function loadPlatforms() {
  const data = await api('/api/platforms');
  state.platforms = data.platforms;
  state.byPlatform = Object.fromEntries(data.platforms.map(p => [p.name, p]));
}

export function platformLabel(name) { return state.byPlatform[name]?.label || name; }

// --- Notices ---------------------------------------------------------------
export function notice(message, type = '') {
  const box = $('notice');
  box.textContent = message || '';
  box.className = 'notice' + (type ? ' ' + type : '');
  box.hidden = !message;
}

// --- Unsaved-changes guard -------------------------------------------------
let guard = null;
export function setGuard(fn) { guard = fn; }
export function hasUnsaved() { return !!(guard && guard()); }
export function confirmLeave() { return !hasUnsaved() || window.confirm('Leave without saving your changes?'); }

// --- Background jobs -------------------------------------------------------
const TERMINAL = new Set(['ready', 'partial', 'failed', 'conflict']);
export function busy(value) { document.body.classList.toggle('busy', value); }

export function followJob(id, {onUpdate, onDone}) {
  let stopped = false;
  const tick = async () => {
    if (stopped) return;
    try {
      const job = await api('/api/job?id=' + encodeURIComponent(id));
      const terminal = TERMINAL.has(job.state);
      notice(job.message, terminal ? (job.state === 'ready' ? 'success' : 'error') : 'progress');
      onUpdate?.(job);
      if (!terminal) { setTimeout(tick, 900); return; }
      busy(false);
      try { sessionStorage.removeItem('practice-job'); } catch (_) { /* ignore */ }
      onDone?.(job);
    } catch (error) {
      if (error.status === 404 || error.status === 403) {
        busy(false);
        try { sessionStorage.removeItem('practice-job'); } catch (_) { /* ignore */ }
        notice(error.message, 'error');
        onDone?.({state: 'failed', message: error.message});
        return;
      }
      notice(error.message + ' Reconnecting shortly…', 'error');
      setTimeout(tick, 2500);
    }
  };
  busy(true);
  try { sessionStorage.setItem('practice-job', id); } catch (_) { /* ignore */ }
  tick();
  return () => { stopped = true; };
}
