// Figures of the server panel (#/server). Pure: no DOM, so it can be tested.

// [what the API is asked for, the button, how many seconds back it goes]
export const WINDOWS = [['1h', '1 hora', 3600], ['24h', '24 horas', 86400], ['7d', '7 días', 7 * 86400], ['30d', '30 días', 30 * 86400]];

// What Hetzner calls each state of a server, how the panel says it and how it is coloured.
const STATUS = {
  running: ['En marcha', 'ok'],
  off: ['Apagado', 'bad'],
  initializing: ['Arrancando', 'warn'],
  starting: ['Arrancando', 'warn'],
  stopping: ['Apagándose', 'warn'],
  migrating: ['Migrando', 'warn'],
  rebuilding: ['Reconstruyéndose', 'warn'],
  deleting: ['Eliminándose', 'bad'],
};

export const statusInfo = (status) => {
  const [label, tone] = STATUS[status] ?? ['Desconocido', 'warn'];
  return { label, tone };
};

const UNITS = ['B', 'KB', 'MB', 'GB', 'TB'];

/** 1536 -> "1,5 KB" (decimal units, the ones Hetzner bills traffic in). */
export function bytes(value) {
  let n = Math.max(value || 0, 0);
  let unit = 0;
  while (n >= 1000 && unit < UNITS.length - 1) { n /= 1000; unit += 1; }
  const digits = unit === 0 || n >= 100 ? 0 : 1;
  return `${n.toLocaleString('es-ES', { maximumFractionDigits: digits })} ${UNITS[unit]}`;
}

/** "2026-03" -> "marzo". */
export const monthName = (month) => new Date(`${month}-01T12:00:00`).toLocaleDateString('es-ES', { month: 'long' });

/** "2023-12-05" -> "diciembre de 2023". */
export const monthYear = (day) => `${monthName(day.slice(0, 7))} de ${day.slice(0, 4)}`;

/** 90061 seconds -> "1 d 1 h"; under an hour, the minutes. */
export function uptime(seconds) {
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  if (days) return `${days} d ${hours} h`;
  return hours ? `${hours} h` : `${Math.floor(seconds / 60)} min`;
}

/** A load average with two decimals: 0.5 -> "0,50". */
export const load = (value) => value.toLocaleString('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** An amount in euros always with its cents, so the figures of a table line up: 2 -> "2,00 €". */
export const money = (amount) => amount.toLocaleString('es-ES', { style: 'currency', currency: 'EUR' });

export const rate = (value) => `${bytes(value)}/s`;

export const percent = (value) => `${(value || 0).toLocaleString('es-ES', { maximumFractionDigits: 1 })} %`;

/** What fraction (0 to 1) of the traffic the plan includes has been used. */
export const trafficShare = (traffic) => (traffic.included ? Math.min(traffic.out / traffic.included, 1) : 0);

export const last = (points) => (points.length ? points[points.length - 1][1] : 0);
export const peak = (points) => points.reduce((max, [, value]) => Math.max(max, value), 0);

/**
 * The `points` attribute of a polyline for `[[time, value], ...]`, in a box of `width` x `height` where `max` is the top
 * (a flat zero line stays at the bottom). '' with fewer than two points: there is no line to draw.
 */
export function linePoints(points, { width = 300, height = 80, max, from, to }) {
  if (points.length < 2) return '';
  const start = from ?? points[0][0];
  const span = (to ?? points[points.length - 1][0]) - start || 1;
  const top = max || 1;
  return points
    .map(([time, value]) => `${((time - start) / span * width).toFixed(1)},${(height - Math.min(value / top, 1) * height).toFixed(1)}`)
    .join(' ');
}

/** The top of a chart that shows several series at once: the highest value of all, never less than 1. */
export const sharedMax = (...series) => Math.max(1, ...series.map(peak));
