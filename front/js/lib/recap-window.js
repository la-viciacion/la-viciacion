// The first days of a month, when the recap of the month that ended is offered: a notice on opening the app and a card in the
// profile. Pure apart from the storage of what this device has already shown.
import { lastMonth } from './recap.js';

/** How many days at the start of a month the recap is offered (the 1st to the 5th). */
export const WINDOW_DAYS = 5;

/** The periods on offer today, the most special first: the month that ended ("2026-09" on 3 October) and, in January,
 * the season that ended with it ("2026", then "2026-12"). Nothing outside the first days of the month. */
export function windowPeriods(now = new Date()) {
  if (now.getDate() > WINDOW_DAYS) return [];
  const month = lastMonth(now);
  return month.endsWith('-12') ? [month.slice(0, 4), month] : [month];
}

const key = (period) => `lv-recap-seen-${period}`;

/** Has this device already shown the notice of the period (opened or closed)? A browser without storage says no. */
export function hasSeen(period) {
  try { return localStorage.getItem(key(period)) === '1'; } catch { return false; }
}

export function markSeen(period) {
  try { localStorage.setItem(key(period), '1'); } catch { /* private mode: it will be offered again on the next visit */ }
}
