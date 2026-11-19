// Tool updates and record upgrades. Nothing is installed or changed without a click.

import {$, h, clear, readStored, writeStored} from './dom.js';
import {api} from './api.js';
import {refreshProblems, hasUnsaved} from './state.js';

let info = null;
let retried = false;

function banner() { return $('update-banner'); }

function show(...children) {
  const box = clear(banner());
  box.append(...children.filter(Boolean));
  box.hidden = children.length === 0;
}

function hide() { show(); }

function button(text, onclick, kind = 'secondary') {
  return h('button', {class: 'button ' + kind, type: 'button', text, onclick});
}

function message(text, type = '') {
  show(h('p', {class: 'update-text' + (type ? ' ' + type : ''), text}), button('Close', hide, 'text-button'));
}

function versionLabel(version) { return version ? 'v' + version : 'an earlier version'; }

function renderFooter() {
  const footer = $('tool-version');
  if (!footer || !info) return;
  clear(footer);
  footer.append(h('span', {text: info.current ? 'Tracker v' + info.current : 'Tracker version unknown'}), ' · ',
    h('button', {class: 'link-button', type: 'button', text: 'Check for updates', onclick: () => check(true)}));
}

function renderAvailable() {
  const latest = info.latest;
  const parts = [
    h('p', {class: 'update-text'},
      h('strong', {text: `Coding Practice Tracker ${versionLabel(latest.version)} is available`}),
      ` (you have ${versionLabel(info.current)}). Your problems, plans and style notes are never changed; tool files you edited are kept.`),
    h('div', {class: 'update-actions'},
      h('a', {class: 'button secondary', href: latest.url, target: '_blank', rel: 'noopener noreferrer', text: 'What’s new'}),
      button('Update now', install, 'primary'),
      button('Later', () => { writeStored('practice-update-skip', latest.version); hide(); }, 'text-button')),
  ];
  show(...parts);
}

function renderInstalled() {
  const result = info.installed;
  const c = result.counts;
  const details = `${c.update} updated, ${c.add} added, ${c.delete} removed.`;
  const kept = result.kept.length
    ? h('p', {class: 'update-text muted', text: `Kept your edited ${result.kept.join(', ')}. The release copies are in ${result.stash}/ for comparison.`})
    : null;
  const action = info.can_restart
    ? button('Restart now', restart, 'primary')
    : h('p', {class: 'update-text', text: 'Stop web.command with Ctrl-C and start it again to use the new version.'});
  show(h('p', {class: 'update-text success'}, h('strong', {text: `Installed ${versionLabel(result.version)}. `}), details,
    ' Review the change with git status, then commit it.'), kept, h('div', {class: 'update-actions'}, action));
}

function renderMigration() {
  const items = info.migration;
  const list = h('ul', {class: 'update-list'}, items.slice(0, 8).map(item => h('li', {}, h('code', {text: item.key}), ': ' + item.changes.join('; '))));
  if (items.length > 8) list.append(h('li', {text: `…and ${items.length - 8} more`}));
  show(h('p', {class: 'update-text'}, h('strong', {text: `${items.length} saved problem${items.length === 1 ? '' : 's'} use the older record layout. `}),
    'Upgrading adds problem.json, keeps folder hashes and never changes code, notes or Quick recall.'),
    list, h('div', {class: 'update-actions'}, button('Upgrade records', applyMigration, 'primary'),
      button('Later', () => { writeStored('practice-migration-later', true, 'session'); hide(); }, 'text-button')));
}

function render() {
  renderFooter();
  if (!info) return;
  if (info.installed) { renderInstalled(); return; }
  if (info.available && info.latest && readStored('practice-update-skip', '') !== info.latest.version) { renderAvailable(); return; }
  if (info.migration?.length && !readStored('practice-migration-later', false, 'session')) { renderMigration(); return; }
  hide();
}

async function check(force) {
  try {
    info = force ? await api('/api/update/check', {}) : await api('/api/update');
  } catch (error) {
    if (force) message(error.message, 'error');
    return;
  }
  if (force) {
    writeStored('practice-update-skip', null);
    if (info.error) { renderFooter(); message('Could not check for updates: ' + info.error, 'error'); return; }
    if (!info.available && !info.installed) { renderFooter(); message(`You have the latest version (${versionLabel(info.current)}).`, 'success'); return; }
  }
  render();
  // The service checks in the background when it starts; pick up that result once.
  const stale = !info.checked_at || Date.now() / 1000 - info.checked_at > 86400;
  if (!force && !retried && info.auto_check && stale) { retried = true; setTimeout(() => check(false), 5000); }
}

async function install() {
  if (hasUnsaved() && !window.confirm('You have unsaved edits. Install the update anyway? They stay in this tab until you restart.')) return;
  show(h('p', {class: 'update-text', text: 'Downloading and installing the update…'}));
  try { info = await api('/api/update/install', {}); render(); }
  catch (error) { message(error.message, 'error'); }
}

async function restart() {
  if (hasUnsaved() && !window.confirm('Restarting reloads the page and discards unsaved edits. Continue?')) return;
  let before;
  try { before = (await api('/api/restart', {})).boot; }
  catch (error) { message(error.message, 'error'); return; }
  show(h('p', {class: 'update-text', text: 'Restarting with the new version…'}));
  const started = Date.now();
  const poll = async () => {
    try {
      const response = await fetch('/api/health', {cache: 'no-store'});
      const health = await response.json();
      if (health.boot && health.boot !== before) { window.onbeforeunload = null; location.reload(); return; }
    } catch (_) { /* still restarting */ }
    if (Date.now() - started > 30000) { message('The app did not come back. Start web.command again.', 'error'); return; }
    setTimeout(poll, 700);
  };
  setTimeout(poll, 700);
}

async function applyMigration() {
  show(h('p', {class: 'update-text', text: 'Upgrading saved records…'}));
  try {
    info = await api('/api/migrate', {});
    await refreshProblems().catch(() => {});
    message(`Upgraded ${info.migrated} problem folder${info.migrated === 1 ? '' : 's'}. Review with git status, then commit the result.`, 'success');
    renderFooter();
  } catch (error) { message(error.message, 'error'); }
}

export function initUpdates() { check(false); }
