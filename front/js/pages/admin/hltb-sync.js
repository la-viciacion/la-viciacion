// HowLongToBeat sync UI: the average time to complete of every game.
// It replaces the stored times, so launching it takes an explicit step with a typed phrase
// (the API enforces the phrase too). It spends no quota, so there are no options.
import { api, jsonRequest } from '../../lib/api.js';
import { html, mount } from '../../lib/html.js';
import { modalHeader, openModal } from '../../ui/modal.js';
import { toast } from '../../ui/toast.js';
import { statTile } from './components.js';

const SYNC_PHRASE = 'SINCRONIZAR';
const STOP_REASONS = {
  completed: 'Terminada: se han procesado todos los juegos.',
  cancelled: 'Cancelada manualmente.',
  errors: 'Detenida por errores consecutivos de HowLongToBeat. Prueba de nuevo más tarde.',
};

/** Entry point. onDone() runs when a sync finishes so the admin can refresh its data. */
export async function hltbSyncFlow({ onDone }) {
  const status = await api('/manage/hltb-sync/status');
  // A run in progress (or just finished) is shown instead of starting another one.
  if (['running', 'finished', 'cancelled'].includes(status.state)) return progress(onDone);
  return confirmStep(onDone);
}

async function confirmStep(onDone) {
  const est = await api('/manage/hltb-sync/estimate');
  const m = openModal(html`
    ${modalHeader('Sincronizar tiempos con HowLongToBeat')}
    <form class="adm-form" novalidate>
      <p class="adm-sub">Busca cada juego en HowLongToBeat y guarda el tiempo medio para completarlo (la historia principal). Solo se aceptan coincidencias claras por nombre; las dudosas se listan al terminar, con sus horas, y no se tocan.</p>
      <div class="adm-stats adm-stats-sm">
        ${statTile('juegos a procesar', est.total_games)}
        ${statTile('duración aproximada (min)', Math.max(1, Math.ceil(est.estimated_seconds / 60)))}
      </div>
      <div class="adm-warn"><strong>Pisa los tiempos que ya hay</strong>, también los editados a mano: HowLongToBeat manda. Un juego sin tiempo allí conserva el suyo. La deuda y «Justo a tiempo» se calculan con estos tiempos.</div>
      <label>Escribe <strong>${SYNC_PHRASE}</strong> para habilitar el botón<input class="adm-input" name="phrase" autocomplete="off" /></label>
      <div class="adm-error" role="alert"></div>
      <div class="adm-actions">
        <button type="button" class="adm-btn" data-close>Cancelar</button>
        <button class="adm-btn danger" type="submit" disabled>Lanzar sincronización</button>
      </div>
    </form>`, { wide: true });

  const form = m.el.querySelector('form');
  const go = form.querySelector('button[type=submit]');
  const typedOk = () => form.phrase.value.trim() === SYNC_PHRASE;
  form.phrase.addEventListener('input', () => { go.disabled = !typedOk(); });
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!typedOk()) return;
    go.disabled = true;
    try {
      await api('/manage/hltb-sync/start', jsonRequest('POST', { confirm: SYNC_PHRASE }));
      m.close();
      progress(onDone);
    } catch (err) {
      form.querySelector('.adm-error').textContent = err.message;
      go.disabled = false;
    }
  });
  form.phrase.focus();
}

const details = (title, items, row) => (items.length
  ? html`<details class="adm-details"><summary>${title} (${items.length})</summary>${items.map(row)}</details>`
  : '');

