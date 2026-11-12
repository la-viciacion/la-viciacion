// What the app's AI has been used for (admin panel, IA → Uso y coste): the labels and figures of GET /manage/ai-usage/calls.
// Pure, so it can be tested. The cost is an estimate (the token prices of the day of each call), in dollars like OpenAI's.

export const ALL = 'all';

// the chat and the guide are asked by a player; the welcome and the notices are written by the AI on its own, paid by the group
const FEATURES = { chat: 'Chat', guide: 'Guía de juego', welcome: 'Bienvenida del grupo', notice: 'Avisos con IA', test: 'Pruebas del panel' };
const SOURCES = { group: 'Clave del grupo', user: 'Clave propia de cada jugador' };
const STATUSES = {
  ok: 'Respondidas',
  off_topic: 'Fuera de tema',
  too_big: 'Demasiado grandes',
  quota: 'Sin cupo del proveedor',
  error: 'Con error',
  limited: 'Frenadas por el límite',
  budget: 'Frenadas por el presupuesto',
};

export const featureLabel = (id) => FEATURES[id] ?? id;
export const sourceLabel = (id) => SOURCES[id] ?? id;
export const statusLabel = (id) => STATUSES[id] ?? id;

/** 1234 -> "1.234"; 1_500_000 -> "1,5 M": the tokens of a month are millions. */
export function tokens(value) {
  if (value >= 1_000_000) return `${(value / 1_000_000).toLocaleString('es-ES', { maximumFractionDigits: 1 })} M`;
  return value.toLocaleString('es-ES');
}

/** What to say when some of the calls went to Google and were not marked as made on a free plan, or null when none was: Google has no
 * API for what was spent, so its figure is always the app's estimate, and with a key of the free plan what was really charged is
 * nothing (an admin says so in the settings and the calls from then on count as free). */
export function googleNote(byModel) {
  if (!byModel.some((item) => item.name.startsWith('google/') && item.calls > (item.free_calls ?? 0))) return null;
  return 'Lo de Google es solo una estimación: Google no ofrece su gasto por API. Si la clave es del plan gratuito, márcalo en la tarjeta «Coste de la IA» de abajo: lo que realmente se cobra es 0 US$ aunque aquí salga un coste.';
}

/** What to say when some calls were made on a key of a free plan, or null when none was: their estimate is kept (it helps to know what
 * they would cost) but they really cost nothing. */
export function freeNote(total) {
  if (!total.free_calls) return null;
  return `${total.free_calls} ${total.free_calls === 1 ? 'llamada' : 'llamadas'} con una clave de plan gratuito: se guarda su coste estimado, pero el coste real fue 0 US$.`;
}

/** The share of the calls with no known price, as a sentence, or null when every call has one. */
export function unpricedNote(total) {
  if (!total.unpriced) return null;
  return `${total.unpriced} ${total.unpriced === 1 ? 'llamada' : 'llamadas'} sin precio conocido para su modelo: no suman al coste.`;
}

/** The price of the average call, or null with no calls. */
export const perCall = (total) => (total.calls ? total.cost / total.calls : null);
