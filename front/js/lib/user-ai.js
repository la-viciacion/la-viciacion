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

/** Who pays for a feature now, in one sentence, from its state ({ available, needs_key, paid_by, mode }). */
export function payerText(state) {
  if (!state.available) return 'Ahora mismo no está disponible.';
  if (state.needs_key) return 'Se paga con tu propia clave: guárdala para poder usarla.';
  if (state.paid_by === 'user') return 'Se paga con tu clave, de tu cuenta de OpenAI.';
  if (state.mode === 'group_only') return 'Lo paga el grupo, tengas clave o no.';
  return 'Lo paga el grupo mientras no guardes tu propia clave; con ella, lo pagas tú.';
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