/** Minutes the run still needs at the pace seen since the first poll, or null until two games give a pace.
 * `first` is { at: ms, done: games processed } taken at the first poll (the browser's own clock: the server's is not
 * the same one), `now` in ms. */
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
      ${statTile('actualizados', s.updated)}
      ${statTile('sin cambios', s.unchanged)}
      ${statTile('ambiguos', s.ambiguous.length)}
      ${statTile('sin resultado', s.not_found.length)}
      ${statTile('sin tiempo', s.no_time.length)}
      ${statTile('errores', s.errors.length)}
    </div>
    ${running ? '' : html`<p class="adm-sub">${STOP_REASONS[s.stop_reason] || s.stop_reason || ''}</p>`}`;
}

/** What the run could not decide: redrawn only when it changes and never under an admin who has one open. */
const listsView = (s) => html`
  ${details('Ambiguos: ponles el tiempo a mano en Juegos → Editar (segundos)', s.ambiguous, (a) => html`
    <div class="adm-amb"><strong>${a.name}</strong>
      ${a.candidates.map((c) => html`<div class="adm-sub">${c.name}${c.year ? ` (${c.year})` : ''}: ${c.hours} h</div>`)}
    </div>`)}
  ${details('Sin resultado en HowLongToBeat', s.not_found, (n) => html`<div class="adm-sub">${n.name}</div>`)}
  ${details('Encontrados, pero sin tiempo de historia principal', s.no_time, (n) => html`<div class="adm-sub">${n.name}</div>`)}
  ${details('Errores', s.errors, (e) => html`<div class="adm-sub">${e.name}: ${e.error}</div>`)}`;

const actionsView = (s) => html`
  <div class="adm-actions">
    ${s.state === 'running' ? html`<button class="adm-btn danger" id="hlCancel">Cancelar sincronización</button>` : ''}
    <button class="adm-btn" id="hlClose">${s.state === 'running' ? 'Ocultar' : 'Cerrar'}</button>
    ${s.state === 'running' ? '' : html`<button class="adm-btn primary" id="hlAgain">Nueva sincronización</button>`}
  </div>`;

function progress(onDone) {
  let timer = null;
  let drawnLists = null; // the sizes of the lists on screen: they are redrawn only when one grows
  let first = null; // where the run was at the first poll, to tell how fast it goes
  const m = openModal(html`
    ${modalHeader('Sincronización con HowLongToBeat')}
    <div class="adm-body">
      <div id="hlHead"><div class="loading-spinner">Cargando…</div></div>
      <div id="hlLists"></div>
      <div id="hlActions"></div>
    </div>`, { wide: true, onClose: () => clearTimeout(timer) });
  const body = m.el.querySelector('.adm-body');
  const part = (id) => body.querySelector(`#${id}`);

  const draw = (s, { lists }) => {
    first ||= { at: Date.now(), done: s.processed };
    mount(part('hlHead'), headView(s, minutesLeft(first, s, Date.now())));
    mount(part('hlActions'), actionsView(s));
    const sizes = [s.ambiguous, s.not_found, s.no_time, s.errors].map((list) => list.length).join();
    if (lists && sizes !== drawnLists) {
      mount(part('hlLists'), listsView(s));
      drawnLists = sizes;
    }
    body.querySelector('#hlClose').addEventListener('click', () => m.close());
    // The last run stays on screen after it ends (its ambiguous games are still to be looked at), so a new one starts from here.
    body.querySelector('#hlAgain')?.addEventListener('click', () => {
      m.close();
      confirmStep(onDone).catch((err) => toast(err.message, 'err'));
    });
    body.querySelector('#hlCancel')?.addEventListener('click', async () => {
      await api('/manage/hltb-sync/cancel', { method: 'POST' });
      toast('Cancelando…');
    });
  };

  const tick = async () => {
    if (!m.el.isConnected) return;
    try {
      const s = await api('/manage/hltb-sync/status');
      if (!m.el.isConnected) return;
      // The figures move every time; a list is not redrawn under the admin who is reading it (it would close it),
      // but that must not stop the bar: it used to, and a run looked stuck until it was cancelled.
      const reading = part('hlLists').querySelector('.adm-details[open]');
      draw(s, { lists: !reading || s.state !== 'running' });
      if (s.state === 'running') {
        timer = setTimeout(tick, 2000);
      } else {
        toast('Sincronización terminada');
        onDone();
      }
    } catch (err) {
      mount(body, html`<div class="adm-error">${err.message}</div>`);
    }
  };
  tick();
}
