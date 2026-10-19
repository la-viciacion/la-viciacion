// The recap (#/recap): which periods exist, how they are named and addressed. Pure: no DOM, so it can be tested.
// A period is a month ("2026-09") or a season ("2026"), as GET /statistics/recap/{period} expects.
import { FIRST } from './seasons.js';

const MONTHS = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];

const pad = (n) => String(n).padStart(2, '0');

/** The month of a date as a period key: 2026-09-14 -> "2026-09". */
export const monthKey = (date) => `${date.getFullYear()}-${pad(date.getMonth() + 1)}`;

/** The month that has just ended: where the recap opens by default. */
export const lastMonth = (now = new Date()) => monthKey(new Date(now.getFullYear(), now.getMonth() - 1, 1));

export const isMonth = (period) => /^\d{4}-\d{2}$/.test(period);

/** "2026-09" -> "septiembre de 2026"; "2026" -> "temporada 2026". */
export function periodLabel(period) {
  if (isMonth(period)) return `${MONTHS[Number(period.slice(5)) - 1]} de ${period.slice(0, 4)}`;
  return `temporada ${period}`;
}

/** What the selector offers: the months from the running one back to the first season, then the seasons. */
export function periodChoices(now = new Date()) {
  const months = [];
  for (let date = new Date(now.getFullYear(), now.getMonth(), 1); date.getFullYear() >= FIRST; date = new Date(date.getFullYear(), date.getMonth() - 1, 1)) {
    months.push({ value: monthKey(date), label: periodLabel(monthKey(date)) });
  }
  const seasons = [];
  for (let year = now.getFullYear(); year >= FIRST; year -= 1) seasons.push({ value: String(year), label: `Temporada ${year}` });
  return { months, seasons };
}

/** The address of a recap; an admin can look at another player's with `username`. */
export const recapHref = (period, username) => `#/recap/${period}${username ? `/${encodeURIComponent(username)}` : ''}`;

/** What an address asks for: { period, username }; the period is null when it names none (or a wrong one). */
export function parseHash(hash) {
  const match = /^#\/recap(?:\/(\d{4}(?:-(?:0[1-9]|1[0-2]))?)(?:\/([^/]+))?)?\/?$/.exec(hash || '');
  return { period: match?.[1] ?? null, username: match?.[2] ? decodeURIComponent(match[2]) : null };
}

/** The period before: "2026-01" -> "2025-12", "2026" -> "2025". */
export function previousPeriod(period) {
  if (!isMonth(period)) return String(Number(period) - 1);
  return monthKey(new Date(Number(period.slice(0, 4)), Number(period.slice(5)) - 2, 1));
}

/** How a figure moved against the period before: { text: "+2 h 10 min", trend: "up" | "down" | "same" }. */
export function change(now, before, render) {
  const difference = Math.round(now) - Math.round(before);
  if (difference === 0) return { text: 'igual', trend: 'same' };
  return { text: `${difference > 0 ? '+' : '−'}${render(Math.abs(difference))}`, trend: difference > 0 ? 'up' : 'down' };
}

// ── choosing a period without one long list: monthly or annual, a year and, for a month, the month ──

/** "2026-09" -> { kind: "month", year: 2026, month: 9 }; "2026" -> { kind: "year", year: 2026, month: null }. */
export function pickOf(period) {
  return isMonth(period)
    ? { kind: 'month', year: Number(period.slice(0, 4)), month: Number(period.slice(5)) }
    : { kind: 'year', year: Number(period), month: null };
}

/** The period of a choice: the inverse of pickOf. */
export const periodKey = ({ kind, year, month }) => (kind === 'year' ? String(year) : `${year}-${pad(month)}`);

/** The years on offer, the running one first, down to the first season. */
export function yearChoices(now = new Date()) {
  return Array.from({ length: now.getFullYear() - FIRST + 1 }, (_, i) => now.getFullYear() - i);
}

/** The months of a year as { value (1-12), label }: all of them, or up to the running month in the running year (nothing is there to see after it). */
export function monthChoices(year, now = new Date()) {
  const last = year === now.getFullYear() ? now.getMonth() + 1 : 12;
  return MONTHS.slice(0, last).map((label, i) => ({ value: i + 1, label: label[0].toUpperCase() + label.slice(1) }));
}

/** A choice made valid: a year that is not offered becomes the running one and a month that does not exist yet the last one that does. */
export function clampPick(pick, now = new Date()) {
  const year = Math.min(now.getFullYear(), Math.max(FIRST, pick.year));
  if (pick.kind === 'year') return { kind: 'year', year, month: null };
  const last = monthChoices(year, now).length;
  return { kind: 'month', year, month: Math.min(last, Math.max(1, pick.month ?? last)) };
}

/** The same choice in the other kind: a year stays, a month starts at the last month there is. */
export function withKind(pick, kind, now = new Date()) {
  return clampPick({ kind, year: pick.year, month: kind === 'month' ? pick.month ?? 12 : null }, now);
}
