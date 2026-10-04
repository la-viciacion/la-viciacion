// Declarative description of every admin section (its place in the sidebar is in nav.js). The generic controller in
// index.js renders the toolbar, table, pager, forms and delete flow from this.
//
// Entity: { label, nav? (shorter name for its tab), description? (line under the title), endpoint, search?, filters?, columns, fields, createFields?,
//           createLabel?, name(row), actions?, toolbarActions?, canDelete, deleteLabel?, deleteNote?,
//           selects?, defaultSort? }
//         or a custom page: { label, custom (module in this folder exporting render(panel, { entity, admin })) }
// Column: { label, render(row) -> html``, filter?(row) -> filters to apply on click, sort? (API sort key) }
// Select: { key, label, options: [[value, label], ...] | () => [...] }   sent to the API as ?key=value
// Action: { label, show?(row), run(row, admin) }   admin = { jumpTo, open, reload }
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
    description: 'Cuentas de los jugadores. Las crea un administrador; no hay registro público.',
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
    description: 'Catálogo de juegos compartido por todos. Los metadatos y portadas vienen de RAWG.',
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

  platforms: {
    label: 'Plataformas',
    description: 'Plataformas que se pueden elegir en sesiones y biblioteca.',
    endpoint: '/manage/platforms',
    paged: false,
    columns: [
      { label: 'Plataforma', render: (r) => html`<strong>${r.name}</strong><div class="adm-sub">${r.id}</div>` },
      { label: 'Sesiones', render: (r) => r.sessions },
      { label: 'Biblioteca', render: (r) => r.library },
    ],
    fields: [{ key: 'name', label: 'Nombre', type: 'text', required: true }],
    createFields: [{ key: 'name', label: 'Nombre', type: 'text', required: true }],
    createLabel: 'Nueva plataforma',
    name: (r) => r.name,
    actions: [
      { label: 'Sesiones', show: (r) => r.sessions > 0, run: (r, admin) => admin.jumpTo('timers', { platform: r.id }) },
      { label: 'Biblioteca', show: (r) => r.library > 0, run: (r, admin) => admin.jumpTo('library', { platform: r.id }) },
    ],
    canDelete: true,
    deleteNote: 'Solo se puede borrar una plataforma que ninguna sesión ni entrada de biblioteca use. Renombrarla no afecta a lo que ya la tiene.',
  },

  timers: {
    label: 'Sesiones',
    description: 'Todas las sesiones de juego, en curso o cerradas. La temporada sale de la fecha de inicio.',
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
      { key: 'game_id', label: 'Juego (cámbialo si se registró en otro por error)', type: 'game', nameKey: 'game' },
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
    description: 'Juegos de la biblioteca de cada jugador por temporada, con su estado.',
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
    ],
    fields: [
      platformField,
      { key: 'started_date', label: 'Fecha de inicio (su año es la temporada)', type: 'date', required: true },
      { key: 'completed', label: 'Completado', type: 'checkbox' },
      { key: 'completed_date', label: 'Fecha de completado', type: 'date' },
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

  scores: {
    label: 'Puntuaciones',
    description: 'La nota (1-100) que cada jugador ha dado a un juego: una por jugador y juego, sea cual sea la temporada.',
    endpoint: '/manage/scores',
    filters: ['user', 'game'],
    defaultSort: { key: 'updated', dir: 'desc' },
    columns: [
      userColumn,
      gameColumn,
      { label: 'Nota', sort: 'score', render: (r) => r.score },
      { label: 'Cambiada', sort: 'updated', render: (r) => formatTimestamp(r.updated_at) },
    ],
    fields: [{ key: 'score', label: 'Nota (1-100)', type: 'number', required: true }],
    createFields: [
      { key: 'user_id', label: 'Usuario', type: 'user', required: true },
      { key: 'game_id', label: 'Juego', type: 'game', required: true },
      { key: 'score', label: 'Nota (1-100)', type: 'number', required: true },
    ],
    createLabel: 'Nueva puntuación',
    name: (r) => `${r.user} · ${r.game}`,
    canDelete: true,
  },

  achievements: {
    label: 'Logros',
    nav: 'Catálogo',
    description: 'Logros que se pueden conseguir: su título, mensaje e imagen.',
    toolbarActions: [{ act: 'check-achievements', label: 'Comprobar logros' }],
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
  nav: 'Concedidos',
  description: 'Qué ha desbloqueado cada jugador y cuándo.',
  toolbarActions: [{ act: 'check-achievements', label: 'Comprobar logros' }],
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

// Not tables: custom pages, each one a module exporting render(panel, { entity, admin }).
ENTITIES.home = { label: 'Inicio', description: 'Resumen de la aplicación y lo que necesita atención.', custom: 'home' };
ENTITIES.announce = { label: 'Redactar aviso', description: 'Escribe un aviso y envíalo a los dispositivos de la app.', custom: 'announce' };
ENTITIES.notifications = {
  label: 'Ajustes',
  description: 'Interruptor general de notificaciones, resumen semanal, bot de Telegram y avisos en la app.',
  custom: 'settings',
  sections: ['notifications', 'weekly', 'telegram', 'push'],
};
ENTITIES.system = {
  label: 'Sistema',
  description: 'Inteligencia artificial que redacta algunos avisos y correo para recuperar la contraseña.',
  custom: 'settings',
  sections: ['ai', 'aiuses', 'mail'],
};

export const TABS = Object.keys(ENTITIES);
