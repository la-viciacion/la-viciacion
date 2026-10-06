// Small building blocks shared by the admin panel modules.
import { html } from '../../lib/html.js';

export const badge = (text, color) => html`<span class="adm-badge ${color}">${text}</span>`;

export const statTile = (label, value) => html`
  <div class="adm-stat"><div class="adm-stat-v">${value}</div><div class="adm-stat-l">${label}</div></div>`;

export const overviewStats = (ov) => [
  statTile('Usuarios', ov.users),
  statTile('Juegos', ov.games),
  statTile('Sesiones', ov.timers),
  statTile('Timers activos', ov.active_timers),
  statTile('Biblioteca', ov.library),
];

export const errorState = (message) => html`<div class="empty-state"><span>⚠️</span>${message}</div>`;

/** Seasons the panel offers (the app began recording in 2023), the running one first. */
export const FIRST_SEASON = 2023;
export const seasonYears = () => Array.from({ length: new Date().getFullYear() - FIRST_SEASON + 1 }, (_, i) => new Date().getFullYear() - i);

/** Runs in the admin panel state: users (for selects) loaded once at start. */
export const store = { users: [], achievements: [], me: null };
