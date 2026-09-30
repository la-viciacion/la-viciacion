// Admin panel (admins only). All data goes through /api/v1/manage/*, which the
// API restricts to admins. One generic controller renders the toolbar, table
// and pager of whichever tab is active; tabs are described in entities.js.
import { api } from '../../lib/api.js';
import { html, mount } from '../../lib/html.js';
import { loadPlatforms } from '../../lib/platforms.js';
import { toast } from '../../ui/toast.js';
import { errorState, overviewStats, store } from './components.js';
import { deleteRow, pickGame, recomputeDialog } from './dialogs.js';
import { ENTITIES, TABS } from './entities.js';
import { openForm } from './form.js';

export const active = 'admin';
export const mainClass = 'admin-main';
export const adminOnly = true;

const PAGE = 25;

const state = Object.fromEntries(TABS.map((t) => [t, { filters: {}, search: '', offset: 0, data: null, sort: ENTITIES[t].defaultSort ? { ...ENTITIES[t].defaultSort } : null }]));
let root;
let current = 'users';
let searchTimer;

// What entities/dialogs may call back into.
const admin = {
  jumpTo(tab, filters) {
    state[tab].filters = { ...filters };
    state[tab].offset = 0;
    setTab(tab);
  },
  async reload() {
    await Promise.all([load(), refreshOverview()]);
  },
};

export async function render({ main }) {
  root = main;
  current = 'users';
  mount(root, html`<div class="loading-spinner">Cargando panel...</div>`);

  let overview;
  try {
    await loadPlatforms();
    const [users, ov, achievements] = await Promise.all([api('/manage/users?limit=200'), api('/manage/overview'), api('/manage/achievements')]);
    store.achievements = (achievements || []).map((a) => ({ id: a.id, title: a.title }));
    store.users = (users?.items || []).map((u) => ({ id: u.id, username: u.username, name: u.name }));
    overview = ov;
  } catch (err) {
    mount(root, errorState(err.message));
    return;
  }

  root.addEventListener('click', onClick);
  root.addEventListener('input', onInput);
  root.addEventListener('change', onChange);
  drawLayout(overview);
  await load();
}

// ── Layout ──────────────────────────────────────────────────
function drawLayout(overview) {
  mount(root, html`
    <div class="adm-head">
      <h1 class="adm-title">Panel de administración</h1>
      <button class="adm-btn" data-act="recompute">Recalcular estadísticas</button>
    </div>
    <div class="adm-stats" id="admStats">${overviewStats(overview)}</div>
    <div class="adm-tabs" role="tablist">
      ${TABS.map((t) => html`<button class="adm-tab ${t === current ? 'active' : ''}" role="tab" data-tab="${t}">${ENTITIES[t].label}</button>`)}
    </div>
    <div id="admPanel"></div>`);
}

async function refreshOverview() {
  try {
    const overview = await api('/manage/overview');
    const el = document.getElementById('admStats');
    if (el) mount(el, html`${overviewStats(overview)}`);
  } catch { /* cosmetic */ }
}

function setTab(tab) {
  current = tab;
  root.querySelectorAll('.adm-tab').forEach((b) => b.classList.toggle('active', b.dataset.tab === tab));
  load();
}

// ── Load & render the current tab ───────────────────────────
function queryFor(entity, st) {
  const params = new URLSearchParams();
  if (entity.paged !== false) {
    params.set('limit', PAGE);
    params.set('offset', st.offset);
  }
  if (entity.search && st.search) params.set('search', st.search);
  const f = st.filters;
  if (entity.filters?.includes('user') && f.user_id) params.set('user_id', f.user_id);
  if (entity.filters?.includes('game') && f.game_id) params.set('game_id', f.game_id);
  if (entity.filters?.includes('active') && f.active) params.set('active', 'true');
  for (const select of entity.selects || []) if (f[select.key]) params.set(select.key, f[select.key]);
  if (st.sort) {
    params.set('sort', st.sort.key);
    params.set('order', st.sort.dir);
  }
  return params;
}

