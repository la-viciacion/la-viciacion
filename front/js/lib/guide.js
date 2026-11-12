// The game guide's pure logic: the levels of help and what goes to the API. The card is ui/game-guide.js.
import { api } from './api.js';
import { MAX_QUESTION, toRequest } from './chat.js';

// The levels of help, softest first (api/src/guide/prompt.py LEVELS): the guide never goes above the one chosen
export const LEVELS = [
  { id: 'nudge', label: 'Empujón', hint: 'Solo una dirección, sin destripes' },
  { id: 'hint', label: 'Pista', hint: 'Qué hacer, sin el paso a paso' },
  { id: 'solution', label: 'Solución', hint: 'La respuesta completa (con destripes)' },
];
export const DEFAULT_LEVEL = 'nudge';
export { MAX_QUESTION };

const known = (level) => LEVELS.some((l) => l.id === level);

/** The body of POST /guide/{game}: the chat's (question and last turns) plus the level of help; an unknown level is the softest. */
export function toGuideRequest(turns, text, level) {
  return { ...toRequest(turns, text), level: known(level) ? level : DEFAULT_LEVEL };
}

// The conversations of this visit, by game: leaving the page and coming back keeps them, a reload or logout forgets them
// (the API stores nothing of them while the guide is on trial)
const conversations = new Map();

export function conversationOf(gameId) {
  if (!conversations.has(gameId)) conversations.set(gameId, { turns: [], level: DEFAULT_LEVEL });
  return conversations.get(gameId);
}

const OFF = { available: false, needs_key: false, paid_by: null };
let status = null;

/** What the API says the guide is for this player ({ available, needs_key, paid_by }), asked once per visit (a failure is
 * "off" and is asked again next time). `needs_key`: the group does not cover it, the player has to save their own key. */
export function guideStatus() {
  status ??= api('/guide/status').then((found) => ({
    available: Boolean(found?.available), needs_key: Boolean(found?.needs_key), paid_by: found?.paid_by ?? null,
  }), () => {
    status = null; // optional: a failure here must never show on a page
    return OFF;
  });
  return status;
}

/** Whether the player can ask the guide right now (it is on and somebody pays for it). */
export async function guideAvailable() {
  const found = await guideStatus();
  return found.available && !found.needs_key;
}

/** Asks again next time: the player saved or removed their own key, which changes who pays. */
export function forgetGuideStatus() {
  status = null;
}

/** What this visit knows about the guide, at the end of the session. */
export function forgetConversations() {
  conversations.clear();
  status = null;
}
