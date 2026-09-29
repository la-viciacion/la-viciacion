// ============================================================
//  La Viciación — Admin panel (lazy-loaded from app.js, admins only)
//  All data goes through /api/v1/manage/* which the API restricts to admins.
//  Each tab is described by an entity config; one generic controller renders
//  the toolbar, table, pager, edit/create form and delete confirmation.
// ============================================================

const PAGE = 25;

let api, esc, root, me;
let platforms = [];   // [{id, name}]
let users = [];       // [{id, username, name}] for selects

const pname = (id) => platforms.find((p) => p.id === id)?.name || id || '—';

// ── Formatting ──────────────────────────────────────────────
const fmtDT = (ts) => (ts ? String(ts).replace('T', ' ').slice(0, 16) : '—');
function fmtDur(sec) {
  if (sec == null) return '—';
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  return h ? `${h} h ${m} min` : m ? `${m} min` : `${sec} s`;
}
const badge = (text, cls) => `<span class="adm-badge ${cls}">${esc(text)}</span>`;
const toLocalISO = (d) => {
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
};

// ── UI helpers ──────────────────────────────────────────────
function toast(msg, type = 'ok') {
  const el = document.createElement('div');
  el.className = `adm-toast ${type}`;
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 3500);
}

function openModal(html, { wide = false } = {}) {
  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay adm-overlay';
  overlay.innerHTML = `<div class="modal-content ${wide ? 'adm-wide' : ''}">${html}</div>`;
  const close = () => overlay.remove();
  overlay.addEventListener('mousedown', (e) => { if (e.target === overlay) close(); });
  overlay.querySelectorAll('[data-close]').forEach((b) => b.addEventListener('click', close));
  document.body.appendChild(overlay);
  return { el: overlay, close };
}

function confirmDialog(title, bodyHtml, { danger = false, ok = 'Confirmar' } = {}) {
  return new Promise((resolve) => {
    const m = openModal(`
      <div class="modal-header"><h3>${esc(title)}</h3><button class="modal-close" data-close aria-label="Cerrar">&times;</button></div>
      <div class="adm-body">${bodyHtml}</div>
      <div class="adm-actions">
        <button class="adm-btn" data-close>Cancelar</button>
        <button class="adm-btn ${danger ? 'danger' : 'primary'}" id="admOk">${esc(ok)}</button>
      </div>`);
    let done = false;
    const finish = (v) => { if (!done) { done = true; resolve(v); } m.close(); };
    m.el.querySelector('#admOk').addEventListener('click', () => finish(true));
    m.el.querySelectorAll('[data-close]').forEach((b) => b.addEventListener('click', () => finish(false)));
    m.el.addEventListener('mousedown', (e) => { if (e.target === m.el) finish(false); });
  });
}

// Pick a game via /manage/games search. Resolves to {id, name} or null.
function pickGame(title = 'Elegir juego') {
  return new Promise((resolve) => {
    const m = openModal(`
      <div class="modal-header"><h3>${esc(title)}</h3><button class="modal-close" data-close aria-label="Cerrar">&times;</button></div>
      <input type="text" class="modal-search-input" id="admGameSearch" placeholder="Buscar juego..." autocomplete="off" />
      <div class="modal-results-list" id="admGameResults"><div class="modal-hint">Escribe para buscar</div></div>`);
    let done = false;
    const finish = (v) => { if (!done) { done = true; resolve(v); } m.close(); };
    m.el.querySelectorAll('[data-close]').forEach((b) => b.addEventListener('click', () => finish(null)));
    m.el.addEventListener('mousedown', (e) => { if (e.target === m.el) finish(null); });
    const input = m.el.querySelector('#admGameSearch');
    const results = m.el.querySelector('#admGameResults');
    let t;
    input.addEventListener('input', () => {
      clearTimeout(t);
      t = setTimeout(async () => {
        const q = input.value.trim();
        if (q.length < 2) { results.innerHTML = '<div class="modal-hint">Escribe al menos 2 caracteres</div>'; return; }
        try {
          const r = await api(`/manage/games?search=${encodeURIComponent(q)}&limit=20`);
          results.innerHTML = r.items.length
            ? r.items.map((g) => `
                <button class="modal-result-row" data-id="${esc(g.id)}" data-name="${esc(g.name)}">
                  ${g.image_url ? `<img src="${esc(g.image_url)}" alt="" class="modal-result-thumb" />` : '<div class="modal-result-thumb-placeholder">🎮</div>'}
                  <span class="modal-result-name">${esc(g.name)}</span>
                </button>`).join('')
            : '<div class="modal-hint">Sin resultados</div>';
        } catch (e) { results.innerHTML = `<div class="modal-hint">${esc(e.message)}</div>`; }
      }, 250);
    });
    results.addEventListener('click', (e) => {
      const b = e.target.closest('.modal-result-row');
      if (b) finish({ id: b.dataset.id, name: b.dataset.name });
    });
    input.focus();
  });
}

