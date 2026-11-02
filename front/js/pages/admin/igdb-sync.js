// IGDB link UI: gives each game of the catalogue the id it has in IGDB (the backup source of the game search).
// It writes nothing else and only on games that have no id yet, so it asks for no phrase. It goes in batches the admin
// sizes (the games a batch could not decide stay pending and come back in the next one); each game takes a second or so.
import { api, jsonRequest } from '../../lib/api.js';
import { html, mount } from '../../lib/html.js';
import { modalHeader, openModal } from '../../ui/modal.js';
import { toast } from '../../ui/toast.js';
import { statTile } from './components.js';

const STOP_REASONS = {
  completed: 'Terminada: se han procesado todos los juegos de la tanda.',
  cancelled: 'Cancelada manualmente.',
  errors: 'Detenida por errores consecutivos de IGDB. Prueba de nuevo más tarde.',
};

/** The number of games of the batch as the API takes it ({ max_games } or {} for all of them), or null when it is not valid. */
export function batchOf(text) {
  if (String(text).trim() === '') return {};
  const max = Number(text);
  return Number.isInteger(max) && max >= 1 ? { max_games: max } : null;
}

/** Entry point. onDone() runs when a run finishes so the admin can refresh its data. */
export async function igdbSyncFlow({ onDone }) {
  const status = await api('/manage/igdb-sync/status');
  // A run in progress (or just finished) is shown instead of starting another one.
  if (['running', 'finished', 'cancelled'].includes(status.state)) return progress(onDone);
  return confirmStep(onDone);
}

const estimateStats = (est) => html`
  ${statTile('juegos sin enlazar', est.pending_games)}
  ${statTile('juegos de esta tanda', est.games)}
  ${statTile('duración aproximada (min)', Math.max(1, Math.ceil(est.estimated_seconds / 60)))}`;

async function confirmStep(onDone) {
  const m = openModal(html`
    ${modalHeader('Enlazar juegos con IGDB')}
    <form class="adm-form" novalidate>
      <p class="adm-sub">Busca cada juego que aún no tiene id de IGDB y se lo guarda, solo cuando la coincidencia es segura: el mismo juego de Steam, o el mismo nombre con un año que cuadre. Los dudosos se listan al terminar para elegir a mano. No se cambia ningún otro dato del juego.</p>
      <label>¿Cuántos juegos en esta tanda? (vacío = todos)<input class="adm-input" type="number" name="max" min="1" step="1" placeholder="todos" value="50" /></label>
      <div class="adm-stats adm-stats-sm" id="igEstimate"></div>
      <div class="adm-error" role="alert"></div>
      <div class="adm-actions">
        <button type="button" class="adm-btn" data-close>Cancelar</button>
        <button class="adm-btn primary" type="submit">Enlazar</button>
      </div>
    </form>`, { wide: true });

  const form = m.el.querySelector('form');
  const el = form.elements;
  const go = form.querySelector('button[type=submit]');
  const error = form.querySelector('.adm-error');

  const refresh = async () => {
    const picked = batchOf(el.max.value);
    if (!picked) {
      error.textContent = 'El número de juegos debe ser un entero de 1 en adelante';
      go.disabled = true;
      return;
    }
    error.textContent = '';
    go.disabled = false;
    try {
      const params = new URLSearchParams(Object.entries(picked).map(([key, value]) => [key, String(value)]));
      mount(form.querySelector('#igEstimate'), estimateStats(await api(`/manage/igdb-sync/estimate?${params}`)));
    } catch (err) {
      error.textContent = err.message;
    }
  };
  el.max.addEventListener('change', refresh);
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const picked = batchOf(el.max.value);
    if (!picked) return;
    go.disabled = true;
    try {
      await api('/manage/igdb-sync/start', jsonRequest('POST', picked));
      m.close();
      progress(onDone);
    } catch (err) {
      error.textContent = err.message;
      go.disabled = false;
    }
  });
  await refresh();
  el.max.focus();
}

const details = (title, items, row) => (items.length
  ? html`<details class="adm-details"><summary>${title} (${items.length})</summary>${items.map(row)}</details>`
  : '');

/** Minutes the run still needs at the pace seen since the first poll, or null until two games give a pace.
 * `first` is { at: ms, done: games processed } taken at the first poll, `now` in ms. */
export function minutesLeft(first, s, now) {
  const done = s.processed - first.done;
  const seconds = (now - first.at) / 1000;
  if (done < 2 || seconds <= 0) return null;
  return Math.max(1, Math.ceil(((s.total - s.processed) * seconds) / done / 60));
}

