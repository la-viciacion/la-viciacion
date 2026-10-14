// Refresh one game from RAWG (metadata) and HLTB (average time) from the games list.
import { api, jsonRequest } from '../../lib/api.js';
import { html, mount } from '../../lib/html.js';
import { modalHeader, openModal } from '../../ui/modal.js';
import { toast } from '../../ui/toast.js';
import { confirmDialog } from './dialogs.js';

const FIELDS = {
  rawg_id: 'ID de RAWG', slug: 'slug', dev: 'desarrolladora', release_date: 'lanzamiento',
  image_url: 'imagen', genres: 'géneros', tags: 'etiquetas', steam_id: 'Steam ID',
};

const hours = (seconds) => `${Math.round(seconds / 360) / 10} h`;

export function rawgLine(r) {
  switch (r.status) {
    case 'updated': return html`✓ Actualizado: ${r.changed.map((f) => FIELDS[f] || f).join(', ')}.`;
    case 'unchanged': return html`✓ Ya estaba al día.`;
    case 'not_found': return html`No lo encuentra en RAWG.`;
    case 'duplicate': return html`Ese juego de RAWG ya lo tiene «${r.other_name}».`;
    case 'ambiguous': return html`Coincidencia dudosa, elige la correcta:
      <div class="adm-amb-candidates">${r.candidates.map((c) => html`<button class="adm-btn sm" data-use="${c.rawg_id}" title="${(c.platforms || []).join(', ')}">${c.name}${c.released ? ` (${c.released.slice(0, 4)})` : ''}</button>`)}</div>`;
    default: return html`Error: ${r.error}`;
  }
}

export function hltbLine(r) {
  switch (r.status) {
    case 'updated': return html`✓ Tiempo actualizado: ${hours(r.seconds)}.`;
    case 'unchanged': return html`✓ El tiempo ya era ${hours(r.seconds)}.`;
    case 'no_time': return html`HLTB no tiene tiempo para este juego.`;
    case 'not_found': return html`No lo encuentra en HLTB.`;
    case 'ambiguous': return html`Coincidencia dudosa (no se ha cambiado nada). Pon el tiempo a mano al editar el juego:
      <ul class="adm-list">${r.candidates.map((c) => html`<li>${c.name}${c.year ? ` (${c.year})` : ''}: ${c.hours} h</li>`)}</ul>`;
    default: return html`Error: ${r.error}`;
  }
}

export async function resyncGame(game, admin) {
  const ok = await confirmDialog(
    `Resincronizar · ${game.name}`,
    html`<p>Se consultarán RAWG y HowLongToBeat. Los datos que den <strong>sustituyen</strong> a los guardados (el nombre no se toca y nada se deja en blanco).</p>`,
    { ok: 'Resincronizar' },
  );
  if (!ok) return;
  toast('Consultando RAWG y HLTB…');
  const result = await api(`/manage/games/${game.id}/resync`, { method: 'POST' });
  const m = openModal(html`
    ${modalHeader(`Resincronizado · ${game.name}`)}
    <div class="adm-body" id="rsBody"></div>
    <div class="adm-actions"><button class="adm-btn primary" data-close>Cerrar</button></div>`, { onClose: () => admin.reload() });
  const body = m.el.querySelector('#rsBody');
  const draw = (rawg) => mount(body, html`
    <p><strong>RAWG</strong><br />${rawgLine(rawg)}</p>
    <p><strong>HowLongToBeat</strong><br />${hltbLine(result.hltb)}</p>`);
  draw(result.rawg);
  body.addEventListener('click', async (e) => {
    const button = e.target.closest('[data-use]');
    if (!button) return;
    button.disabled = true;
    try {
      const r = await api('/manage/rawg-sync/apply', jsonRequest('POST', { game_id: game.id, rawg_id: Number(button.dataset.use), overwrite: true }));
      draw({ status: r.changed.length ? 'updated' : 'unchanged', changed: r.changed });
    } catch (err) {
      toast(err.message, 'err');
      button.disabled = false;
    }
  });
}