// ── Entity configs ──────────────────────────────────────────
const platformField = { key: 'platform', label: 'Plataforma', type: 'platform' };

const ENTITIES = {
  users: {
    label: 'Usuarios',
    endpoint: '/manage/users',
    search: true,
    columns: [
      { label: 'Usuario', render: (r) => `<strong>${esc(r.username)}</strong><div class="adm-sub">${esc(r.name || '')}</div>` },
      { label: 'Email', render: (r) => esc(r.email || '—') },
      { label: 'Sesiones', render: (r) => r.sessions },
      { label: 'Biblioteca', render: (r) => r.library },
      { label: 'Estado', render: (r) => (r.is_admin ? badge('Admin', 'purple') : '') + badge(r.is_active ? 'Activo' : 'Inactivo', r.is_active ? 'green' : 'red') },
    ],
    fields: [
      { key: 'name', label: 'Nombre', type: 'text' },
      { key: 'username', label: 'Usuario', type: 'text', required: true },
      { key: 'email', label: 'Email', type: 'text' },
      { key: 'telegram_id', label: 'Telegram ID', type: 'number' },
      { key: 'is_admin', label: 'Administrador', type: 'checkbox' },
      { key: 'is_active', label: 'Activo', type: 'checkbox' },
    ],
    name: (r) => r.username,
    actions: [
      { label: 'Contraseña', run: (r) => passwordDialog(r) },
      { label: 'Sesiones', run: (r) => jumpTo('timers', { user_id: r.id }) },
    ],
    canDelete: true,
    deleteNote: 'Se borrarán también sus sesiones, biblioteca y logros.',
  },

  games: {
    label: 'Juegos',
    endpoint: '/manage/games',
    search: true,
    columns: [
      { label: 'Juego', render: (r) => `<div class="adm-game">${r.image_url ? `<img src="${esc(r.image_url)}" alt="" loading="lazy" />` : '<span>🎮</span>'}<div><strong>${esc(r.name)}</strong><div class="adm-sub">${esc(r.dev || '')}</div></div></div>` },
      { label: 'Géneros', render: (r) => esc(r.genres || '—') },
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
      { label: 'Sesiones', run: (r) => jumpTo('timers', { game_id: r.id, game_name: r.name }) },
      { label: 'Fusionar…', run: (r) => mergeDialog(r) },
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
      { label: 'Usuario', render: (r) => esc(r.user || r.user_id), filter: (r) => ({ user_id: r.user_id }) },
      { label: 'Juego', render: (r) => esc(r.game || r.game_id), filter: (r) => ({ game_id: r.game_id, game_name: r.game }) },
      { label: 'Inicio', render: (r) => fmtDT(r.start_time) },
      { label: 'Fin', render: (r) => (r.is_active ? badge('En curso', 'orange') : fmtDT(r.end_time)) },
      { label: 'Duración', render: (r) => fmtDur(r.duration_seconds) },
      { label: 'Plataforma', render: (r) => esc(pname(r.platform)) },
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
    name: (r) => `${r.game || r.game_id} · ${fmtDT(r.start_time)}`,
    actions: [
      { label: 'Cerrar ahora', show: (r) => r.is_active, run: (r) => closeTimerNow(r) },
    ],
    canDelete: true,
  },

  library: {
    label: 'Biblioteca',
    endpoint: '/manage/library',
    filters: ['user', 'game'],
    columns: [
      { label: 'Usuario', render: (r) => esc(r.user || r.user_id), filter: (r) => ({ user_id: r.user_id }) },
      { label: 'Juego', render: (r) => esc(r.game || r.game_id), filter: (r) => ({ game_id: r.game_id, game_name: r.game }) },
      { label: 'Plataforma', render: (r) => esc(pname(r.platform)) },
      { label: 'Temp.', render: (r) => r.season ?? '—' },
      { label: 'Inicio', render: (r) => esc(r.started_date || '—') },
      { label: 'Completado', render: (r) => (r.completed ? badge('Sí ' + (r.completed_date || ''), 'green') : badge('No', 'gray')) },
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
    columns: [
      { label: 'Imagen', render: (r) => (r.has_image ? `<img class="adm-ach" src="/api/v1/utils/achievement-image/${esc(r.key)}?v=${Date.now()}" alt="" />` : '—') },
      { label: 'Logro', render: (r) => `<strong>${esc(r.title)}</strong><div class="adm-sub">${esc(r.key)}</div>` },
      { label: 'Mensaje', render: (r) => esc(r.message || '') },
      { label: 'Concedido', render: (r) => r.awarded },
    ],
    fields: [
      { key: 'title', label: 'Título', type: 'text', required: true },
      { key: 'message', label: 'Mensaje ({} = usuario / juego)', type: 'text' },
    ],
    name: (r) => r.title,
    actions: [{ label: 'Imagen…', run: (r) => uploadAchievementImage(r) }],
    canDelete: false,
  },
};

const TABS = Object.keys(ENTITIES);
const state = Object.fromEntries(TABS.map((t) => [t, { filters: {}, search: '', offset: 0, data: null }]));
let current = 'users';
let overview = null;

// ── Init & layout ───────────────────────────────────────────
export async function initAdmin(rootEl, ctx) {
  root = rootEl;
  api = ctx.apiFetch;
  esc = ctx.escapeHtml;
  me = ctx.me;

  root.innerHTML = '<div class="loading-spinner">Cargando panel...</div>';
  try {
    const [pl, us, ov] = await Promise.all([
      api('/utils/platforms'),
      api('/manage/users?limit=200'),
      api('/manage/overview'),
    ]);
    platforms = pl || [];
    users = (us?.items || []).map((u) => ({ id: u.id, username: u.username, name: u.name }));
    overview = ov;
  } catch (e) {
    root.innerHTML = `<div class="empty-state"><span>⚠️</span>${esc(e.message)}</div>`;
    return;
  }

  root.addEventListener('click', onClick);
  root.addEventListener('input', onInput);
  root.addEventListener('change', onChange);
  layout();
  await load();
}

function layout() {
  const ov = overview;
  root.innerHTML = `
    <div class="adm-head">
      <h1 class="adm-title">Panel de administración</h1>
      <button class="adm-btn" data-act="recompute">Recalcular estadísticas</button>
    </div>
    <div class="adm-stats" id="admStats">
      ${[['Usuarios', ov.users], ['Juegos', ov.games], ['Sesiones', ov.timers], ['Timers activos', ov.active_timers], ['Biblioteca', ov.library]]
        .map(([l, v]) => `<div class="adm-stat"><div class="adm-stat-v">${v}</div><div class="adm-stat-l">${l}</div></div>`).join('')}
    </div>
    <div class="adm-tabs" role="tablist">
      ${TABS.map((t) => `<button class="adm-tab ${t === current ? 'active' : ''}" role="tab" data-tab="${t}">${ENTITIES[t].label}</button>`).join('')}
    </div>
    <div id="admPanel"></div>`;
}

async function refreshOverview() {
  try {
    overview = await api('/manage/overview');
    const el = document.getElementById('admStats');
    if (el) {
      const ov = overview;
      el.innerHTML = [['Usuarios', ov.users], ['Juegos', ov.games], ['Sesiones', ov.timers], ['Timers activos', ov.active_timers], ['Biblioteca', ov.library]]
        .map(([l, v]) => `<div class="adm-stat"><div class="adm-stat-v">${v}</div><div class="adm-stat-l">${l}</div></div>`).join('');
    }
  } catch { /* cosmetic */ }
}

function jumpTo(tab, filters) {
  state[tab].filters = { ...filters };
  state[tab].offset = 0;
  setTab(tab);
}

function setTab(tab) {
  current = tab;
  root.querySelectorAll('.adm-tab').forEach((b) => b.classList.toggle('active', b.dataset.tab === tab));
  load();
}

// ── Load & render current tab ───────────────────────────────
async function load() {
  const ent = ENTITIES[current];
  const st = state[current];
  const panel = document.getElementById('admPanel');
  panel.innerHTML = renderPanel(ent, st, true);
  const params = new URLSearchParams();
  if (ent.endpoint !== '/manage/achievements') {
    params.set('limit', PAGE);
    params.set('offset', st.offset);
  }
  if (ent.search && st.search) params.set('search', st.search);
  const f = st.filters;
  if (ent.filters?.includes('user') && f.user_id) params.set('user_id', f.user_id);
  if (ent.filters?.includes('game') && f.game_id) params.set('game_id', f.game_id);
  if (ent.filters?.includes('active') && f.active) params.set('active', 'true');
  const tab = current;
  try {
    const r = await api(`${ent.endpoint}?${params}`);
    if (tab !== current) return;                       // user switched tab meanwhile
    st.data = Array.isArray(r) ? { total: r.length, items: r } : r;
  } catch (e) {
    if (tab !== current) return;
    st.data = null;
    panel.innerHTML = `<div class="empty-state"><span>⚠️</span>${esc(e.message)}</div>`;
    return;
  }
  panel.innerHTML = renderPanel(ent, st, false);
}

function renderPanel(ent, st, loading) {
  const f = st.filters;
  const toolbar = `
    <div class="adm-toolbar">
      ${ent.search ? `<input type="search" class="adm-input" id="admSearch" placeholder="Buscar..." value="${esc(st.search)}" />` : ''}
      ${ent.filters?.includes('user') ? `
        <select class="adm-input" id="admFilterUser">
          <option value="">Todos los usuarios</option>
          ${users.map((u) => `<option value="${u.id}" ${String(f.user_id) === String(u.id) ? 'selected' : ''}>${esc(u.username)}</option>`).join('')}
        </select>` : ''}
      ${ent.filters?.includes('game') ? (f.game_id
        ? `<span class="adm-chip">Juego: ${esc(f.game_name || f.game_id)} <button data-act="clear-game" aria-label="Quitar filtro">&times;</button></span>`
        : '<button class="adm-btn" data-act="filter-game">Filtrar por juego…</button>') : ''}
      ${ent.filters?.includes('active') ? `<label class="adm-check"><input type="checkbox" id="admFilterActive" ${f.active ? 'checked' : ''}/> Solo en curso</label>` : ''}
      <span class="adm-spacer"></span>
      ${(ent.toolbarActions || []).map((a) => `<button class="adm-btn" data-act="${a.act}">${esc(a.label)}</button>`).join('')}
      ${ent.createFields ? `<button class="adm-btn primary" data-act="create">+ ${esc(ent.createLabel)}</button>` : ''}
    </div>`;

  if (loading || !st.data) {
    return toolbar + '<div class="loading-spinner">Cargando...</div>';
  }
  const { items, total } = st.data;
  if (!items.length) return toolbar + '<div class="empty-state"><span>🗂️</span>Sin resultados</div>';

  const rows = items.map((r, i) => `
    <tr>
      ${ent.columns.map((c) => {
        const cell = c.render(r);
        return c.filter
          ? `<td><button class="adm-link" data-act="cell-filter" data-col="${ent.columns.indexOf(c)}" data-i="${i}" title="Filtrar">${cell}</button></td>`
          : `<td>${cell}</td>`;
      }).join('')}
      <td class="adm-row-actions">
        ${(ent.actions || []).filter((a) => !a.show || a.show(r)).map((a) => `<button class="adm-btn sm" data-act="row-action" data-a="${ent.actions.indexOf(a)}" data-i="${i}">${esc(a.label)}</button>`).join('')}
        <button class="adm-btn sm" data-act="edit" data-i="${i}">Editar</button>
        ${ent.canDelete ? `<button class="adm-btn sm danger" data-act="delete" data-i="${i}">Borrar</button>` : ''}
      </td>
    </tr>`).join('');

  const paged = ent.endpoint !== '/manage/achievements';
  const from = st.offset + 1;
  const to = st.offset + items.length;
  const pager = paged ? `
    <div class="adm-pager">
      <span>${from}–${to} de ${total}</span>
      <button class="adm-btn sm" data-act="prev" ${st.offset === 0 ? 'disabled' : ''}>← Anterior</button>
      <button class="adm-btn sm" data-act="next" ${to >= total ? 'disabled' : ''}>Siguiente →</button>
    </div>` : '';

  return `${toolbar}
    <div class="adm-table-wrap">
      <table class="adm-table">
        <thead><tr>${ent.columns.map((c) => `<th>${c.label}</th>`).join('')}<th></th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>${pager}`;
}

// ── Events ──────────────────────────────────────────────────
let searchTimer;
function onInput(e) {
  if (e.target.id === 'admSearch') {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      state[current].search = e.target.value.trim();
      state[current].offset = 0;
      load();
    }, 300);
  }
}

