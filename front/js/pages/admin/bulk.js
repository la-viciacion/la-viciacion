// Bulk edit of the rows a table has ticked (an entity with `bulk`: { endpoint?, noun, nouns }). The selection lives in the
// tab's state (`st.selected`, a Set of ids) and the API takes the ids: it is all or nothing.
import { api, jsonRequest } from '../../lib/api.js';
import { html, mount } from '../../lib/html.js';
import { platformList } from '../../lib/platforms.js';
import { modalHeader, openModal } from '../../ui/modal.js';
import { toast } from '../../ui/toast.js';
import { pickGame } from './dialogs.js';

export const BULK_MAX = 500; // what the API takes at once (BULK_MAX of routers/manage/sessions.py)
const KEEP = '__keep';
const NONE = '__none';

const plural = (n, entity) => `${n} ${n === 1 ? entity.bulk.noun : entity.bulk.nouns}`;

/** The strip above the table: how many are ticked and what can be done with them (empty while there are none). */
export function bulkBarView(entity, st) {
  const n = st.selected.size;
  if (!n) return html``;
  const { items = [], total = 0 } = st.data || {};
  const pageTicked = items.length > 0 && items.every((r) => st.selected.has(r.id));
  const more = total > n && pageTicked;
  return html`
    <div class="adm-bulk-bar" role="status">
      <strong>Seleccionadas: ${plural(n, entity)}</strong>
      <button class="adm-btn primary sm" data-act="bulk-edit">Editar en lote…</button>
      ${more ? (total <= BULK_MAX
        ? html`<button class="adm-btn sm" data-act="bulk-all">Seleccionar las ${total} que coinciden</button>`
        : html`<span class="adm-sub">Hay ${total}: afina el filtro para editar más de ${BULK_MAX} a la vez.</span>`) : ''}
      <button class="adm-btn sm" data-act="bulk-clear">Quitar la selección</button>
    </div>`;
}

/** Ticks every row that matches the current filters (all pages), up to BULK_MAX. `params` is the table's query. */
export async function selectAllMatching(entity, st, params) {
  const ids = new Set();
  for (let offset = 0; offset < Math.min(st.data.total, BULK_MAX); offset += 200) {
    const page = new URLSearchParams(params);
    page.set('limit', '200');
    page.set('offset', String(offset));
    const { items } = await api(`${entity.endpoint}?${page}`);
    items.forEach((r) => ids.add(r.id));
  }
  st.selected = ids;
}

/** The form of the bulk edit: what is the same for all of them. Resolves when it is closed. */
export function openBulkEdit(entity, st, admin) {
  const ids = [...st.selected];
  const noun = plural(ids.length, entity);
  let game = null; // { id, name } or null: not changed
  const modal = openModal(html`
    ${modalHeader(`Editar ${noun}`)}
    <form class="adm-form" novalidate>
      <p class="adm-sub">Solo se cambia lo que elijas aquí; las fechas y las notas de cada una se quedan como están. Si cambias el juego o la plataforma, cada sesión se lleva su entrada de biblioteca.</p>
      <label>Plataforma<select class="adm-input" id="bulkPlatform">
        <option value="${KEEP}">No cambiar</option>
        <option value="${NONE}">Sin plataforma</option>
        ${platformList().map((p) => html`<option value="${p.id}">${p.name}</option>`)}
      </select></label>
      <div class="adm-field-game"><span>Juego (cámbialo si se registraron en otro por error)</span>
        <div><span class="adm-picked" id="bulkGameName">No cambiar</span> <button type="button" class="adm-btn sm" data-bulk-pick>Elegir…</button> <button type="button" class="adm-btn sm" data-bulk-keep hidden>No cambiar</button></div>
      </div>
      <div class="adm-error" role="alert"></div>
      <div class="adm-actions">
        <button type="button" class="adm-btn" data-close>Cancelar</button>
        <button type="submit" class="adm-btn primary">Aplicar a ${noun}</button>
      </div>
    </form>`, { wide: true });

  const nameEl = modal.el.querySelector('#bulkGameName');
  const keepButton = modal.el.querySelector('[data-bulk-keep]');
  const errorEl = modal.el.querySelector('.adm-error');
  const showGame = () => {
    nameEl.textContent = game ? game.name : 'No cambiar';
    keepButton.hidden = !game;
  };
  modal.el.querySelector('[data-bulk-pick]').addEventListener('click', async () => {
    const picked = await pickGame();
    if (picked) game = picked;
    showGame();
  });
  keepButton.addEventListener('click', () => {
    game = null;
    showGame();
  });

  modal.el.querySelector('form').addEventListener('submit', async (e) => {
    e.preventDefault();
    errorEl.textContent = '';
    const platform = modal.el.querySelector('#bulkPlatform').value;
    const body = { ids };
    if (platform !== KEEP) body.platform = platform === NONE ? null : platform;
    if (game) body.game_id = game.id;
    if (Object.keys(body).length === 1) {
      errorEl.textContent = 'Elige qué cambiar: la plataforma o el juego';
      return;
    }
    try {
      const { updated } = await api(entity.endpoint, jsonRequest('PATCH', body));
      modal.close();
      st.selected.clear();
      toast(`Actualizadas: ${plural(updated, entity)}`);
      await admin.reload();
    } catch (err) {
      errorEl.textContent = err.message;
    }
  });
}

/** Re-draws the strip and the "all of the page" box of the header after a tick, without redrawing the table (it would lose its scroll). */
export function refreshBulk(entity, st) {
  const bar = document.getElementById('admBulkBar');
  if (bar) mount(bar, bulkBarView(entity, st));
  const head = document.getElementById('admBulkAll');
  if (head) {
    const items = st.data?.items || [];
    const ticked = items.filter((r) => st.selected.has(r.id)).length;
    head.checked = items.length > 0 && ticked === items.length;
    head.indeterminate = ticked > 0 && ticked < items.length;
  }
}
