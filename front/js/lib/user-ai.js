// "Mi IA" (profile, Ajustes): the pure part of the player's own AI key screen: who pays for each feature and how a model reads.
// The screen is pages/profile/ai.js. Everything comes from GET /users/{username}/ai and /ai/models.
import { budgetLine } from './ai-budget.js';
import { money } from './ai-usage.js';

export const TIERS = {
  economico: 'económico',
  medio: 'precio medio',
  caro: 'caro',
  sin_precio: 'sin precio conocido',
};

export const FEATURES = [
  ['chat', 'El chat'],
  ['guide', 'La guía de cada juego'],
];

/** What a model reads like in the list: its name, how much it weighs on the account and its price per million tokens. */
export function modelLabel(model) {
  const price = model.output_per_million == null
    ? ''
    : ` · ${money(model.input_per_million)} / ${money(model.output_per_million)} por millón`;
  return `${model.id} · ${TIERS[model.tier] ?? TIERS.sin_precio}${price}`;
}

/** A short, quiet note on where the cost of the chat and the guide goes, from their states ({ available, needs_key, paid_by, mode }):
 * it says what is true for this player now and nothing more. */
export function costNote({ chat, guide }) {
  const notes = [];
  if (!chat.available) notes.push('El chat no está disponible ahora mismo.');
  if (!guide.available) notes.push('La guía de cada juego no está disponible ahora mismo.');
  const features = [chat, guide].filter((f) => f.available);
  if (features.some((f) => f.paid_by === 'user')) {
    notes.push('Con tu clave, el coste de lo que preguntes va a tu cuenta de OpenAI.');
  } else if (chat.available && chat.paid_by === 'group' && guide.available && guide.needs_key) {
    notes.push('El coste del chat lo cubre el grupo. La guía de cada juego busca en internet y cuesta más: funciona con tu propia clave.');
  } else if (features.length && features.every((f) => f.paid_by === 'group')) {
    notes.push(features.every((f) => f.mode === 'group_only') ? 'El coste lo cubre el grupo, tengas clave o no.' : 'El coste lo cubre el grupo; con tu propia clave pasa a tu cuenta.');
  } else if (guide.available && guide.needs_key) {
    notes.push('La guía de cada juego busca en internet y cuesta más: funciona con tu propia clave.');
  }
  return notes.join(' ');
}

/** What the player paid with their own key and what the group's key covered for them, from the usage's `by_source` (dollars). */
export function paidBy(data) {
  const cost = (name) => data.by_source.find((s) => s.name === name)?.cost ?? 0;
  return { own: cost('user'), group: cost('group') };
}

/** The budget lines of the group's key, or none when neither has a cap: what is spent of each and when they start again. */
export function budgetLines(budget) {
  return [budgetLine('Presupuesto del grupo este mes', budget.group, budget.resets_on), budgetLine('Tu parte', budget.user, budget.resets_on)]
    .filter((line, i) => (i === 0 ? budget.group.cap : budget.user.cap) > 0 && line);
}

/** What a feature's state says when the budget stops the group's key from answering this player (else null). */
export function blockedText(state) {
  if (state.blocked === 'group') return 'Se ha agotado el presupuesto de IA del grupo este mes.';
  if (state.blocked === 'user') return 'Has gastado tu parte del presupuesto de IA del grupo este mes.';
  return null;
}

/** The key as the player sees it: the last characters, never the key. */
export const keyText = (status) => `Clave guardada, termina en …${status.hint}`;

/** The key field's value looks like an OpenAI key (the API checks it for real with OpenAI). */
export const looksLikeKey = (value) => /^sk-[A-Za-z0-9_-]{16,}$/.test(String(value).trim());