/** The figures of the run: always refreshed, whatever the admin is doing. */
function headView(s, left = null) {
  const running = s.state === 'running';
  const pct = s.total ? Math.round((s.processed / s.total) * 100) : 0;
  return html`
    <div class="adm-progress"><div style="width:${pct}%"></div></div>
    <div class="adm-progress-txt">${s.processed} / ${s.total} juegos${running && s.current ? ` · ${s.current}` : ''}${running && left ? ` · quedan unos ${left} min` : ''}</div>
    <div class="adm-stats adm-stats-sm">
      ${statTile('enlazados', s.linked)}
      ${statTile('dudosos', s.ambiguous.length)}
      ${statTile('sin resultado', s.not_found.length)}
      ${statTile('duplicados', s.duplicates.length)}
      ${statTile('errores', s.errors.length)}
    </div>
    ${running ? '' : html`<p class="adm-sub">${STOP_REASONS[s.stop_reason] || s.stop_reason || ''}</p>`}`;
}

/** What the run could not decide: redrawn only when it changes and never under an admin who has one open. */
const listsView = (s) => html`
  ${details('Dudosos: elige la coincidencia correcta', s.ambiguous, (a) => html`
    <div class="adm-amb" data-game="${a.game_id}"><strong>${a.name}</strong>
      ${a.candidates.map((c) => html`<button class="adm-btn sm" data-use="${c.igdb_id}" title="${(c.platforms || []).join(', ')}">${c.name}${c.year ? ` (${c.year})` : ''}</button>`)}
    </div>`)}
  ${details('Duplicados (ese id de IGDB ya lo tiene otro juego: fusiónalos)', s.duplicates, (d) => html`<div class="adm-sub">«${d.name}» ↔ «${d.other_name}» (IGDB ${d.igdb_id})</div>`)}
  ${details('Sin resultado en IGDB', s.not_found, (n) => html`<div class="adm-sub">${n.name}</div>`)}
  ${details('Errores', s.errors, (e) => html`<div class="adm-sub">${e.name}: ${e.error}</div>`)}`;

const actionsView = (s) => html`
  <div class="adm-actions">
    ${s.state === 'running' ? html`<button class="adm-btn danger" id="igCancel">Cancelar enlazado</button>` : ''}
    <button class="adm-btn" id="igClose">${s.state === 'running' ? 'Ocultar' : 'Cerrar'}</button>
    ${s.state === 'running' ? '' : html`<button class="adm-btn primary" id="igAgain">Otra tanda</button>`}
  </div>`;

function progress(onDone) {
  let timer = null;
  let drawnLists = null; // the sizes of the lists on screen: they are redrawn only when one grows
  let first = null; // where the run was at the first poll, to tell how fast it goes
  const m = openModal(html`
    ${modalHeader('Enlazado con IGDB')}
    <div class="adm-body">
      <div id="igHead"><div class="loading-spinner">Cargando…</div></div>
      <div id="igLists"></div>
      <div id="igActions"></div>
    </div>`, { wide: true, onClose: () => clearTimeout(timer) });
  const body = m.el.querySelector('.adm-body');
  const part = (id) => body.querySelector(`#${id}`);

  const draw = (s, { lists }) => {
    first ||= { at: Date.now(), done: s.processed };
    mount(part('igHead'), headView(s, minutesLeft(first, s, Date.now())));
    mount(part('igActions'), actionsView(s));
    const sizes = [s.ambiguous, s.duplicates, s.not_found, s.errors].map((list) => list.length).join();
    if (lists && sizes !== drawnLists) {
      mount(part('igLists'), listsView(s));
      drawnLists = sizes;
    }
    body.querySelector('#igClose').addEventListener('click', () => m.close());
    // The last run stays on screen after it ends (its doubtful games are still to be resolved), so the next batch starts from here.
    body.querySelector('#igAgain')?.addEventListener('click', () => {
      m.close();
      confirmStep(onDone).catch((err) => toast(err.message, 'err'));
    });
    body.querySelector('#igCancel')?.addEventListener('click', async () => {
      await api('/manage/igdb-sync/cancel', { method: 'POST' });
      toast('Cancelando…');
    });
  };

  const tick = async () => {
    if (!m.el.isConnected) return;
    try {
      const s = await api('/manage/igdb-sync/status');
      if (!m.el.isConnected) return;
      // A list is not redrawn under the admin who is reading it (it would close it), but the bar keeps moving.
      const reading = part('igLists').querySelector('.adm-details[open]');
      draw(s, { lists: !reading || s.state !== 'running' });
      if (s.state === 'running') {
        timer = setTimeout(tick, 2000);
      } else {
        toast('Enlazado terminado');
        onDone();
      }
    } catch (err) {
      mount(body, html`<div class="adm-error">${err.message}</div>`);
    }
  };

  // Resolve a doubtful game by hand (one IGDB request).
  body.addEventListener('click', async (e) => {
    const button = e.target.closest('[data-use]');
    if (!button) return;
    const row = button.closest('.adm-amb');
    button.disabled = true;
    try {
      await api('/manage/igdb-sync/apply', jsonRequest('POST', { game_id: row.dataset.game, igdb_id: Number(button.dataset.use) }));
      mount(row, html`<span class="adm-sub">✓ ${row.querySelector('strong').textContent} enlazado</span>`);
    } catch (err) {
      toast(err.message, 'err');
      button.disabled = false;
    }
  });
  tick();
}
