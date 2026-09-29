// Declarative description of every admin tab. The generic controller in
// index.js renders the toolbar, table, pager, forms and delete flow from this.
//
// Entity: { label, endpoint, search?, filters?, columns, fields, createFields?,
//           createLabel?, name(row), actions?, toolbarActions?, canDelete, deleteNote? }
// Column: { label, render(row) -> html``, filter?(row) -> filters to apply on click }
// Action: { label, show?(row), run(row, admin) }   admin = { jumpTo, reload }
import { formatDuration, formatTimestamp } from '../../lib/format.js';
import { html } from '../../lib/html.js';
import { platformName } from '../../lib/platforms.js';
import { badge } from './components.js';
import { closeTimerNow, mergeGames, uploadAchievementImage } from './dialogs.js';

const platformField = { key: 'platform', label: 'Plataforma', type: 'platform' };
const duration = (sec) => (sec == null ? '—' : formatDuration(sec));
const platform = (id) => platformName(id) || '—';

const userColumn = { label: 'Usuario', render: (r) => r.user || r.user_id, filter: (r) => ({ user_id: r.user_id }) };
const gameColumn = { label: 'Juego', render: (r) => r.game || r.game_id, filter: (r) => ({ game_id: r.game_id, game_name: r.game }) };

export const ENTITIES = {
  users: {
    label: 'Usuarios',
    endpoint: '/manage/users',
    search: true,
    columns: [
      { label: 'Usuario', render: (r) => html`<strong>${r.username}</strong><div class="adm-sub">${r.name || ''}</div>` },
      { label: 'Email', render: (r) => r.email || '—' },
      { label: 'Sesiones', render: (r) => r.sessions },
      { label: 'Biblioteca', render: (r) => r.library },
      { label: 'Estado', render: (r) => html`${r.is_admin ? badge('Admin', 'purple') : ''}${badge(r.is_active ? 'Activo' : 'Inactivo', r.is_active ? 'green' : 'red')}` },
    ],
    fields: [
      { key: 'name', label: 'Nombre', type: 'text' },
      { key: 'username', label: 'Usuario', type: 'text', required: true },
      { key: 'email', label: 'Email', type: 'text' },
      { key: 'telegram_id', label: 'Telegram ID', type: 'number' },
      { key: 'is_admin', label: 'Administrador', type: 'checkbox' },
      { key: 'is_active', label: 'Activo', type: 'checkbox' },
      { key: 'new_password', label: 'Nueva contraseña (dejar vacío para no cambiarla)', type: 'password' },
    ],
    name: (r) => r.username,
    actions: [
      { label: 'Sesiones', run: (r, admin) => admin.jumpTo('timers', { user_id: r.id }) },
    ],
    canDelete: true,
    deleteNote: 'Se borrarán también sus sesiones, biblioteca y logros.',
  },

  games: {
    label: 'Juegos',
    endpoint: '/manage/games',
    search: true,
    columns: [
      {
        label: 'Juego',
        render: (r) => html`<div class="adm-game">
          ${r.image_url ? html`<img src="${r.image_url}" alt="" loading="lazy" />` : html`<span>🎮</span>`}
          <div><strong>${r.name}</strong><div class="adm-sub">${r.dev || ''}</div></div>
        </div>`,
      },
      { label: 'Géneros', render: (r) => r.genres || '—' },
      { label: 'Sesiones', render: (r) => r.sessions },
      { label: 'Jugadores', render: (r) => r.players },
    ],
    fields: [
      { key: 'name', label: 'Nombre', type: 'text', required: true },
      { key: 'dev', label: 'Desarrolladora', type: 'text' },
      { key: 'release_date', label: 'Lanzamiento', type: 'date' },
      { key: 'genres', label: 'Géneros (coma)', type: 'text' },
      { key: 'avg_time', label: 'Tiempo medio (s)', type: 'number' },
      { key: 'image_url', label: 'Imagen (URL)', type: 'text' },
      { key: 'steam_id', label: 'Steam ID', type: 'text' },
      { key: 'rawg_id', label: 'RAWG ID', type: 'number' },
      { key: 'slug', label: 'Slug', type: 'text' },
    ],
    name: (r) => r.name,
    actions: [
      { label: 'Sesiones', run: (r, admin) => admin.jumpTo('timers', { game_id: r.id, game_name: r.name }) },
      { label: 'Fusionar…', run: (r, admin) => mergeGames(r, admin) },
    ],
    toolbarActions: [{ act: 'rawg-sync', label: 'Sincronizar con RAWG…' }],
    canDelete: true,
    deleteNote: 'Se borrarán también sus sesiones, entradas de biblioteca y estadísticas.',
  },

  timers: {
    label: 'Sesiones',
    endpoint: '/manage/timers',
    filters: ['user', 'game', 'active'],
    columns: [
      userColumn,
      gameColumn,
      { label: 'Inicio', render: (r) => formatTimestamp(r.start_time) },
      { label: 'Fin', render: (r) => (r.is_active ? badge('En curso', 'orange') : formatTimestamp(r.end_time)) },
      { label: 'Duración', render: (r) => duration(r.duration_seconds) },
      { label: 'Plataforma', render: (r) => platform(r.platform) },
      { label: 'Temp.', render: (r) => r.season ?? '—' },
    ],
    fields: [
      { key: 'start_time', label: 'Inicio', type: 'datetime', required: true },
      { key: 'end_time', label: 'Fin', type: 'datetime', omitEmpty: true },
      platformField,
      { key: 'season', label: 'Temporada', type: 'number' },
      { key: 'notes', label: 'Notas', type: 'text' },
    ],
    createFields: [
      { key: 'user_id', label: 'Usuario', type: 'user', required: true },
      { key: 'game_id', label: 'Juego', type: 'game', required: true },
      { key: 'start_time', label: 'Inicio', type: 'datetime', required: true },
      { key: 'end_time', label: 'Fin', type: 'datetime', required: true },
      platformField,
      { key: 'season', label: 'Temporada (vacío = año del inicio)', type: 'number' },
      { key: 'notes', label: 'Notas', type: 'text' },
    ],
    createLabel: 'Nueva sesión',
    name: (r) => `${r.game || r.game_id} · ${formatTimestamp(r.start_time)}`,
    actions: [
      { label: 'Cerrar ahora', show: (r) => r.is_active, run: (r, admin) => closeTimerNow(r, admin) },
    ],
    canDelete: true,
  },

  library: {
    label: 'Biblioteca',
    endpoint: '/manage/library',
    filters: ['user', 'game'],
    columns: [
      userColumn,
      gameColumn,
      { label: 'Plataforma', render: (r) => platform(r.platform) },
      { label: 'Temp.', render: (r) => r.season ?? '—' },
      { label: 'Inicio', render: (r) => r.started_date || '—' },
      { label: 'Completado', render: (r) => (r.completed ? badge(`Sí ${r.completed_date || ''}`, 'green') : badge('No', 'gray')) },
      { label: 'Nota', render: (r) => (r.score != null ? r.score : '—') },
    ],
    fields: [
      platformField,
      { key: 'season', label: 'Temporada', type: 'number' },
      { key: 'started_date', label: 'Fecha de inicio', type: 'date' },
      { key: 'completed', label: 'Completado', type: 'checkbox' },
      { key: 'completed_date', label: 'Fecha de completado', type: 'date' },
      { key: 'score', label: 'Nota (0-10)', type: 'number', step: '0.1' },
    ],
    createFields: [
      { key: 'user_id', label: 'Usuario', type: 'user', required: true },
      { key: 'game_id', label: 'Juego', type: 'game', required: true },
      platformField,
      { key: 'season', label: 'Temporada (vacío = actual)', type: 'number' },
    ],
    createLabel: 'Nueva entrada',
    name: (r) => `${r.user} · ${r.game}`,
    canDelete: true,
  },

  achievements: {
    label: 'Logros',
    endpoint: '/manage/achievements',
    paged: false,
    columns: [
      { label: 'Imagen', render: (r) => (r.has_image ? html`<img class="adm-ach" src="/api/v1/utils/achievement-image/${r.key}?v=${Date.now()}" alt="" />` : '—') },
      { label: 'Logro', render: (r) => html`<strong>${r.title}</strong><div class="adm-sub">${r.key}</div>` },
      { label: 'Mensaje', render: (r) => r.message || '' },
      { label: 'Concedido', render: (r) => r.awarded },
    ],
    fields: [
      { key: 'title', label: 'Título', type: 'text', required: true },
      { key: 'message', label: 'Mensaje ({} = usuario / juego)', type: 'text' },
    ],
    name: (r) => r.title,
    actions: [{ label: 'Imagen…', run: (r, admin) => uploadAchievementImage(r, admin) }],
    canDelete: false,
  },
};

export const TABS = Object.keys(ENTITIES);
