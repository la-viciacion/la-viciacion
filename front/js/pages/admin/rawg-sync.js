// RAWG catalogue sync UI.
// The sync is intensive (it spends the monthly RAWG quota), so launching it
// takes two explicit approvals: an options/estimate step and a typed phrase.
// The API enforces the phrase too.
import { api, jsonRequest } from '../../lib/api.js';
import { html, mount } from '../../lib/html.js';
import { modalHeader, openModal } from '../../ui/modal.js';
import { toast } from '../../ui/toast.js';
import { statTile } from './components.js';

const SYNC_PHRASE = 'SINCRONIZAR';
const MAX_CALLS_LIMIT = 20000;
const STOP_REASONS = {
  completed: 'Terminada: se han procesado todos los juegos pendientes.',
  max_calls: 'Detenida: se alcanzó el tope de llamadas. Puedes lanzarla otra vez para continuar con los que falten.',
  cancelled: 'Cancelada manualmente.',
  errors: 'Detenida por errores consecutivos de RAWG. Prueba de nuevo más tarde.',
};

const number = (n) => n.toLocaleString('es-ES');

/** Entry point. onDone() runs when a sync finishes so the admin can refresh its data. */
export async function rawgSyncFlow({ onDone }) {
  const status = await api('/manage/rawg-sync/status');
  // A run in progress (or just finished) is shown instead of starting another one.
  if (['running', 'finished', 'cancelled'].includes(status.state)) return progress(onDone);
  return optionsStep(onDone);
}

const estimateStats = (est) => html`
  ${statTile(`juegos por procesar de ${est.total_games}`, est.pending_games)}
  ${statTile('llamadas a RAWG (máx.)', `~${est.estimated_calls}`)}
  ${statTile(`de la cuota mensual (${number(est.monthly_quota)})`, `${((est.estimated_calls / est.monthly_quota) * 100).toFixed(1)}%`)}`;

/** The number of games the admin limited the run to, or null for all of them (blank or invalid). */
const gamesLimit = (form) => {
  const n = Number(form.games.value);
  return form.games.value.trim() !== '' && Number.isInteger(n) && n >= 1 ? n : null;
};

