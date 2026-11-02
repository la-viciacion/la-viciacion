// Refresh one game from RAWG and IGDB (metadata) and HLTB (average time) from the games list.
import { api, jsonRequest } from '../../lib/api.js';
import { html, mount } from '../../lib/html.js';
import { modalHeader, openModal } from '../../ui/modal.js';
import { toast } from '../../ui/toast.js';
import { confirmDialog } from './dialogs.js';

const FIELDS = {
  rawg_id: 'ID de RAWG', slug: 'slug', dev: 'desarrolladora', release_date: 'lanzamiento',
  image_url: 'imagen', genres: 'géneros', tags: 'etiquetas', steam_id: 'Steam ID',
  parent_rawg_id: 'juego base (DLC)',
  igdb_id: 'ID de IGDB', igdb_slug: 'enlace de IGDB', themes: 'temas', keywords: 'palabras clave', franchises: 'franquicias', collections: 'colecciones',
  is_dlc: 'marca de DLC', parent_game_id: 'juego base (DLC)',
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

export function igdbLine(r) {
  switch (r.status) {
    case 'updated': return html`✓ Actualizado: ${r.changed.map((f) => FIELDS[f] || f).join(', ')}.`;
    case 'unchanged': return html`✓ Ya estaba al día.`;
    case 'not_found': return html`No lo encuentra en IGDB.`;
    case 'duplicate': return html`Ese juego de IGDB ya lo tiene «${r.other_name}».`;
    case 'ambiguous': return html`Coincidencia dudosa, elige la correcta:
      <div class="adm-amb-candidates">${r.candidates.map((c) => html`<button class="adm-btn sm" data-use-igdb="${c.igdb_id}" title="${(c.platforms || []).join(', ')}">${c.name}${c.year ? ` (${c.year})` : ''}</button>`)}</div>`;
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
    html`<p>Se consultarán IGDB, RAWG y HowLongToBeat. Los datos que den <strong>sustituyen</strong> a los guardados (el nombre no se toca y nada se deja en blanco). Si los dos dan el mismo dato, manda IGDB.</p>`,
    { ok: 'Resincronizar' },
  );
  if (!ok) return;
  // The window is up from the start: the sources take several seconds and the admin must see that something is happening
  const m = openModal(html`
    <div id="rsHead">${modalHeader(`Resincronizando · ${game.name}`)}</div>
    <div class="adm-body" id="rsBody">
      <p class="adm-sub">Consultando IGDB, RAWG y HowLongToBeat. Puede tardar unos segundos.</p>
      <div class="adm-indeterminate" role="progressbar" aria-label="Resincronizando"></div>
    </div>
    <div class="adm-actions" id="rsActions"></div>`, { onClose: () => admin.reload() });
  const head = m.el.querySelector('#rsHead');
  const body = m.el.querySelector('#rsBody');
  const closeButton = html`<button class="adm-btn primary" data-close>Cerrar</button>`;
  let result;
  try {
    result = await api(`/manage/games/${game.id}/resync`, { method: 'POST' });
  } catch (err) {
    mount(head, modalHeader(`No se ha podido resincronizar · ${game.name}`));
    mount(body, html`<div class="adm-error" role="alert">${err.message}</div>`);
    mount(m.el.querySelector('#rsActions'), closeButton);
    return;
  }
  mount(head, modalHeader(`Resincronizado · ${game.name}`));
  mount(m.el.querySelector('#rsActions'), closeButton);
  const shown = { ...result };
  const draw = () => mount(body, html`
    <p><strong>IGDB</strong><br />${igdbLine(shown.igdb)}</p>
    <p><strong>RAWG</strong><br />${rawgLine(shown.rawg)}</p>
    <p><strong>HowLongToBeat</strong><br />${hltbLine(shown.hltb)}</p>`);
  draw();
  body.addEventListener('click', async (e) => {
    const button = e.target.closest('[data-use], [data-use-igdb]');
    if (!button) return;
    const igdb = button.dataset.useIgdb != null;
    button.disabled = true;
    try {
      const r = igdb
        ? await api('/manage/igdb-sync/apply', jsonRequest('POST', { game_id: game.id, igdb_id: Number(button.dataset.useIgdb), overwrite: true }))
        : await api('/manage/rawg-sync/apply', jsonRequest('POST', { game_id: game.id, rawg_id: Number(button.dataset.use), overwrite: true }));
      shown[igdb ? 'igdb' : 'rawg'] = { status: r.changed.length ? 'updated' : 'unchanged', changed: r.changed };
      draw();
    } catch (err) {
      toast(err.message, 'err');
      button.disabled = false;
    }
  });
}