function onChange(e) {
  const st = state[current];
  if (e.target.id === 'admFilterUser') { st.filters.user_id = e.target.value || undefined; st.offset = 0; load(); }
  if (e.target.id === 'admFilterActive') { st.filters.active = e.target.checked || undefined; st.offset = 0; load(); }
}

async function onClick(e) {
  const tabBtn = e.target.closest('[data-tab]');
  if (tabBtn) return setTab(tabBtn.dataset.tab);
  const btn = e.target.closest('[data-act]');
  if (!btn) return;
  const ent = ENTITIES[current];
  const st = state[current];
  const row = btn.dataset.i != null ? st.data?.items?.[Number(btn.dataset.i)] : null;
  try {
    switch (btn.dataset.act) {
      case 'prev': st.offset = Math.max(0, st.offset - PAGE); return load();
      case 'next': st.offset += PAGE; return load();
      case 'recompute': return recomputeDialog();
      case 'rawg-sync': {
        const { rawgSyncFlow } = await import('./admin-rawg.js');
        return rawgSyncFlow({ api, esc, openModal, toast, jsonReq, onDone: () => { load(); refreshOverview(); } });
      }
      case 'create': return openForm(ent, null);
      case 'edit': return openForm(ent, row);
      case 'delete': return deleteRow(ent, row);
      case 'row-action': return ent.actions[Number(btn.dataset.a)].run(row);
      case 'clear-game': delete st.filters.game_id; delete st.filters.game_name; st.offset = 0; return load();
      case 'filter-game': {
        const g = await pickGame('Filtrar por juego');
        if (g) { st.filters.game_id = g.id; st.filters.game_name = g.name; st.offset = 0; load(); }
        return;
      }
      case 'cell-filter': {
        Object.assign(st.filters, ent.columns[Number(btn.dataset.col)].filter(row));
        st.offset = 0;
        return load();
      }
    }
  } catch (err) {
    toast(err.message, 'err');
  }
}

