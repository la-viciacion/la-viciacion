// Declarative description of every admin tab. The generic controller in
// index.js renders the toolbar, table, pager, forms and delete flow from this.
//
// Entity: { label, endpoint, search?, filters?, columns, fields, createFields?,
//           createLabel?, name(row), actions?, toolbarActions?, canDelete, deleteLabel?, deleteNote?,
//           selects?, defaultSort? }
// Column: { label, render(row) -> html``, filter?(row) -> filters to apply on click, sort? (API sort key) }
// Select: { key, label, options: [[value, label], ...] | () => [...] }   sent to the API as ?key=value
// Action: { label, show?(row), run(row, admin) }   admin = { jumpTo, reload }
import { formatDuration, formatTimestamp } from '../../lib/format.js';
import { html } from '../../lib/html.js';
import { platformList, platformName } from '../../lib/platforms.js';
import { badge, store } from './components.js';
import { closeTimerNow, uploadAchievementImage } from './dialogs.js';

const platformField = { key: 'platform', label: 'Plataforma', type: 'platform' };
const duration = (sec) => (sec == null ? '—' : formatDuration(sec));
const platform = (id) => platformName(id) || '—';

// Filters shared by the tables that have seasons / platforms (options are read when the toolbar is drawn)
const firstSeason = 2023;
const seasonSelect = {
  key: 'season',
  label: 'Temporada',
  options: () => [['', 'Temporada: todas'], ...Array.from({ length: new Date().getFullYear() - firstSeason + 1 }, (_, i) => String(new Date().getFullYear() - i)).map((y) => [y, y])],
};
const platformSelect = { key: 'platform', label: 'Plataforma', options: () => [['', 'Plataforma: todas'], ...platformList().map((p) => [p.id, p.name])] };

const userColumn = { label: 'Usuario', sort: 'user', render: (r) => r.user || r.user_id, filter: (r) => ({ user_id: r.user_id }) };
const gameColumn = { label: 'Juego', sort: 'game', render: (r) => r.game || r.game_id, filter: (r) => ({ game_id: r.game_id, game_name: r.game }) };

