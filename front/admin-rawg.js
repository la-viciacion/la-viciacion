// ============================================================
//  Admin panel — RAWG catalogue sync UI (lazy-loaded from admin.js).
//  The sync is intensive (it spends the monthly RAWG quota), so launching it
//  takes two explicit approvals: an options/estimate step and a typed phrase.
//  The API enforces the phrase too.
// ============================================================

let api, esc, openModal, toast, jsonReq, onDone;

const SYNC_PHRASE = 'SINCRONIZAR';
const STOP_REASONS = {
  completed: 'Terminada: se han procesado todos los juegos pendientes.',
  max_calls: 'Detenida: se alcanzó el tope de llamadas. Puedes lanzarla otra vez para continuar con los que falten.',
  cancelled: 'Cancelada manualmente.',
  errors: 'Detenida por errores consecutivos de RAWG. Prueba de nuevo más tarde.',
};

export async function rawgSyncFlow(ctx) {
  ({ api, esc, openModal, toast, jsonReq, onDone } = ctx);
  const status = await api('/manage/rawg-sync/status');
  // A run in progress (or just finished) is shown instead of starting another one.
  if (status.state === 'running' || status.state === 'finished' || status.state === 'cancelled') {
    return progress();
  }
  return step1();
}

async function step1() {
  const est = await api('/manage/rawg-sync/estimate');
  const m = openModal(`
    <div class="modal-header"><h3>Sincronizar juegos con RAWG</h3><button class="modal-close" data-close aria-label="Cerrar">&times;</button></div>
    <form class="adm-form" id="rgForm" novalidate>
      <p class="adm-sub">Busca cada juego en RAWG para guardar su <strong>ID</strong> y completar los datos que falten (desarrolladora, géneros, fecha, imagen, slug y Steam ID). El nombre nunca se modifica.</p>
      <div class="adm-stats adm-stats-sm">
        <div class="adm-stat"><div class="adm-stat-v">${est.pending_games}</div><div class="adm-stat-l">juegos por procesar de ${est.total_games}</div></div>
        <div class="adm-stat"><div class="adm-stat-v">~${est.estimated_calls}</div><div class="adm-stat-l">llamadas a RAWG (máx.)</div></div>
        <div class="adm-stat"><div class="adm-stat-v">${((est.estimated_calls / est.monthly_quota) * 100).toFixed(1)}%</div><div class="adm-stat-l">de la cuota mensual (${est.monthly_quota.toLocaleString('es-ES')})</div></div>
      </div>
      <label>Tope de llamadas para esta ejecución<input class="adm-input" type="number" id="rgMax" min="1" max="20000" value="${Math.min(2000, Math.max(50, est.estimated_calls))}" /></label>
      <label class="adm-check"><input type="checkbox" id="rgOver" /> Sobrescribir datos existentes (pisa ediciones manuales)</label>
      <div class="adm-sub">Se procesan primero los juegos con más sesiones. Sin sobrescribir, solo se rellenan campos vacíos. Duración aproximada: ${Math.ceil((est.estimated_calls * 0.5) / 60)} min.</div>
      <div class="adm-error" id="rgErr" role="alert"></div>
      <div class="adm-actions"><button type="button" class="adm-btn" data-close>Cancelar</button><button class="adm-btn primary" type="submit" ${est.pending_games ? '' : 'disabled'}>${est.pending_games ? 'Continuar…' : 'Nada pendiente'}</button></div>
    </form>`, { wide: true });
  m.el.querySelector('#rgForm').addEventListener('submit', (e) => {
    e.preventDefault();
    const max = Number(m.el.querySelector('#rgMax').value);
    if (!(max >= 1 && max <= 20000)) { m.el.querySelector('#rgErr').textContent = 'El tope debe estar entre 1 y 20000'; return; }
    const overwrite = m.el.querySelector('#rgOver').checked;
    m.close();
    step2(max, overwrite);
  });
}

function step2(max, overwrite) {
  const m = openModal(`
    <div class="modal-header"><h3>⚠️ Segunda confirmación</h3><button class="modal-close" data-close aria-label="Cerrar">&times;</button></div>
    <form class="adm-form" id="rgConfirm" novalidate>
      <div class="adm-warn">
        <strong>Este es un proceso intensivo.</strong> Hará hasta <strong>${max.toLocaleString('es-ES')}</strong> llamadas a la API de RAWG,
        que cuentan contra el límite mensual del plan gratuito (20.000). Tarda varios minutos y modifica datos de juegos${overwrite ? ', <strong>sobrescribiendo los valores existentes</strong>' : ''}.
        <br/>Lánzalo solo en casos de extrema necesidad.
      </div>
      <label>Escribe <strong>${SYNC_PHRASE}</strong> para habilitar el botón<input class="adm-input" id="rgPhrase" autocomplete="off" /></label>
      <div class="adm-error" id="rgErr2" role="alert"></div>
      <div class="adm-actions"><button type="button" class="adm-btn" data-close>Cancelar</button><button class="adm-btn danger" id="rgGo" type="submit" disabled>Lanzar sincronización</button></div>
    </form>`, { wide: true });
  const phrase = m.el.querySelector('#rgPhrase');
  const go = m.el.querySelector('#rgGo');
  phrase.addEventListener('input', () => { go.disabled = phrase.value.trim() !== SYNC_PHRASE; });
  m.el.querySelector('#rgConfirm').addEventListener('submit', async (e) => {
    e.preventDefault();
    if (phrase.value.trim() !== SYNC_PHRASE) return;
    go.disabled = true;
    try {
      await api('/manage/rawg-sync/start', jsonReq('POST', { confirm: SYNC_PHRASE, max_calls: max, overwrite }));
      m.close();
      progress();
    } catch (err) {
      m.el.querySelector('#rgErr2').textContent = err.message;
      go.disabled = false;
    }
  });
  phrase.focus();
}

