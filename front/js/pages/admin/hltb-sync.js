// HowLongToBeat sync UI: the average time to complete of the games.
// It replaces the stored times of the games it goes through, so launching it takes an explicit step with a typed phrase
// (the API enforces the phrase too). It spends no quota, but each game takes about 5 s, so the admin chooses which
// games to go through: all of them, the ones with no time, the ones whose time is not believable, or the most recent.
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
export const SCOPES = [
  ['all', 'Todos los juegos'],
  ['missing', 'Solo los que no tienen tiempo'],
  ['suspicious', 'Solo los que tienen un tiempo dudoso (más de 1.000 h)'],
  ['recent', 'Los jugados más recientemente'],
];
const DEFAULT_RECENT = 50;
const OVERWRITES = {
  all: 'Pisa los tiempos que ya hay, también los editados a mano: HowLongToBeat manda.',
  missing: 'Solo rellena juegos sin tiempo: no pisa ninguno.',
  suspicious: 'Pisa esos tiempos tan grandes con los de HowLongToBeat (si lo encuentra con claridad).',
  recent: 'Pisa los tiempos de esos juegos, también los editados a mano: HowLongToBeat manda.',
};

/** Entry point. onDone() runs when a sync finishes so the admin can refresh its data. */
export async function hltbSyncFlow({ onDone }) {
  const status = await api('/manage/hltb-sync/status');
  // A run in progress (or just finished) is shown instead of starting another one.
  if (['running', 'finished', 'cancelled'].includes(status.state)) return progress(onDone);
  return confirmStep(onDone);
}

const estimateStats = (est) => html`
  ${statTile('juegos a procesar', est.total_games)}
  ${statTile('duración aproximada (min)', Math.max(1, Math.ceil(est.estimated_seconds / 60)))}`;

/** What the form asks for, as the API takes it ({ scope, limit? }), or null while the number of recent games is not valid. */
export function scopeOf(scope, limitText) {
  if (scope !== 'recent') return { scope };
  const limit = Number(limitText);
  return Number.isInteger(limit) && limit >= 1 ? { scope, limit } : null;
}

async function confirmStep(onDone) {
  const m = openModal(html`
    ${modalHeader('Sincronizar tiempos con HowLongToBeat')}
    <form class="adm-form" novalidate>
      <p class="adm-sub">Busca cada juego en HowLongToBeat y guarda el tiempo medio para completarlo (la historia principal). Solo se aceptan coincidencias claras por nombre; las dudosas se listan al terminar, con sus horas, y no se tocan. Cada juego tarda unos 5 segundos: elige qué juegos revisar.</p>
      <label>Juegos<select class="adm-input" name="scope">
        ${SCOPES.map(([value, label]) => html`<option value="${value}">${label}</option>`)}
      </select></label>
      <label data-for="recent" hidden>¿Cuántos?<input class="adm-input" type="number" name="limit" min="1" step="1" value="${DEFAULT_RECENT}" /></label>
      <div class="adm-stats adm-stats-sm" id="hlEstimate"></div>
      <div class="adm-warn"><strong id="hlWarn"></strong> Un juego sin tiempo allí conserva el suyo. La deuda y «Justo a tiempo» se calculan con estos tiempos.</div>
      <label>Escribe <strong>${SYNC_PHRASE}</strong> para habilitar el botón<input class="adm-input" name="phrase" autocomplete="off" /></label>
      <div class="adm-error" role="alert"></div>
      <div class="adm-actions">
        <button type="button" class="adm-btn" data-close>Cancelar</button>
        <button class="adm-btn danger" type="submit" disabled>Lanzar sincronización</button>
      </div>
    </form>`, { wide: true });

  const form = m.el.querySelector('form');
  const el = form.elements;
  const go = form.querySelector('button[type=submit]');
  const error = form.querySelector('.adm-error');
  const typedOk = () => el.phrase.value.trim() === SYNC_PHRASE;
  const chosen = () => scopeOf(el.scope.value, el.limit.value);

  // The figures follow the choice: how many games it is and how long it takes (the API answers without asking HLTB).
  const refresh = async () => {
    form.querySelector('[data-for="recent"]').hidden = el.scope.value !== 'recent';
    form.querySelector('#hlWarn').textContent = OVERWRITES[el.scope.value];
    const picked = chosen();
    if (!picked) {
      error.textContent = 'El número de juegos debe ser un entero de 1 en adelante';
      go.disabled = true;
      return;
    }
    error.textContent = '';
    go.disabled = !typedOk();
    try {
      const params = new URLSearchParams(Object.entries(picked).map(([key, value]) => [key, String(value)]));
      mount(form.querySelector('#hlEstimate'), estimateStats(await api(`/manage/hltb-sync/estimate?${params}`)));
    } catch (err) {
      error.textContent = err.message;
    }
  };
  el.scope.addEventListener('change', refresh);
  el.limit.addEventListener('change', refresh);
  el.phrase.addEventListener('input', () => { go.disabled = !typedOk() || !chosen(); });
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const picked = chosen();
    if (!typedOk() || !picked) return;
    go.disabled = true;
    try {
      await api('/manage/hltb-sync/start', jsonRequest('POST', { confirm: SYNC_PHRASE, ...picked }));
      m.close();
      progress(onDone);
    } catch (err) {
      error.textContent = err.message;
      go.disabled = false;
    }
  });
  await refresh();
  el.phrase.focus();
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
