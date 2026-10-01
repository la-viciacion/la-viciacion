// Admin panel (admins only). All data goes through /api/v1/manage/*, which the
// API restricts to admins. A sidebar (nav.js) picks the section, whose address is
// #/admin/<section>; one generic controller renders the toolbar, table and pager of
// a data section, described in entities.js, and custom sections draw themselves.
import { api } from '../../lib/api.js';
import { html, mount } from '../../lib/html.js';
import { loadPlatforms } from '../../lib/platforms.js';
import { toast } from '../../ui/toast.js';
import { errorState, store } from './components.js';
import { checkAchievementsDialog, deleteRow, pickGame } from './dialogs.js';
import { ENTITIES, TABS } from './entities.js';
import { openForm } from './form.js';
import { SECTIONS, hashFor, sectionOf, tabFromHash } from './nav.js';

export const active = 'admin';
export const mainClass = 'admin-main';
export const adminOnly = true;

const PAGE = 25;

const state = Object.fromEntries(TABS.map((t) => [t, { filters: {}, search: '', offset: 0, data: null, sort: ENTITIES[t].defaultSort ? { ...ENTITIES[t].defaultSort } : null }]));
let root;
let current = 'home';
const lastTab = new Map(); // section -> the tab it was left on
let searchTimer;

// What entities/dialogs may call back into.
const admin = {
  jumpTo,
  open(tab) {
    return jumpTo(tab, state[tab].filters);
  },
  async create(tab) {
    await jumpTo(tab, {});
    return openForm(ENTITIES[tab], null, admin);
  },
  async reload() {
    // the platform lists of the forms and filters are cached: a rename or a new platform must show up
    await loadPlatforms();
    await load();
  },
};

function jumpTo(tab, filters) {
  state[tab].filters = { ...filters };
  state[tab].offset = 0;
  return setTab(tab);
}

export function dispose() {
  window.removeEventListener('scroll', closeMenus, true);
  window.removeEventListener('resize', closeMenus);
}

export async function render({ main, user }) {
  root = main;
  store.me = user.id;
  current = tabFromHash(location.hash, TABS);
  mount(root, html`<div class="loading-spinner">Cargando panel...</div>`);

  try {
    await loadPlatforms();
    const [users, achievements] = await Promise.all([api('/manage/users?limit=200'), api('/manage/achievements')]);
    store.achievements = (achievements || []).map((a) => ({ id: a.id, title: a.title }));
    store.users = (users?.items || []).map((u) => ({ id: u.id, username: u.username, name: u.name, telegram_id: u.telegram_id }));
  } catch (err) {
    mount(root, errorState(err.message));
    return;
  }

  root.addEventListener('click', onClick);
  root.addEventListener('input', onInput);
  root.addEventListener('change', onChange);
  window.addEventListener('scroll', closeMenus, true);
  window.addEventListener('resize', closeMenus);
  drawLayout();
  await load();
}

// ── Layout ──────────────────────────────────────────────────
const tabLabel = (tab) => ENTITIES[tab].nav || ENTITIES[tab].label;

function navView() {
  return SECTIONS.map((section, i) => html`<button class="adm-nav-item" data-section="${i}">${section.label}</button>`);
}

function drawLayout() {
  mount(root, html`
    <div class="adm-shell">
      <aside class="adm-side">
        <button class="adm-side-toggle" data-act="toggle-nav" aria-expanded="false">
          <span>Panel de administración</span><span id="admNavCurrent"></span>
        </button>
        <nav class="adm-nav" aria-label="Secciones del panel">${navView()}</nav>
      </aside>
      <section class="adm-content">
        <header class="adm-page-head">
          <h1 class="adm-title" id="admTitle"></h1>
          <p class="adm-desc" id="admDesc"></p>
        </header>
        <div class="adm-tabs" id="admTabs" role="tablist"></div>
        <div id="admPanel"></div>
      </section>
    </div>`);
  drawHeading();
}

