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

// Where the cost of a feature goes for this player: the group's key comes first, while its monthly budget lasts, and the player's
// own is what goes on after it (or the only one: the guide, by default). `fallback` is a question already going on with the
// player's own key because the group's budget is spent.
function kindOf(feature) {
  if (feature.paid_by === 'user') return feature.blocked ? 'fallback' : 'own';
  if (feature.paid_by === 'group') return feature.mode === 'group_only' ? 'group_only' : 'group';
  return 'needs';
}

/** A short, quiet note on where the cost of the chat and the guide goes, from their states ({ available, needs_key, paid_by, mode,
 * blocked }) and whether the player has a key of their own: it says what is true for this player now and nothing more. */
export function costNote({ chat, guide, key }) {
  const hasKey = Boolean(key?.has_key);
  const features = [
    { feature: chat, of: 'del chat', is: 'el chat', cap: 'El chat' },
    { feature: guide, of: 'de la guía', is: 'la guía', cap: 'La guía' },
  ];
  const notes = features.filter((f) => !f.feature.available).map((f) => `${f.cap}${f.is === 'la guía' ? ' de cada juego' : ''} no está disponible ahora mismo.`);
  const byKind = {};
  for (const f of features.filter((x) => x.feature.available)) (byKind[kindOf(f.feature)] ??= []).push(f);
  const subject = (list) => [list[0].cap, ...list.slice(1).map((f) => f.is)].join(' y '); // 'El chat y la guía'
  const after = hasKey ? 'después seguirá con tu clave, a tu cuenta de OpenAI' : 'después necesitarás tu propia clave';
  for (const [kind, list] of Object.entries(byKind)) {
    const of = list.map((f) => f.of).join(' y ');
    if (kind === 'group_only') notes.push(`El coste ${of} lo cubre el grupo, tengas clave o no.`);
    else if (kind === 'group') notes.push(`El coste ${of} lo cubre el grupo mientras haya presupuesto este mes; ${after}.`);
    else if (kind === 'own') notes.push(`El coste ${of} va a tu cuenta de OpenAI.`);
    else if (kind === 'fallback') notes.push(`Se ha agotado el presupuesto del grupo este mes: de momento el coste ${of} va a tu cuenta de OpenAI.`);
    else if (list.length === 1 && list[0].is === 'la guía') notes.push('La guía de cada juego busca en internet y cuesta más: funciona con tu propia clave.');
    else notes.push(`${subject(list)} ${list.length > 1 ? 'funcionan' : 'funciona'} con tu propia clave.`);
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
  if (state.paid_by === 'user') return null; // the player's own key took over: the note above says so
  if (state.blocked === 'group') return 'Se ha agotado el presupuesto de IA del grupo este mes.';
  if (state.blocked === 'user') return 'Has gastado tu parte del presupuesto de IA del grupo este mes.';
  return null;
}

/** The key as the player sees it: the last characters, never the key. */
export const keyText = (status) => `Clave guardada, termina en …${status.hint}`;

/** The key field's value looks like an OpenAI key (the API checks it for real with OpenAI). */
export const looksLikeKey = (value) => /^sk-[A-Za-z0-9_-]{16,}$/.test(String(value).trim());