// ── Create / edit form ──────────────────────────────────────
function fieldHtml(f, value) {
  const id = `f_${f.key}`;
  const v = value ?? '';
  switch (f.type) {
    case 'checkbox':
      return `<label class="adm-check"><input type="checkbox" id="${id}" ${value ? 'checked' : ''}/> ${esc(f.label)}</label>`;
    case 'platform':
      return `<label>${esc(f.label)}<select class="adm-input" id="${id}"><option value="">—</option>${platforms.map((p) => `<option value="${esc(p.id)}" ${p.id === v ? 'selected' : ''}>${esc(p.name)}</option>`).join('')}${v && !platforms.some((p) => p.id === v) ? `<option value="${esc(v)}" selected>${esc(v)}</option>` : ''}</select></label>`;
    case 'user':
      return `<label>${esc(f.label)}<select class="adm-input" id="${id}"><option value="">Elegir…</option>${users.map((u) => `<option value="${u.id}">${esc(u.username)}</option>`).join('')}</select></label>`;
    case 'game':
      return `<div class="adm-field-game"><span>${esc(f.label)}</span><div><span class="adm-picked" id="${id}_name">Ninguno</span> <button type="button" class="adm-btn sm" data-pickfor="${f.key}">Elegir…</button></div><input type="hidden" id="${id}" /></div>`;
    case 'datetime':
      return `<label>${esc(f.label)}<input class="adm-input" type="datetime-local" step="1" id="${id}" value="${esc(String(v).slice(0, 19))}" /></label>`;
    case 'date':
      return `<label>${esc(f.label)}<input class="adm-input" type="date" id="${id}" value="${esc(String(v).slice(0, 10))}" /></label>`;
    case 'number':
      return `<label>${esc(f.label)}<input class="adm-input" type="number" step="${f.step || '1'}" id="${id}" value="${esc(v)}" /></label>`;
    default:
      return `<label>${esc(f.label)}<input class="adm-input" type="text" id="${id}" value="${esc(v)}" /></label>`;
  }
}

