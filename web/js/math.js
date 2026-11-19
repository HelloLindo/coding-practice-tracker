// A small TeX subset for problem statements: sub/superscripts, fractions, roots,
// \text{}, common operators and Greek letters. Unknown commands are shown as written.

const SYMBOLS = {
  times: '×', cdot: '·', div: '÷', pm: '±', mp: '∓', le: '≤', leq: '≤', ge: '≥', geq: '≥', ne: '≠', neq: '≠',
  approx: '≈', equiv: '≡', sim: '∼', to: '→', rightarrow: '→', leftarrow: '←', Rightarrow: '⇒', Leftarrow: '⇐',
  leftrightarrow: '↔', iff: '⇔', implies: '⇒', infty: '∞', sum: '∑', prod: '∏', in: '∈', notin: '∉',
  subset: '⊂', subseteq: '⊆', supset: '⊃', cup: '∪', cap: '∩', emptyset: '∅', forall: '∀', exists: '∃',
  lfloor: '⌊', rfloor: '⌋', lceil: '⌈', rceil: '⌉', langle: '⟨', rangle: '⟩', ldots: '…', cdots: '⋯',
  dots: '…', vdots: '⋮', mid: '∣', vert: '|', lvert: '|', rvert: '|', Vert: '‖', neg: '¬', land: '∧', lor: '∨',
  oplus: '⊕', otimes: '⊗', circ: '∘', bullet: '•', star: '⋆', prime: '′', partial: '∂', nabla: '∇',
  alpha: 'α', beta: 'β', gamma: 'γ', delta: 'δ', epsilon: 'ε', varepsilon: 'ε', zeta: 'ζ', eta: 'η',
  theta: 'θ', iota: 'ι', kappa: 'κ', lambda: 'λ', mu: 'μ', nu: 'ν', xi: 'ξ', pi: 'π', rho: 'ρ', sigma: 'σ',
  tau: 'τ', upsilon: 'υ', phi: 'φ', varphi: 'φ', chi: 'χ', psi: 'ψ', omega: 'ω', Gamma: 'Γ', Delta: 'Δ',
  Theta: 'Θ', Lambda: 'Λ', Xi: 'Ξ', Pi: 'Π', Sigma: 'Σ', Phi: 'Φ', Psi: 'Ψ', Omega: 'Ω',
  quad: ' ', qquad: '  ', ',': ' ', ';': ' ', ':': ' ', '!': '', ' ': ' ',
  '{': '{', '}': '}', '$': '$', '%': '%', '#': '#', '&': '&', '_': '_', '|': '‖', backslash: '\\',
};
const WORDS = new Set(['log', 'ln', 'lg', 'max', 'min', 'mod', 'gcd', 'lcm', 'sin', 'cos', 'tan', 'exp', 'det', 'deg', 'arg', 'lim', 'sup', 'inf']);
const TEXT = new Set(['text', 'textrm', 'mathrm', 'textbf', 'mathbf', 'textit', 'mathit', 'operatorname', 'texttt', 'mathtt', 'boldsymbol']);
const RELATIONS = new Set(['times', 'cdot', 'div', 'pm', 'le', 'leq', 'ge', 'geq', 'ne', 'neq', 'approx', 'equiv', 'to', 'rightarrow', 'leftarrow', 'Rightarrow', 'Leftarrow', 'leftrightarrow', 'iff', 'implies', 'in', 'notin', 'subset', 'subseteq', 'supset', 'cup', 'cap', 'mid', 'land', 'lor', 'oplus', 'otimes']);
const IGNORE = new Set(['left', 'right', 'big', 'Big', 'bigg', 'Bigg', 'displaystyle', 'limits', 'nolimits']);

function lex(tex) {
  const out = [];
  for (let i = 0; i < tex.length;) {
    const char = tex[i];
    if (char === '\\') {
      const word = /^[A-Za-z]+/.exec(tex.slice(i + 1));
      if (word) { out.push({cmd: word[0]}); i += word[0].length + 1; }
      else if (tex[i + 1] === '\\') { out.push({cmd: 'newline'}); i += 2; }
      else { out.push({cmd: tex[i + 1] ?? ''}); i += 2; }
    } else { out.push({char}); i += 1; }
  }
  return out;
}

