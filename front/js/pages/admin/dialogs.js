// Admin dialogs and one-off actions (confirm, game picker, merge, delete...).
// Everything that changes data takes `admin` = { reload } to refresh the view.
import { api, jsonRequest } from '../../lib/api.js';
import { toLocalISO } from '../../lib/format.js';
import { html, mount } from '../../lib/html.js';
import { modalHeader, openModal } from '../../ui/modal.js';
import { toast } from '../../ui/toast.js';
import { store } from './components.js';

/** Yes/no dialog. Resolves to true only when the confirm button is pressed. */
export function confirmDialog(title, body, { danger = false, ok = 'Confirmar' } = {}) {
  return new Promise((resolve) => {
    let answer = false;
    const m = openModal(html`
      ${modalHeader(title)}
      <div class="adm-body">${body}</div>
      <div class="adm-actions">
        <button class="adm-btn" data-close>Cancelar</button>
        <button class="adm-btn ${danger ? 'danger' : 'primary'}" data-confirm>${ok}</button>
      </div>`, { onClose: () => resolve(answer) });
    m.el.querySelector('[data-confirm]').addEventListener('click', () => { answer = true; m.close(); });
  });
}

/** Search games through /manage/games. Resolves to {id, name} or null. */
export function pickGame(title = 'Elegir juego') {
  return new Promise((resolve) => {
    let picked = null;
    const m = openModal(html`
      ${modalHeader(title)}
      <input type="text" class="modal-search-input" placeholder="Buscar juego..." autocomplete="off" />
      <div class="modal-results-list"><div class="modal-hint">Escribe para buscar</div></div>`, { onClose: () => resolve(picked) });

    const input = m.el.querySelector('input');
    const results = m.el.querySelector('.modal-results-list');
    const hint = (text) => mount(results, html`<div class="modal-hint">${text}</div>`);
    let timer;
    input.addEventListener('input', () => {
      clearTimeout(timer);
      timer = setTimeout(async () => {
        const query = input.value.trim();
        if (query.length < 2) return hint('Escribe al menos 2 caracteres');
        try {
          const found = await api(`/manage/games?search=${encodeURIComponent(query)}&limit=20`);
          if (!found.items.length) return hint('Sin resultados');
          mount(results, html`${found.items.map((g) => html`
            <button class="modal-result-row" data-id="${g.id}" data-name="${g.name}">
              ${g.image_url ? html`<img src="${g.image_url}" alt="" class="modal-result-thumb" />` : html`<div class="modal-result-thumb-placeholder">🎮</div>`}
              <span class="modal-result-name">${g.name}</span>
            </button>`)}`);
        } catch (err) {
          hint(err.message);
        }
      }, 250);
    });
    results.addEventListener('click', (e) => {
      const row = e.target.closest('.modal-result-row');
      if (!row) return;
      picked = { id: row.dataset.id, name: row.dataset.name };
      m.close();
    });
    input.focus();
  });
}

/** Delete a row; rows with dependants come back as 409 + counts and need a second, explicit confirmation. */
export async function deleteRow(entity, row, admin) {
  const url = `${entity.endpoint}/${row.id}`;
  const title = `Borrar · ${entity.name(row)}`;
  try {
    try {
      const ok = await confirmDialog(title, html`<p>Esta acción no se puede deshacer.</p>${entity.deleteNote ? html`<p>${entity.deleteNote}</p>` : ''}`, { danger: true, ok: 'Borrar' });
      if (!ok) return;
      await api(url, { method: 'DELETE' });
    } catch (err) {
      if (err.status !== 409 || !err.detail?.counts) throw err;
      const list = Object.entries(err.detail.counts).map(([k, v]) => html`<li><strong>${v}</strong> ${k}</li>`);
      const ok = await confirmDialog(title, html`
        <p>Tiene datos asociados que <strong>se borrarán también</strong>:</p>
        <ul class="adm-list">${list}</ul>
        <p>Esta acción no se puede deshacer.</p>`, { danger: true, ok: 'Borrar todo' });
      if (!ok) return;
      await api(`${url}?force=true`, { method: 'DELETE' });
    }
    toast('Eliminado');
    await admin.reload();
  } catch (err) {
    toast(err.message, 'err');
  }
}

export async function mergeGames(source, admin) {
  const target = await pickGame(`Fusionar «${source.name}» en…`);
  if (!target) return;
  if (target.id === source.id) return toast('Elige otro juego', 'err');
  const ok = await confirmDialog('Fusionar juegos', html`
    <p>Todas las sesiones y entradas de biblioteca de <strong>${source.name}</strong> pasarán a <strong>${target.name}</strong>, y <strong>${source.name}</strong> se eliminará.</p>
    <p>Los registros que coincidan con uno ya existente en el destino se descartan.</p>`, { danger: true, ok: 'Fusionar' });
  if (!ok) return;
  const r = await api(`/manage/games/${source.id}/merge`, jsonRequest('POST', { target_id: target.id }));
  const fmt = (o) => Object.entries(o).filter(([, v]) => v).map(([k, v]) => `${v} ${k}`).join(', ') || 'nada';
  toast(`Fusionado. Movido: ${fmt(r.moved)}. Descartado: ${fmt(r.dropped)}.`);
  await admin.reload();
}

export async function closeTimerNow(row, admin) {
  const ok = await confirmDialog('Cerrar timer', html`<p>Se cerrará el timer en curso de <strong>${row.user || row.user_id}</strong> con la hora actual.</p>`, { ok: 'Cerrar timer' });
  if (!ok) return;
  await api(`/manage/timers/${row.id}`, jsonRequest('PATCH', { end_time: toLocalISO(new Date()) }));
  toast('Timer cerrado');
  await admin.reload();
}

export function uploadAchievementImage(row, admin) {
  const input = document.createElement('input');
  input.type = 'file';
  input.accept = 'image/png,image/jpeg';
  input.addEventListener('change', async () => {
    const file = input.files[0];
    if (!file) return;
    try {
      const form = new FormData();
      form.append('file', file);
      await api(`/utils/achievement-image/${encodeURIComponent(row.key)}`, { method: 'PATCH', body: form });
      toast('Imagen actualizada');
      await admin.reload();
    } catch (err) {
      toast(err.message, 'err');
    }
  });
  input.click();
}

export function recomputeDialog() {
  const m = openModal(html`
    ${modalHeader('Recalcular estadísticas')}
    <form class="adm-form" novalidate>
      <p class="adm-sub">Vuelve a calcular estadísticas, logros y rankings a partir de las sesiones. Se ejecuta en segundo plano.</p>
      <label>Usuario
        <select class="adm-input" name="user"><option value="">Todos</option>${store.users.map((u) => html`<option value="${u.id}">${u.username}</option>`)}</select>
      </label>
      <label class="adm-check"><input type="checkbox" name="silent" checked /> Sin notificaciones (Telegram)</label>
      <div class="adm-sub">Ojo: con notificaciones desactivadas, los cambios de ranking se guardan igualmente y no se anunciarán después.</div>
      <div class="adm-actions"><button type="button" class="adm-btn" data-close>Cancelar</button><button class="adm-btn primary" type="submit">Recalcular</button></div>
    </form>`);
  m.el.querySelector('form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const form = e.currentTarget;
    try {
      await api('/manage/recompute', jsonRequest('POST', {
        user_id: form.user.value ? Number(form.user.value) : null,
        silent: form.silent.checked,
      }));
      m.close();
      toast('Recálculo en marcha');
    } catch (err) {
      toast(err.message, 'err');
    }
  });
}
