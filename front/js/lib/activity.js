// Helpers of the group activity page (GET /activity).
import { formatDate } from './format.js';

const localDay = (date) => date.toLocaleDateString('sv-SE'); // 2026-10-03

/** "2026-10-03" -> "Hoy", "Ayer" or the date. */
export function dayLabel(day, now = new Date()) {
  const yesterday = new Date(now);
  yesterday.setDate(yesterday.getDate() - 1);
  if (day === localDay(now)) return 'Hoy';
  if (day === localDay(yesterday)) return 'Ayer';
  return formatDate(day);
}

/** The events (newest first) in runs of the same day: [{ day, events }]. */
export function groupByDay(events) {
  const groups = [];
  for (const event of events) {
    const last = groups.at(-1);
    if (last?.day === event.day) last.events.push(event);
    else groups.push({ day: event.day, events: [event] });
  }
  return groups;
}
