// What the app's AI has been used for (admin panel, IA → Uso y coste): the labels and figures of GET /manage/ai-usage/calls.
// Pure, so it can be tested. The cost is an estimate (the token prices of the day of each call), in dollars like OpenAI's.

export const ALL = 'all';

const FEATURES = { chat: 'Chat', guide: 'Guía de juego' };
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

/** The share of the calls with no known price, as a sentence, or null when every call has one. */
export function unpricedNote(total) {
  if (!total.unpriced) return null;
  return `${total.unpriced} ${total.unpriced === 1 ? 'llamada' : 'llamadas'} sin precio conocido para su modelo: no suman al coste.`;
}

/** The price of the average call, or null with no calls. */
export const perCall = (total) => (total.calls ? total.cost / total.calls : null);
