// Safe Markdown renderer (GitHub-flavoured subset) built directly as DOM nodes.
// Raw HTML is shown as text; only http(s)/mailto links are created.

import {codeBlock} from './highlight.js';
import {renderMath} from './math.js';

const SAFE_URL = /^(https?:\/\/|mailto:)/i;

function link(href, children) {
  if (!SAFE_URL.test(href)) return null;
  const a = document.createElement('a');
  a.href = href;
  a.target = '_blank';
  a.rel = 'noopener noreferrer';
  a.append(...children);
  return a;
}

function wrap(tag, children) {
  const element = document.createElement(tag);
  element.append(...children);
  return element;
}

const INLINE_RULES = [
  ['\\', /\\([\\`*_{}[\]()#+\-.!$~|<>])/y, m => [document.createTextNode(m[1])]],
  ['`', /(`+)([\s\S]*?[^`])\1(?!`)/y, m => [wrap('code', [m[2].replace(/^ (.*) $/s, '$1')])]],
  ['$', /\$\$([\s\S]+?)\$\$/y, m => [renderMath(m[1], true)]],
  ['$', /\$(?!\s)((?:\\.|[^$\\\n])+?)(?<!\s)\$(?!\d)/y, m => [renderMath(m[1])]],
  ['*', /\*\*(?=\S)([\s\S]+?)(?<=\S)\*\*/y, m => [wrap('strong', inline(m[1]))]],
  ['_', /(?<![\w])__(?=\S)([\s\S]+?)(?<=\S)__(?![\w])/y, m => [wrap('strong', inline(m[1]))]],
  ['~', /~~(?=\S)([\s\S]+?)(?<=\S)~~/y, m => [wrap('del', inline(m[1]))]],
  ['*', /\*(?=[^\s*])([\s\S]+?)(?<=[^\s*])\*/y, m => [wrap('em', inline(m[1]))]],
  ['_', /(?<![\w])_(?=[^\s_])([\s\S]+?)(?<=[^\s_])_(?![\w])/y, m => [wrap('em', inline(m[1]))]],
  ['!', /!\[([^\]\n]*)\]\(\s*<?([^\s)>]+)>?(?:\s+"[^"]*")?\s*\)/y,
    m => { const a = link(m[2], [m[1] || m[2]]); return a ? [a] : [document.createTextNode(m[0])]; }],
  ['[', /\[((?:\\.|[^\]\n])*)\]\(\s*<?([^\s)>]+)>?(?:\s+"[^"]*")?\s*\)/y,
    m => { const a = link(m[2], inline(m[1])); return a ? [a] : [document.createTextNode(m[0])]; }],
  ['<', /<((?:https?:\/\/|mailto:)[^>\s]+)>/y, m => [link(m[1], [m[1]])]],
  ['h', /(?<![\w/])https?:\/\/[^\s<]*[^\s<.,;:!?)\]'"*_~]/y, m => [link(m[0], [m[0]])]],
];

export function inline(text) {
  const nodes = [];
  let buffer = '';
  let index = 0;
  const flush = () => { if (buffer) { nodes.push(document.createTextNode(buffer)); buffer = ''; } };
  while (index < text.length) {
    const char = text[index];
    let done = false;
    if (char === '\n') { flush(); nodes.push(document.createElement('br')); index += 1; continue; }
    for (const [first, rule, build] of INLINE_RULES) {
      if (first !== char) continue;
      rule.lastIndex = index;
      const match = rule.exec(text);
      if (!match) continue;
      flush();
      nodes.push(...build(match));
      index = rule.lastIndex;
      done = true;
      break;
    }
    if (!done) { buffer += char; index += 1; }
  }
  flush();
  return nodes;
}

const FENCE = /^(\s{0,3})(`{3,}|~{3,})\s*([\w+#-]*)[^`]*$/;
const HEADING = /^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$/;
const RULE = /^\s{0,3}([-*_])(?:\s*\1){2,}\s*$/;
const LIST = /^(\s*)([-*+]|\d{1,9}[.)])\s+(.*)$/;
const QUOTE = /^\s{0,3}>\s?(.*)$/;
const TABLE_SEPARATOR = /^\s*\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)*\|?\s*$/;

function splitRow(line) {
  let row = line.trim();
  if (row.startsWith('|')) row = row.slice(1);
  if (row.endsWith('|') && !row.endsWith('\\|')) row = row.slice(0, -1);
  const cells = [];
  let cell = '';
  for (let i = 0; i < row.length; i++) {
    if (row[i] === '\\' && row[i + 1] === '|') { cell += '|'; i++; }
    else if (row[i] === '|') { cells.push(cell.trim()); cell = ''; }
    else cell += row[i];
  }
  cells.push(cell.trim());
  return cells;
}

function blockStart(line, next) {
  return FENCE.test(line) || HEADING.test(line) || RULE.test(line) || LIST.test(line) || QUOTE.test(line)
    || /^\s*\$\$/.test(line) || (line.includes('|') && next !== undefined && TABLE_SEPARATOR.test(next) && next.includes('-'));
}

function newList(parent, indent, ordered, marker) {
  const list = document.createElement(ordered ? 'ol' : 'ul');
  const number = parseInt(marker, 10);
  if (ordered && number !== 1) list.start = number;
  parent.append(list);
  return {indent, list, ordered};
}