async function optionsStep(onDone) {
  const est = await api('/manage/rawg-sync/estimate');
  const m = openModal(html`
    ${modalHeader('Sincronizar juegos con RAWG')}
    <form class="adm-form" novalidate>
      <p class="adm-sub">Busca cada juego en RAWG para guardar su <strong>ID</strong> y completar los datos que falten (desarrolladora, géneros, fecha, imagen, slug y Steam ID). El nombre nunca se modifica.</p>
      <div class="adm-stats adm-stats-sm" id="rgEstimate">${estimateStats(est)}</div>
      <label>Tope de llamadas para esta ejecución
        <input class="adm-input" type="number" name="max" min="1" max="${MAX_CALLS_LIMIT}" value="${Math.min(2000, Math.max(50, est.estimated_calls))}" />
      </label>
      <label>Juegos a procesar (vacío = todos los pendientes)
        <input class="adm-input" type="number" name="games" min="1" step="1" placeholder="Todos" />
      </label>
      <label class="adm-check"><input type="checkbox" name="overwrite" /> Sincronizar todo (resincronización completa: pisa los cambios hechos a mano)</label>
      <div class="adm-sub">Por defecto se procesan primero los juegos con más sesiones. Si limitas el número de juegos, se toman los primeros por orden alfabético, sin más criterio. Por defecto solo se tienen en cuenta los que les falta información básica (ID de RAWG, etiquetas, géneros, imagen o slug; si RAWG no tiene las etiquetas de un juego se anota y no se vuelve a pedir, y la desarrolladora y la fecha no cuentan) y solo se rellenan campos vacíos, así que los que ya la tengan no cuentan en la siguiente ejecución. Con «Sincronizar todo» entran todos los juegos, de modo que un límite repetiría siempre los mismos. Duración aproximada con los datos de arriba: ~${Math.ceil((est.estimated_calls * 0.5) / 60)} min.</div>
      <div class="adm-error" role="alert"></div>
      <div class="adm-actions">
        <button type="button" class="adm-btn" data-close>Cancelar</button>
        <button class="adm-btn primary" type="submit" ${est.pending_games ? '' : html`disabled`}>${est.pending_games ? 'Continuar…' : 'Nada pendiente'}</button>
      </div>
    </form>`, { wide: true });

  const form = m.el.querySelector('form');
  // The figures above follow the limit and the "all" switch; the call cap stays the admin's own choice.
  const refreshEstimate = async () => {
    const params = new URLSearchParams({ overwrite: form.overwrite.checked });
    const limit = gamesLimit(form);
    if (limit) params.set('max_games', limit);
    try {
      mount(m.el.querySelector('#rgEstimate'), estimateStats(await api(`/manage/rawg-sync/estimate?${params}`)));
    } catch (err) {
      m.el.querySelector('.adm-error').textContent = err.message;
    }
  };
  form.games.addEventListener('change', refreshEstimate);
  form.overwrite.addEventListener('change', refreshEstimate);

  form.addEventListener('submit', (e) => {
    e.preventDefault();
    const max = Number(form.max.value);
    if (!(max >= 1 && max <= MAX_CALLS_LIMIT)) {
      m.el.querySelector('.adm-error').textContent = `El tope debe estar entre 1 y ${MAX_CALLS_LIMIT}`;
      return;
    }
    if (form.games.value.trim() !== '' && gamesLimit(form) === null) {
      m.el.querySelector('.adm-error').textContent = 'El número de juegos debe ser un entero de 1 en adelante (o vacío para todos)';
      return;
    }
    const overwrite = form.overwrite.checked;
    const games = gamesLimit(form);
    m.close();
    confirmStep(max, overwrite, games, onDone);
  });
}