async function load() {
  const entity = ENTITIES[current];
  const st = state[current];
  const tab = current;
  const panel = document.getElementById('admPanel');
  if (entity.custom) {
    mount(panel, html`<div class="loading-spinner">Cargando...</div>`);
    const { render: renderSettings } = await import('./settings.js');
    if (tab === current) await renderSettings(panel);
    return;
  }
  mount(panel, panelView(entity, st, true));
  try {
    const result = await api(`${entity.endpoint}?${queryFor(entity, st)}`);
    if (tab !== current) return; // user switched tab meanwhile
    st.data = Array.isArray(result) ? { total: result.length, items: result } : result;
  } catch (err) {
    if (tab !== current) return;
    st.data = null;
    mount(panel, errorState(err.message));
    return;
  }
  mount(panel, panelView(entity, st, false));
}

function toolbarView(entity, st) {
  const f = st.filters;
  return html`
    <div class="adm-toolbar">
      ${entity.search ? html`<input type="search" class="adm-input" id="admSearch" placeholder="Buscar..." value="${st.search}" />` : ''}
      ${entity.filters?.includes('user') ? html`
        <select class="adm-input" id="admFilterUser">
          <option value="">Todos los usuarios</option>
          ${store.users.map((u) => html`<option value="${u.id}" ${String(f.user_id) === String(u.id) ? html`selected` : ''}>${u.username}</option>`)}
        </select>` : ''}
      ${entity.filters?.includes('game')
        ? (f.game_id
          ? html`<span class="adm-chip">Juego: ${f.game_name || f.game_id} <button data-act="clear-game" aria-label="Quitar filtro">&times;</button></span>`
          : html`<button class="adm-btn" data-act="filter-game">Filtrar por juego…</button>`)
        : ''}
      ${entity.filters?.includes('active') ? html`<label class="adm-check"><input type="checkbox" id="admFilterActive" ${f.active ? html`checked` : ''} /> Solo en curso</label>` : ''}
      ${(entity.selects || []).map((s) => html`
        <select class="adm-input" data-filter="${s.key}" aria-label="${s.label}">
          ${(typeof s.options === 'function' ? s.options() : s.options).map(([value, label]) => html`<option value="${value}" ${(f[s.key] || '') === value ? html`selected` : ''}>${label}</option>`)}
        </select>`)}
      <span class="adm-spacer"></span>
      ${(entity.toolbarActions || []).map((a) => html`<button class="adm-btn" data-act="${a.act}">${a.label}</button>`)}
      ${entity.createFields ? html`<button class="adm-btn primary" data-act="create">+ ${entity.createLabel}</button>` : ''}
    </div>`;
}

function rowView(entity, r, i) {
  const cells = entity.columns.map((c, col) => (c.filter
    ? html`<td><button class="adm-link" data-act="cell-filter" data-col="${col}" data-i="${i}" title="Filtrar">${c.render(r)}</button></td>`
    : html`<td>${c.render(r)}</td>`));
  const actions = (entity.actions || []).map((a, index) => (!a.show || a.show(r)
    ? html`<button class="adm-btn sm" data-act="row-action" data-a="${index}" data-i="${i}">${a.label}</button>`
    : ''));
  return html`
    <tr>
      ${cells}
      <td class="adm-row-actions">
        ${actions}
        <button class="adm-btn sm" data-act="edit" data-i="${i}">Editar</button>
        ${entity.canDelete ? html`<button class="adm-btn sm danger" data-act="delete" data-i="${i}">${entity.deleteLabel || 'Borrar'}</button>` : ''}
      </td>
    </tr>`;
}

