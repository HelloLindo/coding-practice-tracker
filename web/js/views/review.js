// Review page: progress at a glance, practice calendar, and what to revisit.

import {h, problemHref, statusPill, difficultyPill, formatDate, STATUS_LABELS} from '../dom.js';
import {api} from '../api.js';

const WEEKS = 26;

function isoDate(date) {
  return `${date.getFullYear()}${String(date.getMonth() + 1).padStart(2, '0')}${String(date.getDate()).padStart(2, '0')}`;
}

function parseDay(text) { return new Date(+text.slice(0, 4), +text.slice(4, 6) - 1, +text.slice(6, 8)); }

function streak(calendar, today) {
  let day = parseDay(today);
  if (!calendar[isoDate(day)]) day.setDate(day.getDate() - 1);
  let count = 0;
  while (calendar[isoDate(day)]) { count++; day.setDate(day.getDate() - 1); }
  return count;
}

function tile(value, label, detail) {
  return h('div', {class: 'stat-tile'}, h('span', {class: 'stat-value', text: String(value)}), h('span', {class: 'stat-label', text: label}),
    detail ? h('span', {class: 'stat-detail', text: detail}) : null);
}

function heatmap(calendar, today) {
  const end = parseDay(today);
  const start = new Date(end);
  start.setDate(start.getDate() - (WEEKS * 7 - 1));
  start.setDate(start.getDate() - start.getDay());  // Weeks start on Sunday.
  const grid = h('div', {class: 'heatmap', role: 'img', 'aria-label': 'Practices per day over the last six months'});
  const months = h('div', {class: 'heatmap-months', 'aria-hidden': 'true'});
  let lastMonth = -1;
  let total = 0;
  for (let week = 0; ; week++) {
    const column = h('div', {class: 'heatmap-week'});
    const first = new Date(start);
    first.setDate(first.getDate() + week * 7);
    if (first > end) break;
    const monthLabel = first.getMonth() !== lastMonth ? first.toLocaleDateString('en-US', {month: 'short'}) : '';
    if (monthLabel) lastMonth = first.getMonth();
    months.append(h('span', {text: monthLabel}));
    for (let day = 0; day < 7; day++) {
      const date = new Date(first);
      date.setDate(date.getDate() + day);
      const key = isoDate(date);
      const count = calendar[key] || 0;
      total += date <= end ? count : 0;
      const level = date > end ? 'future' : String(Math.min(count, 4));
      const label = date > end ? '' : `${count} practice${count === 1 ? '' : 's'} on ${formatDate(key)}`;
      column.append(h('span', {class: 'heatmap-cell level-' + level, title: label, 'aria-label': label || null}));
    }
    grid.append(column);
  }
  const legend = h('div', {class: 'heatmap-legend', 'aria-hidden': 'true'}, h('span', {text: 'Less'}),
    [0, 1, 2, 3, 4].map(n => h('span', {class: 'heatmap-cell level-' + n})), h('span', {text: 'More'}));
  return {element: h('div', {class: 'heatmap-wrap'}, months, grid, legend), total};
}

function fill(ratio) {
  const element = h('span', {class: 'bar-fill'});
  element.style.width = (ratio * 100).toFixed(1) + '%';  // CSSOM, allowed by the page's CSP.
  return element;
}

function bars(title, entries, total) {
  const max = Math.max(1, ...entries.map(([, value]) => value));
  return h('div', {class: 'bar-chart'}, h('h3', {class: 'subheading', text: title}),
    entries.map(([label, value]) => h('div', {class: 'bar-row', title: `${label}: ${value} of ${total}`},
      h('span', {class: 'bar-label', text: label}),
      h('span', {class: 'bar-track'}, fill(value / max)),
      h('span', {class: 'bar-value', text: String(value)}))));
}

function list(items, empty) {
  if (!items.length) return h('p', {class: 'muted', text: empty});
  return h('ul', {class: 'review-list'}, items.map(item => h('li', {},
    h('a', {href: problemHref(item.key)},
      h('span', {class: 'review-title'}, h('strong', {text: item.title}),
        h('small', {text: [item.platform_label, ...(item.companies || [])].filter(Boolean).join(' · ')})),
      h('span', {class: 'review-meta'}, statusPill(item.status), difficultyPill(item.difficulty),
        h('span', {class: 'muted small', text: formatDate(item.date) + (item.count > 1 ? ` · ${item.count}×` : '')}))))));
}

export async function reviewView(root) {
  const data = await api('/api/report');
  const recent = Object.entries(data.calendar).filter(([day]) => parseDay(day) >= new Date(parseDay(data.today).getTime() - 6 * 864e5))
    .reduce((sum, [, count]) => sum + count, 0);
  const map = heatmap(data.calendar, data.today);
  const statusEntries = ['independent', 'improved', 'learned'].map(s => [STATUS_LABELS[s], data.latest_status[s] || 0]);
  const difficultyEntries = ['1', '2', '3', '4', '5', 'unrated'].filter(d => d !== 'unrated' || data.latest_difficulty.unrated)
    .map(d => [d === 'unrated' ? 'Unrated' : d + '/5', data.latest_difficulty[d] || 0]);
  const platformEntries = Object.entries(data.platforms).sort((a, b) => b[1] - a[1]).map(([name, count]) => [data.platform_labels[name] || name, count]);

  root.replaceChildren(
    h('header', {class: 'page-header'}, h('div', {},
      h('div', {class: 'eyebrow', text: 'WHAT TO REVISIT'}), h('h1', {text: 'Review'}),
      h('p', {text: 'Based on your own reported status and difficulty — not a mastery verdict.'}))),
    h('div', {class: 'stat-row'},
      tile(data.problems, 'Problems'), tile(data.practices, 'Practices'),
      tile(recent, 'Last 7 days', 'practices'), tile(streak(data.calendar, data.today), 'Day streak', 'consecutive days')),
    h('section', {class: 'panel'}, h('div', {class: 'panel-heading'}, h('div', {},
      h('span', {class: 'step-label', text: 'RHYTHM'}), h('h2', {text: 'Practice calendar'})),
    h('span', {class: 'pill neutral', text: `${map.total} in ${WEEKS} weeks`})), map.element),
    h('div', {class: 'workspace review-workspace'},
      h('section', {class: 'panel'}, h('div', {class: 'panel-heading'}, h('div', {},
        h('span', {class: 'step-label', text: 'REVISIT FIRST'}), h('h2', {text: 'Review candidates'})),
      h('span', {class: 'pill neutral', text: String(data.review.length)})),
      h('p', {class: 'panel-description', text: 'Latest practice was improved or learned, or rated 4–5. Hardest first, then oldest.'}),
      list(data.review, 'No review candidates recorded yet. This does not establish mastery.')),
      h('div', {class: 'column'},
        h('section', {class: 'panel'}, h('div', {class: 'panel-heading'}, h('div', {},
          h('span', {class: 'step-label', text: 'LATEST PRACTICE'}), h('h2', {text: 'Distribution'}))),
        bars('Status', statusEntries, data.problems), bars('Difficulty', difficultyEntries, data.problems),
        bars('Platform', platformEntries, data.problems)),
        h('section', {class: 'panel'}, h('div', {class: 'panel-heading'}, h('div', {},
          h('span', {class: 'step-label', text: 'COMFORTABLE'}), h('h2', {text: 'Personally easiest'}))),
        h('p', {class: 'panel-description', text: 'Latest practice independent and rated 1–2.'}),
        list(data.easiest, 'No personally easiest problems recorded yet.')))));
}