function readField(f) {
  const el = document.getElementById(`f_${f.key}`);
  switch (f.type) {
    case 'checkbox': return el.checked;
    case 'number': return el.value === '' ? null : Number(el.value);
    case 'datetime': return el.value ? (el.value.length === 16 ? el.value + ':00' : el.value) : null;
    case 'date': return el.value || null;
    case 'platform': return el.value || null;
    case 'user': return el.value ? Number(el.value) : null;
    default: return el.value === '' ? null : el.value;
  }
}

function openForm(ent, row) {
  const creating = !row;
  const fields = creating ? ent.createFields : ent.fields;
  const m = openModal(`
    <div class="modal-header"><h3>${creating ? esc(ent.createLabel) : `Editar · ${esc(ent.name(row))}`}</h3><button class="modal-close" data-close aria-label="Cerrar">&times;</button></div>
    <form class="adm-form" id="admForm" novalidate>
      ${fields.map((f) => fieldHtml(f, row ? row[f.key] : undefined)).join('')}
      <div class="adm-error" id="admFormError" role="alert"></div>
      <div class="adm-actions">
        <button type="button" class="adm-btn" data-close>Cancelar</button>
        <button type="submit" class="adm-btn primary">${creating ? 'Crear' : 'Guardar'}</button>
      </div>
    </form>`, { wide: true });

  m.el.addEventListener('click', async (e) => {
    const pick = e.target.closest('[data-pickfor]');
    if (!pick) return;
    const g = await pickGame();
    if (g) {
      m.el.querySelector(`#f_${pick.dataset.pickfor}`).value = g.id;
      m.el.querySelector(`#f_${pick.dataset.pickfor}_name`).textContent = g.name;
    }
  });

  m.el.querySelector('#admForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const errEl = m.el.querySelector('#admFormError');
    errEl.textContent = '';
    const body = {};
    for (const f of fields) {
      let val = f.type === 'game' ? (document.getElementById(`f_${f.key}`).value || null) : readField(f);
      if (f.required && (val === null || val === '')) { errEl.textContent = `Falta: ${f.label}`; return; }
      if (f.omitEmpty && val === null) continue;
      body[f.key] = val;
    }
    try {
      if (creating) await api(ent.endpoint, jsonReq('POST', body));
      else await api(`${ent.endpoint}/${row.id}`, jsonReq('PATCH', body));
      m.close();
      toast(creating ? 'Creado' : 'Guardado');
      await load();
      refreshOverview();
    } catch (err) {
      errEl.textContent = err.message;
    }
  });
}

