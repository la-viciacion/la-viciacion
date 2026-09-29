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

/** Runs in the admin panel state: users (for selects) loaded once at start. */
export const store = { users: [] };
