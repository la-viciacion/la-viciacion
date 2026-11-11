// Admin dialogs and one-off actions (confirm, game picker, delete...).
// Everything that changes data takes `admin` = { reload } to refresh the view.
import { api, jsonRequest } from '../../lib/api.js';
import { formatDate, toLocalISO } from '../../lib/format.js';
import { html, mount } from '../../lib/html.js';
import { platformName } from '../../lib/platforms.js';
import { modalHeader, openModal } from '../../ui/modal.js';
import { toast } from '../../ui/toast.js';

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

/** Who has a game in their library and who wishes for it (GET /manage/games/{id}/people); the list the admin asked for (`first`) goes on top. */
export async function showGamePeople(game, first = 'players') {
  const { players, wishes } = await api(`/manage/games/${encodeURIComponent(game.id)}/people`);
  const who = (p) => html`<a class="adm-link" href="#/player/${p.user_id}" data-close>${p.name}</a>${p.is_active ? '' : html` <span class="adm-sub">(inactivo)</span>`}`;
  const owned = (p) => p.entries.map((e) => `${e.platform ? platformName(e.platform) : 'sin plataforma'} ${e.season}`).join(', ');
  const section = (title, rows, line) => html`
    <section class="adm-people">
      <h4>${title} <span class="adm-sub">${rows.length}</span></h4>
      ${rows.length ? html`<ul class="adm-list">${rows.map((p) => html`<li>${who(p)} <span class="adm-sub">· ${line(p)}</span></li>`)}</ul>` : html`<p class="adm-sub">Nadie.</p>`}
    </section>`;
  const parts = [
    section('Lo tienen en su biblioteca', players, owned),
    section('Lo desean', wishes, (p) => `desde el ${formatDate(p.added_at)}`),
  ];
  openModal(html`
    ${modalHeader(game.name)}
    <div class="adm-body adm-people-body">${first === 'wishes' ? parts.reverse() : parts}</div>
    <div class="adm-actions"><button class="adm-btn" data-close>Cerrar</button></div>`);
}

/** Delete a row; rows with dependants come back as 409 + counts and need a second, explicit confirmation. */
export async function deleteRow(entity, row, admin) {
  const url = `${entity.endpoint}/${row.id}`;
  const verb = entity.deleteLabel || 'Borrar';
  const title = `${verb} · ${entity.name(row)}`;
  try {
    try {
      const ok = await confirmDialog(title, html`<p>Esta acción no se puede deshacer.</p>${entity.deleteNote ? html`<p>${entity.deleteNote}</p>` : ''}`, { danger: true, ok: verb });
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

export async function closeTimerNow(row, admin) {
  const ok = await confirmDialog('Cerrar timer', html`<p>Se cerrará el timer en curso de <strong>${row.user || row.user_id}</strong> con la hora actual.</p>`, { ok: 'Cerrar timer' });
  if (!ok) return;
  await api(`/manage/timers/${row.id}`, jsonRequest('PATCH', { end_time: toLocalISO(new Date()) }));
  toast('Timer cerrado');
  await admin.reload();
}