const jsonReq = (method, body) => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
});

// ── Delete (with a confirmation that lists what goes with it) ──
async function deleteRow(ent, row) {
  const url = `${ent.endpoint}/${row.id}`;
  const title = `Borrar · ${ent.name(row)}`;
  try {
    try {
      // First try without force: rows with dependants come back as 409 + counts.
      const simple = await confirmDialog(title, `<p>Esta acción no se puede deshacer.</p>${ent.deleteNote ? `<p>${esc(ent.deleteNote)}</p>` : ''}`, { danger: true, ok: 'Borrar' });
      if (!simple) return;
      await api(url, { method: 'DELETE' });
    } catch (err) {
      if (err.status !== 409 || !err.detail?.counts) throw err;
      const list = Object.entries(err.detail.counts).map(([k, v]) => `<li><strong>${v}</strong> ${esc(k)}</li>`).join('');
      const ok = await confirmDialog(title, `<p>Tiene datos asociados que <strong>se borrarán también</strong>:</p><ul class="adm-list">${list}</ul><p>Esta acción no se puede deshacer.</p>`, { danger: true, ok: 'Borrar todo' });
      if (!ok) return;
      await api(`${url}?force=true`, { method: 'DELETE' });
    }
    toast('Eliminado');
    await load();
    refreshOverview();
  } catch (err) {
    toast(err.message, 'err');
  }
}

