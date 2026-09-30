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

/** "2026-09-29" (a calendar day, no timezone) -> local Date at midnight. */
export function parseDay(value) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(value));
  return m ? new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3])) : new Date(value);
}

export function formatDate(value) {
  return value ? parseDay(value).toLocaleDateString(LOCALE, { day: 'numeric', month: 'short', year: 'numeric' }) : '—';
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

/** Date or "2026-09-29T13:05:07" -> "2026-09-29T13:05" (value of a datetime-local input). */
export function toInputValue(value) {
  return toLocalISO(value instanceof Date ? value : new Date(value)).slice(0, 16);
}

/** "2026-09-29T13:05" (datetime-local input) -> "2026-09-29T13:05:00" (what the API expects). */
export const fromInputValue = (value) => (value.length === 16 ? `${value}:00` : value);

/** ["Ana", "Bob", "Cris", "Dan", "Eva"] -> "Ana, Bob, Cris y 2 más" (at most three names). */
export function formatPlayers(names, shown = 3) {
  if (names.length <= shown) {
    return names.length > 1 ? `${names.slice(0, -1).join(', ')} y ${names.at(-1)}` : names.join('');
  }
  return `${names.slice(0, shown).join(', ')} y ${names.length - shown} más`;
}