function renderList(lines, start, target) {
  // Builds nested lists from indentation. Returns the index after the list.
  const stack = [];
  let index = start;
  let lastItem = null;
  while (index < lines.length) {
    const line = lines[index];
    const match = LIST.exec(line);
    if (!match) {
      if (!line.trim()) {
        const next = lines[index + 1];
        if (next !== undefined && (LIST.test(next) || /^\s{2,}\S/.test(next))) { index++; continue; }
        break;
      }
      if (lastItem && (/^\s{2,}\S/.test(line) || !blockStart(line, lines[index + 1]))) {
        lastItem.append(document.createElement('br'), ...inline(line.trim()));
        index++;
        continue;
      }
      break;
    }
    const indent = match[1].replace(/\t/g, '    ').length;
    const ordered = /\d/.test(match[2]);
    while (stack.length && indent < stack[stack.length - 1].indent) stack.pop();
    let top = stack[stack.length - 1];
    if (!top) {
      top = newList(target, indent, ordered, match[2]);
      stack.push(top);
    } else if (indent >= top.indent + 2 && lastItem) {
      top = newList(lastItem, indent, ordered, match[2]);
      stack.push(top);
    } else if (top.ordered !== ordered) {
      const parent = top.list.parentNode;
      stack.pop();
      top = newList(parent, indent, ordered, match[2]);
      stack.push(top);
    }
    const item = document.createElement('li');
    let content = match[3];
    const task = /^\[([ xX])\]\s+(.*)$/.exec(content);
    if (task) {
      const box = document.createElement('input');
      box.type = 'checkbox'; box.disabled = true; box.checked = task[1] !== ' ';
      item.append(box, ' ');
      content = task[2];
    }
    item.append(...inline(content));
    top.list.append(item);
    lastItem = item;
    index++;
  }
  return index;
}

export function renderMarkdown(target, text, {emptyText = ''} = {}) {
  target.replaceChildren();
  target.classList.add('markdown');
  const lines = String(text || '').replace(/\r\n?/g, '\n').split('\n');
  let index = 0;
  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) { index++; continue; }
    const fence = FENCE.exec(line);
    if (fence) {
      const marker = fence[2];
      const body = [];
      index++;
      while (index < lines.length && !new RegExp('^\\s{0,3}' + marker[0] + '{' + marker.length + ',}\\s*$').test(lines[index])) body.push(lines[index++]);
      index++;
      target.append(codeBlock(body.join('\n'), fence[3] || 'text'));
      continue;
    }
    if (/^\s*\$\$/.test(line)) {
      const single = /^\s*\$\$(.+)\$\$\s*$/.exec(line);
      if (single) { target.append(wrap('div', [renderMath(single[1], true)])); index++; continue; }
      const body = [line.replace(/^\s*\$\$/, '')];
      index++;
      while (index < lines.length && !/\$\$\s*$/.test(lines[index])) body.push(lines[index++]);
      if (index < lines.length) body.push(lines[index++].replace(/\$\$\s*$/, ''));
      target.append(wrap('div', [renderMath(body.join(' '), true)]));
      continue;
    }
    const heading = HEADING.exec(line);
    if (heading) {
      target.append(wrap('h' + Math.min(6, heading[1].length + 2), inline(heading[2])));
      index++;
      continue;
    }
    if (RULE.test(line)) { target.append(document.createElement('hr')); index++; continue; }
    if (QUOTE.test(line)) {
      const body = [];
      while (index < lines.length && (QUOTE.test(lines[index]) || (lines[index].trim() && !blockStart(lines[index])))) {
        const match = QUOTE.exec(lines[index]);
        body.push(match ? match[1] : lines[index]);
        index++;
      }
      const quote = document.createElement('blockquote');
      renderMarkdown(quote, body.join('\n'));
      quote.classList.remove('markdown');
      target.append(quote);
      continue;
    }
    if (LIST.test(line)) { index = renderList(lines, index, target); continue; }
    const next = lines[index + 1];
    if (line.includes('|') && next !== undefined && TABLE_SEPARATOR.test(next) && next.includes('-')) {
      const header = splitRow(line);
      const aligns = splitRow(next).map(cell => cell.startsWith(':') && cell.endsWith(':') ? 'center' : cell.endsWith(':') ? 'right' : cell.startsWith(':') ? 'left' : '');
      const table = document.createElement('table');
      const thead = table.createTHead().insertRow();
      header.forEach((cell, i) => { const th = document.createElement('th'); th.append(...inline(cell)); if (aligns[i]) th.style.textAlign = aligns[i]; thead.append(th); });
      const body = table.createTBody();
      index += 2;
      while (index < lines.length && lines[index].includes('|') && lines[index].trim()) {
        const row = body.insertRow();
        splitRow(lines[index]).forEach((cell, i) => { const td = row.insertCell(); td.append(...inline(cell)); if (aligns[i]) td.style.textAlign = aligns[i]; });
        index++;
      }
      const scroller = wrap('div', [table]);
      scroller.className = 'table-scroll';
      target.append(scroller);
      continue;
    }
    const paragraph = [line];
    index++;
    while (index < lines.length && lines[index].trim() && !blockStart(lines[index], lines[index + 1])) paragraph.push(lines[index++]);
    target.append(wrap('p', inline(paragraph.map(l => l.trim()).join('\n'))));
  }
  if (!target.childNodes.length && emptyText) {
    const p = document.createElement('p');
    p.className = 'muted';
    p.textContent = emptyText;
    target.append(p);
  }
  return target;
}
