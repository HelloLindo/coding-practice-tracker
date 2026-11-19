// Lightweight Python syntax highlighting into DOM spans (no HTML strings).

const KEYWORDS = new Set(('and as assert async await break class continue def del elif else except finally for ' +
  'from global if import in is lambda nonlocal not or pass raise return try while with yield match case').split(' '));
const CONSTANTS = new Set(['True', 'False', 'None', 'Ellipsis', 'NotImplemented']);
const BUILTINS = new Set(('abs all any bin bool bytearray bytes callable chr classmethod dict dir divmod enumerate ' +
  'filter float format frozenset getattr hasattr hash hex id input int isinstance issubclass iter len list map max ' +
  'min next object oct open ord pow print property range repr reversed round set setattr slice sorted staticmethod ' +
  'str sum super tuple type vars zip heapq collections deque defaultdict Counter OrderedDict bisect math functools ' +
  'itertools lru_cache cache inf').split(' '));

const RULES = [
  ['comment', /#[^\n]*/y],
  ['string', /(?:[rRbBuUfF]{1,2})?(?:"""[\s\S]*?(?:"""|$)|'''[\s\S]*?(?:'''|$)|"(?:\\.|[^"\\\n])*(?:"|$)|'(?:\\.|[^'\\\n])*(?:'|$))/y],
  ['number', /(?:0[xX][\da-fA-F_]+|0[oO][0-7_]+|0[bB][01_]+|(?:\d[\d_]*\.?[\d_]*|\.\d[\d_]*)(?:[eE][+-]?\d+)?[jJ]?)(?![\w])/y],
  ['decorator', /@[A-Za-z_][\w.]*/y],
  ['name', /[A-Za-z_][\w]*/y],
];

export function tokens(code) {
  const result = [];
  let index = 0;
  let plain = '';
  let previous = '';
  const flush = () => { if (plain) { result.push(['', plain]); plain = ''; } };
  while (index < code.length) {
    const char = code[index];
    let matched = false;
    if (/[#"'\d.@A-Za-z_]/.test(char)) {
      for (const [kind, rule] of RULES) {
        if (kind === 'number' && /[\w]/.test(code[index - 1] || '')) continue;
        rule.lastIndex = index;
        const match = rule.exec(code);
        if (!match || !match[0]) continue;
        flush();
        let type = kind;
        const word = match[0];
        if (kind === 'name') {
          if (/^[rRbBuUfF]{1,2}$/.test(word) && /["']/.test(code[index + word.length] || '')) continue;
          if (KEYWORDS.has(word)) type = 'keyword';
          else if (CONSTANTS.has(word)) type = 'constant';
          else if (previous === 'def') type = 'function';
          else if (previous === 'class') type = 'class';
          else if (word === 'self' || word === 'cls') type = 'self';
          else if (BUILTINS.has(word)) type = 'builtin';
          else type = '';
          previous = word;
        }
        result.push([type, word]);
        index += word.length;
        matched = true;
        break;
      }
    }
    if (!matched) {
      if (!/\s/.test(char)) previous = '';
      plain += char;
      index += 1;
    }
  }
  flush();
  return result;
}

export function highlightInto(target, code) {
  const fragment = document.createDocumentFragment();
  for (const [type, text] of tokens(code)) {
    if (!type) fragment.append(document.createTextNode(text));
    else {
      const span = document.createElement('span');
      span.className = 'tok-' + type;
      span.textContent = text;
      fragment.append(span);
    }
  }
  target.replaceChildren(fragment);
  return target;
}

export function codeBlock(code, language = 'python') {
  const pre = document.createElement('pre');
  pre.className = 'code-block';
  const element = document.createElement('code');
  if (!language || /^(py|python|python3)$/i.test(language)) highlightInto(element, code);
  else element.textContent = code;
  pre.append(element);
  return pre;
}
