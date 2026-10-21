// The chat's pure logic: what goes to the API and how an answer is split for display. The widget is ui/chat.js.

export const MAX_TURNS = 10; // the API keeps the last 10 messages of the history (api/src/chat/agent.py MAX_HISTORY)
export const MAX_QUESTION = 500;
const MAX_TURN_TEXT = 2000;

export const SUGGESTIONS = [
  '¿Quién lleva más horas este año?',
  '¿Qué juegos de terror tenemos?',
  '¿Cuál es mi racha actual?',
  '¿A qué estoy esperando que salga?',
];

/** The body of POST /chat: the question and the last turns before it. A turn that failed never got an answer, so it
 * is left out; the history starts with a question (a provider may refuse one that starts with an answer). */
export function toRequest(turns, text) {
  const history = turns
    .filter((t) => !t.failed && (t.role === 'user' || t.role === 'assistant'))
    .slice(-MAX_TURNS);
  while (history.length && history[0].role !== 'user') history.shift();
  return {
    message: text.trim().slice(0, MAX_QUESTION),
    history: history.map((t) => ({ role: t.role, content: t.content.slice(0, MAX_TURN_TEXT) })),
  };
}

// **bold** inside a line; everything else is plain text (it is escaped when rendered)
function inline(line) {
  return line.split(/(\*\*[^*]+\*\*)/).filter(Boolean).map((part) => (
    part.startsWith('**') && part.endsWith('**') && part.length > 4 ? { bold: true, text: part.slice(2, -2) } : { text: part }
  ));
}

const BULLET = /^\s*(?:[-*•]|\d+[.)])\s+(.*)$/;

/** An answer as blocks: [{ type: 'p', parts }, { type: 'ul', items: [parts] }]. The model writes a little Markdown
 * (bold, lists); nothing else is interpreted, and the text is never turned into markup. */
export function parseAnswer(text) {
  const blocks = [];
  for (const line of String(text ?? '').split('\n')) {
    if (!line.trim()) continue;
    const bullet = line.match(BULLET);
    if (bullet) {
      const last = blocks[blocks.length - 1];
      if (last?.type === 'ul') last.items.push(inline(bullet[1]));
      else blocks.push({ type: 'ul', items: [inline(bullet[1])] });
    } else {
      blocks.push({ type: 'p', parts: inline(line.trim()) });
    }
  }
  return blocks;
}