function confirmStep(max, overwrite, games, onDone) {
  const m = openModal(html`
    ${modalHeader('⚠️ Segunda confirmación')}
    <form class="adm-form" novalidate>
      <div class="adm-warn">
        <strong>Este es un proceso intensivo.</strong> Hará hasta <strong>${number(max)}</strong> llamadas a la API de RAWG,
        que cuentan contra el límite mensual del plan gratuito (20.000). Tarda varios minutos y modifica datos de ${games ? html`los primeros <strong>${number(games)}</strong> juegos por orden alfabético` : 'juegos'}${overwrite ? html`, <strong>resincronizándolos todos y sobrescribiendo los valores existentes</strong>` : ''}.
        <br/>Lánzalo solo en casos de extrema necesidad.
      </div>
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
      await api('/manage/rawg-sync/start', jsonRequest('POST', { confirm: SYNC_PHRASE, max_calls: max, overwrite, max_games: games }));
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

/** The figures of the run: always refreshed, whatever the admin is doing. */
function headView(s) {
  const running = s.state === 'running';
  const pct = s.total ? Math.round((s.processed / s.total) * 100) : 0;
  return html`
    <div class="adm-progress"><div style="width:${pct}%"></div></div>
    <div class="adm-progress-txt">${s.processed} / ${s.total} juegos · ${s.calls} / ${s.max_calls} llamadas${running && s.current ? ` · ${s.current}` : ''}</div>
    <div class="adm-stats adm-stats-sm">
      ${statTile('actualizados', s.updated)}
      ${statTile('ambiguos', s.ambiguous.length)}
      ${statTile('sin resultado', s.not_found.length)}
      ${statTile('errores', s.errors.length)}
    </div>
    ${running ? '' : html`<p class="adm-sub">${STOP_REASONS[s.stop_reason] || s.stop_reason || ''}</p>`}`;
}

/** What the run could not decide: redrawn only when it changes and never under an admin who has one open. */
const listsView = (s) => html`
  ${details('Ambiguos: elige la coincidencia correcta', s.ambiguous, (a) => html`
    <div class="adm-amb" data-game="${a.game_id}"><strong>${a.name}</strong>
      ${a.candidates.map((c) => html`<button class="adm-btn sm" data-use="${c.rawg_id}" title="${(c.platforms || []).join(', ')}">${c.name}${c.released ? ` (${c.released.slice(0, 4)})` : ''}</button>`)}
    </div>`)}
  ${details('Duplicados (mismo ID de RAWG en otro juego: fusiónalos)', s.duplicates, (d) => html`<div class="adm-sub">«${d.name}» ↔ «${d.other_name}» (RAWG ${d.rawg_id})</div>`)}
  ${details('Sin resultado en RAWG', s.not_found, (n) => html`<div class="adm-sub">${n.name}</div>`)}
  ${details('Errores', s.errors, (e) => html`<div class="adm-sub">${e.name}: ${e.error}</div>`)}`;

const actionsView = (s) => html`
  <div class="adm-actions">
    ${s.state === 'running' ? html`<button class="adm-btn danger" id="rgCancel">Cancelar sincronización</button>` : ''}
    <button class="adm-btn" id="rgClose">${s.state === 'running' ? 'Ocultar' : 'Cerrar'}</button>
    ${s.state === 'running' ? '' : html`<button class="adm-btn primary" id="rgAgain">Nueva sincronización</button>`}
  </div>`;

function progress(onDone) {
  let timer = null;
  let drawnLists = null; // the sizes of the lists on screen: they are redrawn only when one grows
  const m = openModal(html`
    ${modalHeader('Sincronización con RAWG')}
    <div class="adm-body">
      <div id="rgHead"><div class="loading-spinner">Cargando…</div></div>
      <div id="rgLists"></div>
      <div id="rgActions"></div>
    </div>`, { wide: true, onClose: () => clearTimeout(timer) });
  const body = m.el.querySelector('.adm-body');
  const part = (id) => body.querySelector(`#${id}`);

  const draw = (s, { lists }) => {
    mount(part('rgHead'), headView(s));
    mount(part('rgActions'), actionsView(s));
    const sizes = [s.ambiguous, s.duplicates, s.not_found, s.errors].map((list) => list.length).join();
    if (lists && sizes !== drawnLists) {
      mount(part('rgLists'), listsView(s));
      drawnLists = sizes;
    }
    body.querySelector('#rgClose').addEventListener('click', () => m.close());
    // The last run stays on screen after it ends (its ambiguous games are still to be resolved), so a new one starts from here.
    body.querySelector('#rgAgain')?.addEventListener('click', () => {
      m.close();
      optionsStep(onDone).catch((err) => toast(err.message, 'err'));
    });
    body.querySelector('#rgCancel')?.addEventListener('click', async () => {
      await api('/manage/rawg-sync/cancel', { method: 'POST' });
      toast('Cancelando…');
    });
  };

  // Resolve an ambiguous game by hand (costs 1-2 RAWG calls).
  body.addEventListener('click', async (e) => {
    const button = e.target.closest('[data-use]');
    if (!button) return;
    const row = button.closest('.adm-amb');
    button.disabled = true;
    try {
      const r = await api('/manage/rawg-sync/apply', jsonRequest('POST', { game_id: row.dataset.game, rawg_id: Number(button.dataset.use) }));
      mount(row, html`<span class="adm-sub">✓ ${row.querySelector('strong').textContent} actualizado (${r.changed.length} campos, ${r.calls} llamadas)</span>`);
    } catch (err) {
      toast(err.message, 'err');
      button.disabled = false;
    }
  });

  const tick = async () => {
    if (!m.el.isConnected) return;
    try {
      const s = await api('/manage/rawg-sync/status');
      if (!m.el.isConnected) return;
      // The figures move every time; a list is not redrawn under the admin who is picking among candidates (it would
      // close it), but that must not stop the bar: a run looked stuck until it was cancelled.
      const picking = part('rgLists').querySelector('.adm-details[open]');
      draw(s, { lists: !picking || s.state !== 'running' });
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
