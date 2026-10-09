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

function progressView(s) {
  const running = s.state === 'running';
  const pct = s.total ? Math.round((s.processed / s.total) * 100) : 0;
  return html`
    <div class="adm-progress"><div style="width:${pct}%"></div></div>
    <div class="adm-progress-txt">${s.processed} / ${s.total} juegos${running && s.current ? ` · ${s.current}` : ''}</div>
    <div class="adm-stats adm-stats-sm">
      ${statTile('actualizados', s.updated)}
      ${statTile('sin cambios', s.unchanged)}
      ${statTile('ambiguos', s.ambiguous.length)}
      ${statTile('sin resultado', s.not_found.length)}
      ${statTile('sin tiempo', s.no_time.length)}
      ${statTile('errores', s.errors.length)}
    </div>
    ${running ? '' : html`<p class="adm-sub">${STOP_REASONS[s.stop_reason] || s.stop_reason || ''}</p>`}
    ${details('Ambiguos: ponles el tiempo a mano en Juegos → Editar (segundos)', s.ambiguous, (a) => html`
      <div class="adm-amb"><strong>${a.name}</strong>
        ${a.candidates.map((c) => html`<div class="adm-sub">${c.name}${c.year ? ` (${c.year})` : ''}: ${c.hours} h</div>`)}
      </div>`)}
    ${details('Sin resultado en HowLongToBeat', s.not_found, (n) => html`<div class="adm-sub">${n.name}</div>`)}
    ${details('Encontrados, pero sin tiempo de historia principal', s.no_time, (n) => html`<div class="adm-sub">${n.name}</div>`)}
    ${details('Errores', s.errors, (e) => html`<div class="adm-sub">${e.name}: ${e.error}</div>`)}
    <div class="adm-actions">
      ${running ? html`<button class="adm-btn danger" id="hlCancel">Cancelar sincronización</button>` : ''}
      <button class="adm-btn" id="hlClose">${running ? 'Ocultar' : 'Cerrar'}</button>
      ${running ? '' : html`<button class="adm-btn primary" id="hlAgain">Nueva sincronización</button>`}
    </div>`;
}

function progress(onDone) {
  let timer = null;
  const m = openModal(html`
    ${modalHeader('Sincronización con HowLongToBeat')}
    <div class="adm-body"><div class="loading-spinner">Cargando…</div></div>`, { wide: true, onClose: () => clearTimeout(timer) });
  const body = m.el.querySelector('.adm-body');

  const draw = (s) => {
    mount(body, progressView(s));
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
      // don't re-render under the admin while they are reading the candidates
      const reading = body.querySelector('.adm-details[open]');
      if (!reading || s.state !== 'running') draw(s);
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