function progress() {
  const m = openModal(`
    <div class="modal-header"><h3>Sincronización con RAWG</h3><button class="modal-close" data-close aria-label="Cerrar">&times;</button></div>
    <div id="rgBody" class="adm-body"><div class="loading-spinner">Cargando…</div></div>`, { wide: true });
  const body = m.el.querySelector('#rgBody');
  let timer = null;
  const alive = () => document.body.contains(m.el);
  m.el.querySelector('.modal-close').addEventListener('click', () => clearTimeout(timer));

  const render = (s) => {
    const running = s.state === 'running';
    const pct = s.total ? Math.round((s.processed / s.total) * 100) : 0;
    const list = (title, items, fmt) => (items.length
      ? `<details class="adm-details"><summary>${title} (${items.length})</summary>${items.map(fmt).join('')}</details>` : '');
    body.innerHTML = `
      <div class="adm-progress"><div style="width:${pct}%"></div></div>
      <div class="adm-progress-txt">${s.processed} / ${s.total} juegos · ${s.calls} / ${s.max_calls} llamadas${running && s.current ? ` · ${esc(s.current)}` : ''}</div>
      <div class="adm-stats adm-stats-sm">
        <div class="adm-stat"><div class="adm-stat-v">${s.updated}</div><div class="adm-stat-l">actualizados</div></div>
        <div class="adm-stat"><div class="adm-stat-v">${s.ambiguous.length}</div><div class="adm-stat-l">ambiguos</div></div>
        <div class="adm-stat"><div class="adm-stat-v">${s.not_found.length}</div><div class="adm-stat-l">sin resultado</div></div>
        <div class="adm-stat"><div class="adm-stat-v">${s.errors.length}</div><div class="adm-stat-l">errores</div></div>
      </div>
      ${running ? '' : `<p class="adm-sub">${esc(STOP_REASONS[s.stop_reason] || s.stop_reason || '')}</p>`}
      ${list('Ambiguos: elige la coincidencia correcta', s.ambiguous, (a) => `
        <div class="adm-amb" data-game="${esc(a.game_id)}"><strong>${esc(a.name)}</strong>
          ${a.candidates.map((c) => `<button class="adm-btn sm" data-use="${c.rawg_id}" title="${esc((c.platforms || []).join(', '))}">${esc(c.name)}${c.released ? ` (${esc(c.released.slice(0, 4))})` : ''}</button>`).join('')}
        </div>`)}
      ${list('Duplicados (mismo ID de RAWG en otro juego: fusiónalos)', s.duplicates, (d) => `<div class="adm-sub">«${esc(d.name)}» ↔ «${esc(d.other_name)}» (RAWG ${d.rawg_id})</div>`)}
      ${list('Sin resultado en RAWG', s.not_found, (n) => `<div class="adm-sub">${esc(n.name)}</div>`)}
      ${list('Errores', s.errors, (e) => `<div class="adm-sub">${esc(e.name)}: ${esc(e.error)}</div>`)}
      <div class="adm-actions">
        ${running ? '<button class="adm-btn danger" id="rgCancel">Cancelar sincronización</button>' : ''}
        <button class="adm-btn" id="rgClose">${running ? 'Ocultar' : 'Cerrar'}</button>
      </div>`;
    body.querySelector('#rgClose').addEventListener('click', () => { clearTimeout(timer); m.close(); });
    body.querySelector('#rgCancel')?.addEventListener('click', async () => {
      await api('/manage/rawg-sync/cancel', { method: 'POST' });
      toast('Cancelando…');
    });
  };

  // Resolve an ambiguous game by hand (costs 1-2 RAWG calls).
  body.addEventListener('click', async (e) => {
    const b = e.target.closest('[data-use]');
    if (!b) return;
    const row = b.closest('.adm-amb');
    b.disabled = true;
    try {
      const r = await api('/manage/rawg-sync/apply', jsonReq('POST', { game_id: row.dataset.game, rawg_id: Number(b.dataset.use) }));
      row.innerHTML = `<span class="adm-sub">✓ ${esc(row.querySelector('strong').textContent)} actualizado (${r.changed.length} campos, ${r.calls} llamadas)</span>`;
    } catch (err) { toast(err.message, 'err'); b.disabled = false; }
  });

  const tick = async () => {
    if (!alive()) return;
    try {
      const s = await api('/manage/rawg-sync/status');
      if (!alive()) return;
      // don't re-render under the admin while they are picking among candidates
      const picking = body.querySelector('.adm-details[open]');
      if (!picking || s.state !== 'running') render(s);
      if (s.state === 'running') timer = setTimeout(tick, 2000);
      else { toast('Sincronización terminada'); onDone(); }
    } catch (err) {
      body.innerHTML = `<div class="adm-error">${esc(err.message)}</div>`;
    }
  };
  tick();
}