function drawHeading() {
  const section = sectionOf(current);
  document.getElementById('admTitle').textContent = section.label;
  document.getElementById('admDesc').textContent = ENTITIES[current].description || '';
  document.getElementById('admNavCurrent').textContent = section.label;
  const tabs = document.getElementById('admTabs');
  tabs.hidden = section.tabs.length < 2;
  mount(tabs, html`${section.tabs.map((t) => html`<button class="adm-tab ${t === current ? 'active' : ''}" role="tab" aria-selected="${String(t === current)}" data-tab="${t}">${tabLabel(t)}</button>`)}`);
  root.querySelectorAll('.adm-nav-item').forEach((b) => {
    const on = SECTIONS[Number(b.dataset.section)] === section;
    b.classList.toggle('active', on);
    if (on) b.setAttribute('aria-current', 'page');
    else b.removeAttribute('aria-current');
  });
}

// Moving inside the panel adds a history entry without a hashchange, so the page is not rebuilt.
function setTab(tab) {
  current = tab;
  lastTab.set(sectionOf(tab), tab);
  if (location.hash !== hashFor(tab)) history.pushState(null, '', hashFor(tab));
  drawHeading();
  closeNav();
  window.scrollTo(0, 0);
  return load();
}

function closeNav() {
  root.querySelector('.adm-side')?.classList.remove('open');
  root.querySelector('.adm-side-toggle')?.setAttribute('aria-expanded', 'false');
}

// Row menus ("⋯") are placed over the page, since the table scrolls on its own.
function closeMenus() {
  document.querySelectorAll('.adm-menu[open]').forEach((m) => { m.open = false; });
}

function toggleMenu(menu) {
  const wasOpen = menu.open;
  closeMenus();
  if (wasOpen) return;
  menu.open = true;
  const button = menu.querySelector('summary').getBoundingClientRect();
  const list = menu.querySelector('.adm-menu-list');
  const below = button.bottom + 4;
  list.style.top = `${below + list.offsetHeight > window.innerHeight ? Math.max(4, button.top - list.offsetHeight - 4) : below}px`;
  list.style.right = `${window.innerWidth - button.right}px`;
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
    const { render: renderCustom } = await import(`./${entity.custom}.js`);
    if (tab === current) await renderCustom(panel, { entity, admin });
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
  const extras = (entity.actions || []).map((a, index) => (!a.show || a.show(r)
    ? html`<button class="adm-menu-item" data-act="row-action" data-a="${index}" data-i="${i}">${a.label}</button>`
    : ''));
  if (entity.canDelete) extras.push(html`<button class="adm-menu-item danger" data-act="delete" data-i="${i}">${entity.deleteLabel || 'Borrar'}</button>`);
  return html`
    <tr>
      ${cells}
      <td class="adm-row-actions">
        <button class="adm-btn sm" data-act="edit" data-i="${i}">Editar</button>
        ${extras.some((x) => x !== '') ? html`
          <details class="adm-menu">
            <summary class="adm-btn sm" aria-label="Más acciones">⋯</summary>
            <div class="adm-menu-list">${extras}</div>
          </details>` : ''}
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
  const summary = e.target.closest('.adm-menu > summary');
  if (summary) {
    e.preventDefault(); // toggled by hand, to place the list
    return toggleMenu(summary.parentElement);
  }
  closeMenus();
  const tabButton = e.target.closest('[data-tab]');
  if (tabButton) return setTab(tabButton.dataset.tab);
  const sectionButton = e.target.closest('[data-section]');
  if (sectionButton) {
    const section = SECTIONS[Number(sectionButton.dataset.section)];
    return setTab(lastTab.get(section) || section.tabs[0]);
  }
  const button = e.target.closest('[data-act]');
  if (!button) return;

  const entity = ENTITIES[current];
  const st = state[current];
  const row = button.dataset.i != null ? st.data?.items?.[Number(button.dataset.i)] : null;
  try {
    switch (button.dataset.act) {
      case 'toggle-nav': {
        const open = root.querySelector('.adm-side').classList.toggle('open');
        button.setAttribute('aria-expanded', String(open));
        return;
      }
      case 'sort': {
        const key = button.dataset.key;
        st.sort = { key, dir: st.sort?.key === key && st.sort.dir === 'asc' ? 'desc' : 'asc' };
        st.offset = 0;
        return load();
      }
      case 'prev': st.offset = Math.max(0, st.offset - PAGE); return load();
      case 'next': st.offset += PAGE; return load();
      case 'check-achievements': return checkAchievementsDialog();
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
