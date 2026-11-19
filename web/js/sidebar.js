// Sidebar: search, filters, sorting, grouping and the problem list.

import {$, h, clear, readStored, writeStored, problemHref, STATUS_LABELS} from './dom.js';
import {state, onProblems, refreshProblems, notice} from './state.js';

const DEFAULTS = {platform: '', status: '', difficulty: '', company: '', tag: '', sort: 'recent', group: ''};
const SORTS = {
  recent: ['Recent practice', (a, b) => b.date.localeCompare(a.date) || a.title.localeCompare(b.title)],
  oldest: ['Oldest latest practice', (a, b) => a.date.localeCompare(b.date) || a.title.localeCompare(b.title)],
  difficulty: ['Highest difficulty', (a, b) => (b.difficulty || 0) - (a.difficulty || 0) || a.date.localeCompare(b.date)],
  count: ['Most practiced', (a, b) => b.count - a.count || b.date.localeCompare(a.date)],
  title: ['Title A–Z', (a, b) => a.title.localeCompare(b.title)],
  added: ['First practiced', (a, b) => b.first_date.localeCompare(a.first_date) || a.title.localeCompare(b.title)],
};
const GROUPS = {'': 'No grouping', platform: 'Platform', company: 'Company', status: 'Latest status', difficulty: 'Latest difficulty'};

let filters = {...DEFAULTS, ...readStored('practice-filters', {})};

function options(select, entries, current) {
  clear(select);
  if (current && !entries.some(([value]) => value === current)) entries = [...entries, [current, current]];
  for (const [value, label] of entries) select.append(h('option', {value, text: label}));
  select.value = entries.some(([value]) => value === current) ? current : '';
}

function unique(values) {
  return [...new Set(values)].sort((a, b) => a.localeCompare(b, undefined, {sensitivity: 'base'}));
}

function populate(problems) {
  const platforms = unique(problems.map(p => p.platform));
  options($('filter-platform'), [['', 'All platforms'], ...platforms.map(p => [p, state.byPlatform[p]?.label || p])], filters.platform);
  options($('filter-status'), [['', 'Any status'], ...Object.entries(STATUS_LABELS).filter(([k]) => k !== 'unknown')], filters.status);
  options($('filter-difficulty'), [['', 'Any difficulty'], ...[1, 2, 3, 4, 5].map(n => [String(n), n + '/5']), ['unrated', 'Unrated']], filters.difficulty);
  options($('filter-company'), [['', 'Any company'], ...unique(problems.flatMap(p => p.companies)).map(c => [c, c])], filters.company);
  options($('filter-tag'), [['', 'Any tag'], ...unique(problems.flatMap(p => p.tags)).map(t => [t, t])], filters.tag);
  options($('sort'), Object.entries(SORTS).map(([k, [label]]) => [k, label]), filters.sort);
  if (!$('sort').value) $('sort').value = 'recent';
  options($('group'), Object.entries(GROUPS), filters.group);
}

function matches(problem) {
  if (filters.platform && problem.platform !== filters.platform) return false;
  if (filters.status && problem.status !== filters.status) return false;
  if (filters.difficulty && String(problem.difficulty || 'unrated') !== filters.difficulty) return false;
  if (filters.company && !problem.companies.includes(filters.company)) return false;
  if (filters.tag && !problem.tags.includes(filters.tag)) return false;
  return true;
}

function groupNames(problem) {
  switch (filters.group) {
    case 'platform': return [problem.platform_label];
    case 'company': return problem.companies.length ? problem.companies : ['No company'];
    case 'status': return [STATUS_LABELS[problem.status] || problem.status];
    case 'difficulty': return [problem.difficulty ? 'Difficulty ' + problem.difficulty + '/5' : 'Unrated'];
    default: return [''];
  }
}

function item(problem) {
  const selected = state.route.name === 'problem' && state.route.params.key === problem.key;
  const prefix = problem.platform === 'leetcode' && problem.id ? problem.id + '. ' : '';
  const meta = [problem.platform_label, STATUS_LABELS[problem.status] || problem.status,
    problem.difficulty ? problem.difficulty + '/5' : 'Unrated'];
  if (problem.count > 1) meta.push(problem.count + '×');
  return h('a', {class: 'problem-item' + (selected ? ' selected' : ''), href: problemHref(problem.key),
    dataset: {key: problem.key}, 'aria-current': selected ? 'page' : null},
  h('strong', {text: prefix + problem.title}),
  h('small', {text: meta.join(' · ')}));
}

export function renderList() {
  const list = $('problem-list');
  const visible = state.problems.filter(matches);
  visible.sort(SORTS[filters.sort]?.[1] || SORTS.recent[1]);
  const active = Object.keys(DEFAULTS).filter(k => !['sort', 'group'].includes(k) && filters[k]).length;
  $('filter-badge').hidden = !active;
  $('filter-badge').textContent = active;
  $('problem-count').textContent = visible.length === state.problems.length ? visible.length : `${visible.length}/${state.problems.length}`;
  clear(list);
  if (!visible.length) {
    list.append(h('p', {class: 'muted sidebar-empty',
      text: state.problems.length ? 'No problems match these filters.' : (state.query ? 'No matching problems.' : 'Your saved problems will appear here.')}));
    return;
  }
  if (!filters.group) { visible.forEach(problem => list.append(item(problem))); return; }
  const groups = new Map();
  for (const problem of visible) for (const name of groupNames(problem)) {
    if (!groups.has(name)) groups.set(name, []);
    groups.get(name).push(problem);
  }
  for (const name of [...groups.keys()].sort((a, b) => a.localeCompare(b))) {
    list.append(h('div', {class: 'group-heading'}, h('span', {text: name}), h('span', {class: 'count', text: groups.get(name).length})));
    groups.get(name).forEach(problem => list.append(item(problem)));
  }
}

export function knownCompanies() { return unique(state.problems.flatMap(p => p.companies)); }
export function knownTags() { return unique(state.problems.flatMap(p => p.tags)); }

export function initSidebar() {
  onProblems(problems => { populate(problems); renderList(); });
  const ids = {platform: 'filter-platform', status: 'filter-status', difficulty: 'filter-difficulty',
    company: 'filter-company', tag: 'filter-tag', sort: 'sort', group: 'group'};
  for (const [key, id] of Object.entries(ids)) {
    $(id).addEventListener('change', () => { filters[key] = $(id).value; writeStored('practice-filters', filters); renderList(); });
  }
  $('clear-filters').addEventListener('click', () => {
    filters = {...DEFAULTS, sort: filters.sort, group: filters.group};
    writeStored('practice-filters', filters);
    populate(state.problems); renderList();
  });
  const toggle = $('filter-toggle');
  const panelOpen = readStored('practice-filters-open', false);
  $('filters').hidden = !panelOpen;
  toggle.setAttribute('aria-expanded', String(panelOpen));
  toggle.addEventListener('click', () => {
    const open = $('filters').hidden;
    $('filters').hidden = !open;
    toggle.setAttribute('aria-expanded', String(open));
    writeStored('practice-filters-open', open);
  });
  let timer;
  $('problem-search').addEventListener('input', () => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      state.query = $('problem-search').value.trim();
      refreshProblems().catch(error => notice(error.message, 'error'));
    }, 180);
  });
}
