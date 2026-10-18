// The first days of a month, when the recap of the month that ended is offered: a notice on opening the app and a card in the
// profile. Pure apart from the storage of what this device has already shown.
import { lastMonth } from './recap.js';

/** How many days at the start of a month the recap is offered (the 1st to the 5th). */
export const WINDOW_DAYS = 5;

/** The period on offer today ("2026-09" on 3 October), or null outside the first days of the month. */
export const windowPeriod = (now = new Date()) => (now.getDate() <= WINDOW_DAYS ? lastMonth(now) : null);

const key = (period) => `lv-recap-seen-${period}`;

/** Has this device already shown the notice of the period (opened or closed)? A browser without storage says no. */
export function hasSeen(period) {
  try { return localStorage.getItem(key(period)) === '1'; } catch { return false; }
}

export function markSeen(period) {
  try { localStorage.setItem(key(period), '1'); } catch { /* private mode: it will be offered again on the next visit */ }
}