// ── Special actions ─────────────────────────────────────────
function passwordDialog(user) {
  const m = openModal(`
    <div class="modal-header"><h3>Contraseña · ${esc(user.username)}</h3><button class="modal-close" data-close aria-label="Cerrar">&times;</button></div>
    <form class="adm-form" id="admPw" novalidate>
      <label>Nueva contraseña<input class="adm-input" type="password" id="admPwInput" autocomplete="new-password" /></label>
      <div class="adm-sub">12-24 caracteres, con mayúscula, minúscula, número y un carácter especial.</div>
      <div class="adm-error" id="admPwErr" role="alert"></div>
      <div class="adm-actions"><button type="button" class="adm-btn" data-close>Cancelar</button><button class="adm-btn primary" type="submit">Cambiar</button></div>
    </form>`);
  m.el.querySelector('#admPw').addEventListener('submit', async (e) => {
    e.preventDefault();
    try {
      await api(`/manage/users/${user.id}/password`, jsonReq('POST', { password: m.el.querySelector('#admPwInput').value }));
      m.close();
      toast('Contraseña actualizada');
    } catch (err) { m.el.querySelector('#admPwErr').textContent = err.message; }
  });
  m.el.querySelector('#admPwInput').focus();
}

async function mergeDialog(source) {
  const target = await pickGame(`Fusionar «${source.name}» en…`);
  if (!target) return;
  if (target.id === source.id) return toast('Elige otro juego', 'err');
  const ok = await confirmDialog('Fusionar juegos', `
    <p>Todas las sesiones y entradas de biblioteca de <strong>${esc(source.name)}</strong> pasarán a <strong>${esc(target.name)}</strong>, y <strong>${esc(source.name)}</strong> se eliminará.</p>
    <p>Los registros que coincidan con uno ya existente en el destino se descartan.</p>`, { danger: true, ok: 'Fusionar' });
  if (!ok) return;
  const r = await api(`/manage/games/${source.id}/merge`, jsonReq('POST', { target_id: target.id }));
  const fmt = (o) => Object.entries(o).filter(([, v]) => v).map(([k, v]) => `${v} ${k}`).join(', ') || 'nada';
  toast(`Fusionado. Movido: ${fmt(r.moved)}. Descartado: ${fmt(r.dropped)}.`);
  await load();
  refreshOverview();
}

async function closeTimerNow(row) {
  const ok = await confirmDialog('Cerrar timer', `<p>Se cerrará el timer en curso de <strong>${esc(row.user || row.user_id)}</strong> con la hora actual.</p>`, { ok: 'Cerrar timer' });
  if (!ok) return;
  await api(`/manage/timers/${row.id}`, jsonReq('PATCH', { end_time: toLocalISO(new Date()) }));
  toast('Timer cerrado');
  await load();
  refreshOverview();
}

function uploadAchievementImage(row) {
  const input = document.createElement('input');
  input.type = 'file';
  input.accept = 'image/png,image/jpeg';
  input.addEventListener('change', async () => {
    const file = input.files[0];
    if (!file) return;
    try {
      const fd = new FormData();
      fd.append('file', file);
      await api(`/utils/achievement-image/${encodeURIComponent(row.key)}`, { method: 'PATCH', body: fd });
      toast('Imagen actualizada');
      await load();
    } catch (err) { toast(err.message, 'err'); }
  });
  input.click();
}

function recomputeDialog() {
  const m = openModal(`
    <div class="modal-header"><h3>Recalcular estadísticas</h3><button class="modal-close" data-close aria-label="Cerrar">&times;</button></div>
    <form class="adm-form" id="admRc">
      <p class="adm-sub">Vuelve a calcular estadísticas, logros y rankings a partir de las sesiones. Se ejecuta en segundo plano.</p>
      <label>Usuario<select class="adm-input" id="rcUser"><option value="">Todos</option>${users.map((u) => `<option value="${u.id}">${esc(u.username)}</option>`).join('')}</select></label>
      <label class="adm-check"><input type="checkbox" id="rcSilent" checked /> Sin notificaciones (Telegram)</label>
      <div class="adm-sub">Ojo: con notificaciones desactivadas, los cambios de ranking se guardan igualmente y no se anunciarán después.</div>
      <div class="adm-actions"><button type="button" class="adm-btn" data-close>Cancelar</button><button class="adm-btn primary" type="submit">Recalcular</button></div>
    </form>`);
  m.el.querySelector('#admRc').addEventListener('submit', async (e) => {
    e.preventDefault();
    try {
      const uid = m.el.querySelector('#rcUser').value;
      await api('/manage/recompute', jsonReq('POST', { user_id: uid ? Number(uid) : null, silent: m.el.querySelector('#rcSilent').checked }));
      m.close();
      toast('Recálculo en marcha');
    } catch (err) { toast(err.message, 'err'); }
  });
}
