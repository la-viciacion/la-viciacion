// "Mi IA" (profile, Ajustes): the pure part of the player's own AI key screen: who pays for each feature and how a model reads.
// The screen is pages/profile/ai.js. Everything comes from GET /users/{username}/ai and /ai/models.
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

/** The key as the player sees it: the last characters, never the key. */
export const keyText = (status) => `Clave guardada, termina en …${status.hint}`;

/** The key field's value looks like an OpenAI key (the API checks it for real with OpenAI). */
export const looksLikeKey = (value) => /^sk-[A-Za-z0-9_-]{16,}$/.test(String(value).trim());
