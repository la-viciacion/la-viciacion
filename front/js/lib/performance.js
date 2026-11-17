// Figures of the admin's performance page (GET /manage/performance). Pure: no DOM, so it can be tested.
import { bytes } from './server.js';

const decimal = (value, digits) => value.toLocaleString('es-ES', { minimumFractionDigits: digits, maximumFractionDigits: digits });

/** A time of answer: milliseconds below a second, seconds above; a dash when the window has no number. */
export function duration(seconds) {
  if (seconds === null || seconds === undefined) return '—';
  if (seconds < 0.01) return '<10 ms';
  if (seconds < 1) return `${Math.round(seconds * 1000)} ms`;
  return `${decimal(seconds, seconds < 10 ? 2 : 1)} s`;
}

/** A count of requests: thousands apart, a dash when there is none recorded. */
export const count = (value) => (value === null || value === undefined ? '—' : value.toLocaleString('es-ES'));

/** Requests per minute, with a decimal only when it is small. */
export const perMinute = (value) => `${decimal(value, value < 10 ? 1 : 0)}/min`;

/** The share of requests that failed with a 5xx, as a percentage, or a dash when there were no requests. */
export function errorRate(requests, errors) {
  if (!requests) return '—';
  const share = (errors / requests) * 100;
  return `${decimal(share, share > 0 && share < 1 ? 2 : 1)} %`;
}

export const memory = (value) => (value === null || value === undefined ? '—' : bytes(value));

/** Just the part of the route after `/api/v1`, so a table of routes is not full of the same prefix. */
export const shortRoute = (route) => route.replace(/^\/api\/v1/, '') || '/';
