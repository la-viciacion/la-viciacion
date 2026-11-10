// The preview of a notice written in the admin panel's "Redactar aviso": the small Markdown subset that
// api/src/utils/announcement_text.py draws for Telegram (headings, **bold**, *italic*, ~~struck~~, `code`, code blocks,
// [links](https://…), bullets, numbered items, quotes and ---). Pure: it returns blocks, the page draws them with
// html``, so whatever is typed stays text. The API is the one that decides what Telegram receives; this is only a preview.

export const BODY_MAX = 3000; // what the API accepts for a Telegram notice
export const MESSAGE_MAX = 4000; // of the drawn text, title included (Telegram allows 4096)
const BULLETS = ['•', '◦', '▪'];
const RULE_LINE = '──────────';

const INLINE = [
  ['code', /`([^`\n]+)`/],
  ['link', /\[([^\]\n]+)\]\(([^)\s]+)\)/],
  ['b', /(\*\*|__)(?=\S)(.+?)(?<=\S)\1/],
  ['s', /~~(?=\S)(.+?)(?<=\S)~~/],
  ['i', /(?<![*\w])\*(?=[^\s*])(.+?)(?<=[^\s*])\*(?![*\w])/],
  ['i', /(?<![_\w])_(?=[^\s_])(.+?)(?<=[^\s_])_(?![_\w])/],
];

const isHttp = (url) => /^https?:\/\//i.test(url);

/** One line as pieces: [{ text, style?: 'b' | 'i' | 's' | 'code', href? }]. */
export function inline(text) {
  const pieces = [];
  let rest = text;
  while (rest) {
    let best = null;
    for (const [kind, pattern] of INLINE) {
      const match = pattern.exec(rest);
      if (match && (!best || match.index < best.match.index)) best = { kind, match };
    }
    if (!best) break;
    const { kind, match } = best;
    if (match.index) pieces.push({ text: rest.slice(0, match.index) });
    if (kind === 'code') pieces.push({ text: match[1], style: 'code' });
    else if (kind === 'link') pieces.push(isHttp(match[2]) ? { text: match[1], href: match[2] } : { text: match[1] });
    else pieces.push(...inline(match[kind === 'b' ? 2 : 1]).map((p) => ({ ...p, style: p.style ?? kind })));
    rest = rest.slice(match.index + match[0].length);
  }
  if (rest) pieces.push({ text: rest });
  return pieces;
}

const indentLevel = (indent, max) => Math.min(Math.floor(indent.replace(/\t/g, '  ').length / 2), max);

/** The text as blocks: { type: 'p' | 'heading' | 'item' | 'quote' | 'rule' | 'code' | 'gap', ... }. */
export function blocks(markdown) {
  const out = [];
  const quote = [];
  let code = null;
  const flushQuote = () => {
    if (quote.length) out.push({ type: 'quote', lines: quote.map(inline) });
    quote.length = 0;
  };
  for (const raw of String(markdown ?? '').replace(/\r\n?/g, '\n').trim().split('\n')) {
    const line = raw.trimEnd();
    if (/^\s*```/.test(line)) {
      flushQuote();
      if (code === null) code = [];
      else {
        out.push({ type: 'code', text: code.join('\n') });
        code = null;
      }
      continue;
    }
    if (code !== null) { code.push(raw); continue; }
    const quoted = /^\s{0,3}>\s?(.*)$/.exec(line);
    if (quoted) { quote.push(quoted[1]); continue; }
    flushQuote();
    let m;
    if (!line.trim()) {
      if (out.length && out[out.length - 1].type !== 'gap') out.push({ type: 'gap' });
    } else if (/^\s{0,3}([-*_])(\s*\1){2,}\s*$/.test(line)) out.push({ type: 'rule' });
    else if ((m = /^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$/.exec(line))) out.push({ type: 'heading', pieces: inline(m[1].replace(/\*\*|__/g, '')) });
    else if ((m = /^(\s*)[-*+]\s+(.*)$/.exec(line))) {
      const level = indentLevel(m[1], BULLETS.length - 1);
      out.push({ type: 'item', level, mark: BULLETS[level], pieces: inline(m[2]) });
    } else if ((m = /^(\s*)(\d{1,3}[.)])\s+(.*)$/.exec(line))) out.push({ type: 'item', level: indentLevel(m[1], 2), mark: m[2], pieces: inline(m[3]) });
    else out.push({ type: 'p', pieces: inline(line.trim()) });
  }
  flushQuote();
  if (code !== null) out.push({ type: 'code', text: code.join('\n') });
  while (out.length && out[out.length - 1].type === 'gap') out.pop();
  return out;
}

const pieceText = (pieces) => pieces.map((p) => p.text).join('');

/** The length the drawn message would have (what Telegram counts), to warn before the API refuses it. */
export function drawnLength(title, markdown) {
  const body = blocks(markdown).map((b) => {
    if (b.type === 'gap') return '';
    if (b.type === 'rule') return RULE_LINE;
    if (b.type === 'code') return b.text;
    if (b.type === 'quote') return b.lines.map(pieceText).join('\n');
    if (b.type === 'item') return `${' '.repeat(b.level)}${b.mark} ${pieceText(b.pieces)}`;
    return pieceText(b.pieces);
  }).join('\n');
  return String(title ?? '').trim().length + 2 + body.length;
}
