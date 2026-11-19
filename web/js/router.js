// Hash router: #/new, #/new/<platform>/<key>, #/p/<platform>/<key>, #/review.

import {$} from './dom.js';
import {state, notice, confirmLeave, setGuard, hasUnsaved} from './state.js';

const views = {};
let lastHash = '';
let ignoreNext = false;
let pendingFlash = null;
let options = {};
let renderVersion = 0;
let afterRender = () => {};

export function register(name, view) { views[name] = view; }
export function onRender(callback) { afterRender = callback; }
export function flash(message, type = '') { pendingFlash = message ? {message, type} : null; }

export function parse(hash) {
  const parts = (hash || '').replace(/^#\/?/, '').split('/').filter(Boolean).map(decodeURIComponent);
  if (parts[0] === 'p' && parts.length === 3) return {name: 'problem', params: {key: parts[1] + '/' + parts[2]}};
  if (parts[0] === 'new' && parts.length === 3) return {name: 'new', params: {key: parts[1] + '/' + parts[2]}};
  if (parts[0] === 'review') return {name: 'review', params: {}};
  return {name: 'new', params: {}};
}

export function navigate(hash, navigationOptions = {}) {
  options = navigationOptions;
  if (navigationOptions.force) setGuard(null);
  if (location.hash === hash) render();
  else location.hash = hash;
}

export function currentOptions() { return options; }

export async function render() {
  const version = ++renderVersion;
  lastHash = location.hash;
  const route = parse(location.hash);
  state.route = route;
  setGuard(null);
  notice('');
  if (pendingFlash) { notice(pendingFlash.message, pendingFlash.type); pendingFlash = null; }
  document.querySelectorAll('.nav-link').forEach(link => {
    const active = link.dataset.route === route.name && !(route.name === 'new' && route.params.key);
    link.classList.toggle('active', active);
    if (active) link.setAttribute('aria-current', 'page'); else link.removeAttribute('aria-current');
  });
  afterRender(route);
  const root = $('view');
  const view = views[route.name];
  const navigationOptions = options;
  options = {};
  try {
    const result = await view(root, route.params, navigationOptions);
    if (version === renderVersion) state.view = result || {};
  } catch (error) {
    if (version !== renderVersion) return;
    root.replaceChildren();
    notice(error.message, 'error');
  }
  window.scrollTo({top: 0});
}

export function start() {
  window.addEventListener('hashchange', () => {
    if (ignoreNext) { ignoreNext = false; return; }
    if (!confirmLeave()) { ignoreNext = true; location.hash = lastHash; return; }
    render();
  });
  window.addEventListener('beforeunload', event => {
    if (hasUnsaved()) { event.preventDefault(); event.returnValue = ''; }
  });
  if (!location.hash) history.replaceState(null, '', '#/new');
  return render();
}