function headerView(column, st) {
  if (!column.sort) return html`<th>${column.label}</th>`;
  const on = st.sort?.key === column.sort;
  const arrow = on ? (st.sort.dir === 'asc' ? ' ▲' : ' ▼') : '';
  const ariaSort = on ? (st.sort.dir === 'asc' ? 'ascending' : 'descending') : 'none';
  return html`<th aria-sort="${ariaSort}"><button class="adm-sort" data-act="sort" data-key="${column.sort}">${column.label}${arrow}</button></th>`;
}

function panelView(entity, st, loading) {
  const toolbar = toolbarView(entity, st);
  if (loading || !st.data) return html`${toolbar}<div class="loading-spinner">Cargando...</div>`;

  const { items, total } = st.data;
  if (!items.length) return html`${toolbar}<div class="empty-state"><span>🗂️</span>Sin resultados</div>`;

  const to = st.offset + items.length;
  const pager = entity.paged !== false ? html`
    <div class="adm-pager">
      <span>${st.offset + 1}–${to} de ${total}</span>
      <button class="adm-btn sm" data-act="prev" ${st.offset === 0 ? html`disabled` : ''}>← Anterior</button>
      <button class="adm-btn sm" data-act="next" ${to >= total ? html`disabled` : ''}>Siguiente →</button>
    </div>` : '';

  return html`${toolbar}
    <div class="adm-table-wrap">
      <table class="adm-table">
        <thead><tr>${entity.columns.map((c) => headerView(c, st))}<th></th></tr></thead>
        <tbody>${items.map((r, i) => rowView(entity, r, i))}</tbody>
      </table>
    </div>${pager}`;
}

// ── Events ──────────────────────────────────────────────────
function onInput(e) {
  if (e.target.id !== 'admSearch') return;
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    state[current].search = e.target.value.trim();
    state[current].offset = 0;
    load();
  }, 300);
}

function onChange(e) {
  const st = state[current];
  if (e.target.id === 'admFilterUser') {
    st.filters.user_id = e.target.value || undefined;
  } else if (e.target.id === 'admFilterActive') {
    st.filters.active = e.target.checked || undefined;
  } else if (e.target.dataset.filter) {
    st.filters[e.target.dataset.filter] = e.target.value || undefined;
  } else {
    return;
  }
  st.offset = 0;
  load();
}

async function onClick(e) {
  const tabButton = e.target.closest('[data-tab]');
  if (tabButton) return setTab(tabButton.dataset.tab);
  const button = e.target.closest('[data-act]');
  if (!button) return;

  const entity = ENTITIES[current];
  const st = state[current];
  const row = button.dataset.i != null ? st.data?.items?.[Number(button.dataset.i)] : null;
  try {
    switch (button.dataset.act) {
      case 'sort': {
        const key = button.dataset.key;
        st.sort = { key, dir: st.sort?.key === key && st.sort.dir === 'asc' ? 'desc' : 'asc' };
        st.offset = 0;
        return load();
      }
      case 'prev': st.offset = Math.max(0, st.offset - PAGE); return load();
      case 'next': st.offset += PAGE; return load();
      case 'recompute': return recomputeDialog();
      case 'rawg-sync': {
        const { rawgSyncFlow } = await import('./rawg-sync.js');
        return rawgSyncFlow({ onDone: admin.reload });
      }
      case 'create': return openForm(entity, null, admin);
      case 'edit': return openForm(entity, row, admin);
      case 'delete': return deleteRow(entity, row, admin);
      case 'row-action': return entity.actions[Number(button.dataset.a)].run(row, admin);
      case 'clear-game':
        delete st.filters.game_id;
        delete st.filters.game_name;
        st.offset = 0;
        return load();
      case 'filter-game': {
        const game = await pickGame('Filtrar por juego');
        if (game) {
          st.filters.game_id = game.id;
          st.filters.game_name = game.name;
          st.offset = 0;
          load();
        }
        return;
      }
      case 'cell-filter':
        Object.assign(st.filters, entity.columns[Number(button.dataset.col)].filter(row));
        st.offset = 0;
        return load();
    }
  } catch (err) {
    toast(err.message, 'err');
  }
}