export const ENTITIES = {
  users: {
    label: 'Usuarios',
    endpoint: '/manage/users',
    search: true,
    columns: [
      { label: 'Usuario', render: (r) => html`<strong>${r.username}</strong><div class="adm-sub">${r.name || ''}</div>` },
      { label: 'Email', render: (r) => r.email || '—' },
      { label: 'Telegram', render: (r) => r.telegram_id ?? '—' },
      { label: 'Sesiones', render: (r) => r.sessions },
      { label: 'Biblioteca', render: (r) => r.library },
      { label: 'Estado', render: (r) => html`${r.is_admin ? badge('Admin', 'purple') : ''}${badge(r.is_active ? 'Activo' : 'Inactivo', r.is_active ? 'green' : 'red')}` },
    ],
    fields: [
      { key: 'email', label: 'Email (inicio de sesión)', type: 'text' },
      { key: 'username', label: 'Usuario (apodo)', type: 'text', required: true },
      { key: 'name', label: 'Nombre', type: 'text' },
      { key: 'telegram_id', label: 'Telegram ID (el bot lo usa para escribirle)', type: 'number' },
      { key: 'is_admin', label: 'Administrador', type: 'checkbox' },
      { key: 'is_active', label: 'Activo', type: 'checkbox' },
      { key: 'new_password', label: 'Nueva contraseña (dejar vacío para no cambiarla)', type: 'password' },
    ],
    createFields: [
      { key: 'email', label: 'Email (inicio de sesión)', type: 'text', required: true },
      { key: 'username', label: 'Usuario (apodo)', type: 'text', required: true },
      { key: 'name', label: 'Nombre', type: 'text' },
      { key: 'telegram_id', label: 'Telegram ID (opcional)', type: 'number' },
      { key: 'password', label: 'Contraseña (compártela con el usuario)', type: 'password', required: true },
      { key: 'is_admin', label: 'Administrador', type: 'checkbox' },
      { key: 'is_active', label: 'Activo', type: 'checkbox', default: true },
    ],
    createLabel: 'Nuevo usuario',
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
    defaultSort: { key: 'name', dir: 'asc' },
    selects: [
      { key: 'usage', label: 'Uso', options: [['', 'Uso: todos'], ['used', 'Con sesiones o jugadores'], ['unused', 'Sin uso']] },
      { key: 'rawg', label: 'RAWG', options: [['', 'RAWG: todos'], ['linked', 'Enlazados a RAWG'], ['unlinked', 'Sin enlazar']] },
    ],
    columns: [
      {
        label: 'Juego',
        sort: 'name',
        render: (r) => html`<div class="adm-game">
          ${r.image_url ? html`<img src="${r.image_url}" alt="" loading="lazy" />` : html`<span>🎮</span>`}
          <div><strong>${r.name}</strong><div class="adm-sub">${r.dev || ''}</div></div>
        </div>`,
      },
      { label: 'Géneros', render: (r) => r.genres || '—' },
      { label: 'Lanzamiento', sort: 'release_date', render: (r) => r.release_date || '—' },
      { label: 'Sesiones', sort: 'sessions', render: (r) => r.sessions },
      { label: 'Jugadores', sort: 'players', render: (r) => r.players },
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
    ],
    toolbarActions: [{ act: 'rawg-sync', label: 'Sincronizar con RAWG…' }],
    canDelete: true,
    deleteNote: 'Se borrarán también sus sesiones, entradas de biblioteca y logros.',
  },

  timers: {
    label: 'Sesiones',
    endpoint: '/manage/timers',
    filters: ['user', 'game', 'active'],
    selects: [seasonSelect, platformSelect],
    defaultSort: { key: 'start', dir: 'desc' },
    columns: [
      userColumn,
      gameColumn,
      { label: 'Inicio', sort: 'start', render: (r) => formatTimestamp(r.start_time) },
      { label: 'Fin', sort: 'end', render: (r) => (r.is_active ? badge('En curso', 'orange') : formatTimestamp(r.end_time)) },
      { label: 'Duración', sort: 'duration', render: (r) => duration(r.duration_seconds) },
      { label: 'Plataforma', sort: 'platform', render: (r) => platform(r.platform) },
      { label: 'Temp.', sort: 'season', render: (r) => r.season ?? '—' },
    ],
    fields: [
      { key: 'start_time', label: 'Inicio', type: 'datetime', required: true },
      { key: 'end_time', label: 'Fin', type: 'datetime', omitEmpty: true },
      platformField,
      { key: 'notes', label: 'Notas', type: 'text' },
    ],
    createFields: [
      { key: 'user_id', label: 'Usuario', type: 'user', required: true },
      { key: 'game_id', label: 'Juego', type: 'game', required: true },
      { key: 'start_time', label: 'Inicio', type: 'datetime', required: true },
      { key: 'end_time', label: 'Fin', type: 'datetime', required: true },
      platformField,
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
    selects: [
      seasonSelect,
      platformSelect,
      { key: 'completed', label: 'Completado', options: [['', 'Completado: todos'], ['yes', 'Completados'], ['no', 'Sin completar']] },
    ],
    defaultSort: { key: 'season', dir: 'desc' },
    columns: [
      userColumn,
      gameColumn,
      { label: 'Plataforma', sort: 'platform', render: (r) => platform(r.platform) },
      { label: 'Temp.', sort: 'season', render: (r) => r.season ?? '—' },
      { label: 'Inicio', sort: 'started', render: (r) => r.started_date || '—' },
      { label: 'Completado', sort: 'completed', render: (r) => (r.completed ? badge(`Sí ${r.completed_date || ''}`, 'green') : badge('No', 'gray')) },
      { label: 'Nota', sort: 'score', render: (r) => (r.score != null ? r.score : '—') },
    ],
    fields: [
      platformField,
      { key: 'started_date', label: 'Fecha de inicio (su año es la temporada)', type: 'date', required: true },
      { key: 'completed', label: 'Completado', type: 'checkbox' },
      { key: 'completed_date', label: 'Fecha de completado', type: 'date' },
      { key: 'score', label: 'Nota (0-10)', type: 'number', step: '0.1' },
    ],
    createFields: [
      { key: 'user_id', label: 'Usuario', type: 'user', required: true },
      { key: 'game_id', label: 'Juego', type: 'game', required: true },
      platformField,
      { key: 'started_date', label: 'Fecha de inicio (vacío = hoy; su año es la temporada)', type: 'date' },
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

ENTITIES.awards = {
  label: 'Logros concedidos',
  endpoint: '/manage/user-achievements',
  filters: ['user', 'game'],
  selects: [
    { key: 'achievement_id', label: 'Logro', options: () => [['', 'Logro: todos'], ...store.achievements.map((a) => [String(a.id), a.title])] },
    seasonSelect,
  ],
  defaultSort: { key: 'date', dir: 'desc' },
  columns: [
    userColumn,
    { label: 'Logro', sort: 'achievement', render: (r) => html`<strong>${r.title || r.key}</strong><div class="adm-sub">${r.key || ''}</div>` },
    { label: 'Juego', sort: 'game', render: (r) => r.game || r.game_id || '—', filter: (r) => (r.game_id ? { game_id: r.game_id, game_name: r.game } : {}) },
    { label: 'Fecha', sort: 'date', render: (r) => r.date },
    { label: 'Temp.', sort: 'season', render: (r) => r.season ?? '—' },
  ],
  fields: [{ key: 'date', label: 'Fecha en la que se obtuvo (su año es la temporada)', type: 'date', required: true }],
  name: (r) => `${r.user || r.user_id} · ${r.title || r.key}`,
  canDelete: true,
  deleteLabel: 'Revocar',
  deleteNote: 'El logro se revoca sin avisar por Telegram. Si el jugador sigue cumpliendo la condición, el próximo recálculo (o el de las 05:00) lo volverá a conceder: corrige antes los datos que lo provocaron.',
};

// Not tables: custom panels, each one a module exporting render(panel) (settings.js, announce.js)
ENTITIES.settings = { label: 'Notificaciones', custom: 'settings' };
ENTITIES.announce = { label: 'Avisos', custom: 'announce' };

export const TABS = Object.keys(ENTITIES);