function parse(tokens, state, stop) {
  const nodes = [];
  while (state.i < tokens.length) {
    const token = tokens[state.i];
    if (stop && token.char === stop) { state.i += 1; return nodes; }
    nodes.push(atom(tokens, state));
  }
  return nodes;
}

function rawGroup(tokens, state) {
  // Text inside \text{...}: keep characters literally.
  let text = '';
  if (tokens[state.i]?.char !== '{') return text;
  state.i += 1;
  let depth = 1;
  while (state.i < tokens.length) {
    const token = tokens[state.i++];
    if (token.char === '{') depth += 1;
    if (token.char === '}' && --depth === 0) break;
    text += token.char ?? (SYMBOLS[token.cmd] ?? (token.cmd.length === 1 ? token.cmd : '\\' + token.cmd));
  }
  return text;
}

function argument(tokens, state) {
  while (tokens[state.i]?.char === ' ') state.i += 1;
  return state.i < tokens.length ? atom(tokens, state) : {type: 'group', children: []};
}

function atom(tokens, state) {
  const token = tokens[state.i++];
  if (token.char === '{') return {type: 'group', children: parse(tokens, state, '}')};
  if (token.char === '^' || token.char === '_') return {type: token.char === '^' ? 'sup' : 'sub', child: argument(tokens, state)};
  if (token.char !== undefined) return {type: 'char', value: token.char};
  const cmd = token.cmd;
  if (cmd === 'frac' || cmd === 'dfrac' || cmd === 'tfrac') return {type: 'frac', top: argument(tokens, state), bottom: argument(tokens, state)};
  if (cmd === 'sqrt') return {type: 'sqrt', child: argument(tokens, state)};
  if (cmd === 'binom') return {type: 'binom', top: argument(tokens, state), bottom: argument(tokens, state)};
  if (TEXT.has(cmd)) return {type: 'text', value: rawGroup(tokens, state), bold: /bf|bold/.test(cmd)};
  if (cmd === 'overline' || cmd === 'bar') return {type: 'overline', child: argument(tokens, state)};
  if (IGNORE.has(cmd)) return {type: 'group', children: []};
  if (cmd === 'newline') return {type: 'break'};
  if (WORDS.has(cmd)) return {type: 'text', value: '\u2009' + cmd + '\u2009'};
  if (RELATIONS.has(cmd)) return {type: 'symbol', value: '\u2009' + SYMBOLS[cmd] + '\u2009'};
  if (cmd in SYMBOLS) return {type: 'symbol', value: SYMBOLS[cmd]};
  return {type: 'text', value: '\\' + cmd};
}

function render(node) {
  const span = cls => { const element = document.createElement('span'); if (cls) element.className = cls; return element; };
  switch (node.type) {
    case 'group': { const element = span(); node.children.forEach(child => element.append(render(child))); return element; }
    case 'sup': case 'sub': { const element = document.createElement(node.type); element.append(render(node.child)); return element; }
    case 'frac': case 'binom': {
      const element = span('math-frac' + (node.type === 'binom' ? ' math-binom' : ''));
      const top = span(); top.append(render(node.top));
      const bottom = span(); bottom.append(render(node.bottom));
      element.append(top, bottom);
      return element;
    }
    case 'sqrt': { const element = span('math-sqrt'); const body = span(); body.append(render(node.child)); element.append('√', body); return element; }
    case 'overline': { const element = span('math-overline'); element.append(render(node.child)); return element; }
    case 'text': { const element = span(node.bold ? 'math-text math-bold' : 'math-text'); element.textContent = node.value; return element; }
    case 'symbol': return document.createTextNode(node.value);
    case 'break': return document.createElement('br');
    default: {
      if (/[A-Za-z]/.test(node.value)) { const element = document.createElement('i'); element.textContent = node.value; return element; }
      if (node.value === ' ') return document.createTextNode('');
      if (/[=<>+\-]/.test(node.value)) return document.createTextNode(' ' + node.value.replace('-', '−') + ' ');
      return document.createTextNode(node.value);
    }
  }
}

export function renderMath(tex, display = false) {
  const element = document.createElement('span');
  element.className = display ? 'math math-display' : 'math';
  element.title = tex;
  try {
    const tokens = lex(tex.trim());
    const state = {i: 0};
    for (const node of parse(tokens, state, null)) element.append(render(node));
  } catch (_) {
    element.textContent = tex;
  }
  return element;
}
