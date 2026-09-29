// Formatting helpers (durations, dates). The API returns naive local
// timestamps (datetime.now() on the server), so they are parsed as local time.

const LOCALE = 'es-ES';
const pad = (n) => String(n).padStart(2, '0');

/** 3725 -> "1 h 2 min" */
export function formatDuration(totalSeconds) {
  const s = Math.max(0, Math.round(totalSeconds || 0));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (h > 0) return m ? `${h} h ${m} min` : `${h} h`;
  if (m > 0) return `${m} min`;
  return `${s} s`;
}

/** 3725 -> "01:02:05" (live timer) */
export function formatClock(totalSeconds) {
  const s = Math.max(0, Math.floor(totalSeconds));
  return `${pad(Math.floor(s / 3600))}:${pad(Math.floor((s % 3600) / 60))}:${pad(s % 60)}`;
}

/** "Hoy", "Ayer", "Hace 3 días" or a short date. */
export function formatRelative(ts, now = new Date()) {
  const d = new Date(ts);
  const startOfDay = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate());
  const days = Math.round((startOfDay(now) - startOfDay(d)) / 86400000);
  if (days <= 0) return 'Hoy';
  if (days === 1) return 'Ayer';
  if (days < 7) return `Hace ${days} días`;
  return d.toLocaleDateString(LOCALE, {
    day: 'numeric',
    month: 'short',
    year: d.getFullYear() === now.getFullYear() ? undefined : 'numeric',
  });
}

export function formatDate(value) {
  return value ? new Date(value).toLocaleDateString(LOCALE, { day: 'numeric', month: 'short', year: 'numeric' }) : '—';
}

export function formatDateTime(ts) {
  return new Date(ts).toLocaleString(LOCALE, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
}

/** "2026-09-29T13:05:07" -> "2026-09-29 13:05" (admin tables) */
export const formatTimestamp = (ts) => (ts ? String(ts).replace('T', ' ').slice(0, 16) : '—');

/** Date -> "2026-09-29T13:05:07" in local time (what the API expects). */
export function toLocalISO(d) {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}
