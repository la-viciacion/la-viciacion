// The chat's pure logic: what goes to the API and how an answer is split for display. The widget is ui/chat.js.

export const MAX_TURNS = 10; // the API keeps the last 10 messages of the history (api/src/chat/agent.py MAX_HISTORY)
export const MAX_QUESTION = 500;
const MAX_TURN_TEXT = 2000;

// Questions the chat's tools can answer (api/src/chat/tools.py): the group's rankings and activity, one's own figures, the
// wishlist, the catalog and how the app and the chat work. A few of them are offered each time a conversation starts (pickSuggestions), so the list can be
// long: it is how people find out what to ask. Keep each one a question of the user's own words and under MAX_QUESTION,
// and one that one or two calls of the tools answer: a question that needs a call per player, or that leaves the model
// to decide what to look at, can run out of the limits of a question (api/src/chat/agent.py LIMITS).
export const SUGGESTION_COUNT = 3;
export const SUGGESTIONS = [
  // the group's rankings
  '¿Quién lleva más horas este año?',
  '¿Quién ha jugado más horas en total?',
  '¿Cuál es el top 5 de jugadores por horas?',
  '¿Quién tiene la mejor racha de días seguidos?',
  '¿Quién tiene ahora mismo la racha más larga?',
  '¿Quién ha jugado más días distintos este año?',
  '¿Quién ha completado más juegos este año?',
  '¿Quién ha desbloqueado más logros este año?',
  '¿Quién ha jugado a más juegos distintos este año?',
  '¿Quién tiene mejor proporción de juegos completados?',
  '¿Quién ganó el ranking de horas el año pasado?',
  '¿Quién desbloqueó más logros el año pasado?',
  // the group's games
  '¿Cuáles son los juegos más jugados del grupo este año?',
  '¿Cuáles son los juegos más jugados de toda la historia?',
  // what is happening
  '¿Alguien está jugando ahora mismo?',
  '¿Qué ha estado jugando el grupo últimamente?',
  '¿Quién ha jugado más recientemente?',
  '¿Qué juegos se han completado en los últimos días?',
  '¿Qué logros se han desbloqueado últimamente?',
  '¿Cuántos jugadores somos y cuántas horas llevamos entre todos?',
  // about the user
  '¿Cuál es mi racha actual?',
  '¿Cuál es mi mejor racha de siempre?',
  '¿Cuántas horas llevo este año?',
  '¿Cuántas horas he jugado en total?',
  '¿Cuáles son mis juegos más jugados?',
  '¿Cuántos juegos he completado este año?',
  '¿Cuántos logros tengo?',
  '¿Qué logros he conseguido últimamente?',
  '¿En qué puesto voy en horas este año?',
  '¿Cuánto me falta para alcanzar al primero en horas?',
  '¿Con quién tengo más afinidad de gustos?',
  // about the app and the chat itself
  '¿Cómo funcionan las temporadas?',
  '¿Cómo se cuentan los días de la racha?',
  '¿Cómo registro una sesión que se me olvidó?',
  '¿Cómo funcionan los retos?',
  '¿Cómo recibo los avisos en el móvil?',
  '¿Quién puede ver mis datos?',
  '¿Cómo puedo exportar mis datos?',
  '¿Qué logros me faltan por conseguir?',
  '¿Cuántas preguntas me quedan en el chat?',
  '¿Qué límites tiene el chat?',
  // the wishlist
  '¿Qué juegos tengo en mi lista de deseados?',
  '¿A qué estoy esperando que salga?',
  '¿Cuándo sale el próximo juego de mi lista de deseados?',
  '¿Para qué sirve la lista de deseados?',
  '¿Alguien más del grupo quiere los mismos juegos que yo?',
  // the catalog
  '¿Qué juegos de terror tenemos?',
  '¿Qué juegos de rol hay en el catálogo?',
  '¿Qué juegos de plataformas tenemos?',
  '¿Qué juegos cooperativos hay?',
  '¿Qué juegos de mundo abierto tenemos?',
  '¿Qué juegos de carreras hay en el catálogo?',
  '¿Qué juegos de estrategia tenemos?',
  '¿Qué juegos indie hay en el catálogo?',
  '¿Qué juegos de puzles tenemos?',
  '¿Qué juegos de lucha hay?',
];

/** `count` different questions of the list, at random (the list itself is left as it is). */
export function pickSuggestions(count = SUGGESTION_COUNT, random = Math.random) {
  const pool = [...SUGGESTIONS];
  const picked = [];
  while (picked.length < count && pool.length) picked.push(pool.splice(Math.floor(random() * pool.length), 1)[0]);
  return picked;
}

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

// What an answer may carry of Markdown: `code`, **bold**, *italic* inside a line, headings, bulleted and numbered lists.
// Everything else (links, tables, HTML...) stays plain text, and none of it is ever turned into markup: ui/chat.js builds the
// elements from these parts, so what the model writes cannot add a tag, an attribute or a link.
const INLINE = /(`[^`\s](?:[^`]*[^`\s])?`|\*\*[^*]+\*\*|\*[^*\s](?:[^*]*[^*\s])?\*)/;

function token(text) {
  if (text.startsWith('`')) return { code: true, text: text.slice(1, -1) };
  if (text.startsWith('**')) return { bold: true, text: text.slice(2, -2) };
  return { italic: true, text: text.slice(1, -1) };
}

// split() with a group keeps what matched at the odd positions, so a stray asterisk in the plain text is never taken for one
function inline(line) {
  return line.split(INLINE).map((text, i) => (i % 2 ? token(text) : { text })).filter((part) => part.text);
}

const HEADING = /^\s{0,3}#{1,6}\s+(.*)$/;
const BULLET = /^\s*[-*•]\s+(.*)$/;
const NUMBERED = /^\s*\d+[.)]\s+(.*)$/;

/** An answer as blocks: { type: 'p', parts }, { type: 'ul' | 'ol', items: [parts] }; a heading is a paragraph in bold. */
export function parseAnswer(text) {
  const blocks = [];
  const item = (type, parts) => {
    const last = blocks[blocks.length - 1];
    if (last?.type === type) last.items.push(parts);
    else blocks.push({ type, items: [parts] });
  };
  for (const line of String(text ?? '').split('\n')) {
    if (!line.trim()) continue;
    const heading = line.match(HEADING);
    const bullet = line.match(BULLET);
    const numbered = line.match(NUMBERED);
    if (heading) blocks.push({ type: 'p', parts: inline(heading[1].trim()).map((p) => (p.code ? p : { ...p, bold: true })) });
    else if (bullet) item('ul', inline(bullet[1]));
    else if (numbered) item('ol', inline(numbered[1]));
    else blocks.push({ type: 'p', parts: inline(line.trim()) });
  }
  return blocks;
}
