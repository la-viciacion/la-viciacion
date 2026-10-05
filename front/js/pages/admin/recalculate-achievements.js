// Recalculating every achievement of every season.
// It works everything out again from the sessions and the library, silently (nobody is notified), and it
// adds, corrects and revokes, so it takes two explicit steps: a preview of exactly what would change and
// a typed phrase. The API enforces the phrase too.
import { api, jsonRequest } from '../../lib/api.js';
import { formatDate } from '../../lib/format.js';
import { html } from '../../lib/html.js';
import { modalHeader, openModal } from '../../ui/modal.js';
import { toast } from '../../ui/toast.js';
import { statTile, store } from './components.js';

const PHRASE = 'RECALCULAR';

const SECTIONS = [
  ['add', 'Se concederán', (c) => formatDate(c.date_after)],
  ['date', 'Cambiarán de fecha o de juego', (c) => `${formatDate(c.date_before)} → ${formatDate(c.date_after)}`],
  ['revoke', 'Se revocarán', (c) => formatDate(c.date_before)],
];

/** Entry point. onDone() runs when the recalculation has been launched. */
export function recalculateAchievementsFlow({ onDone } = {}) {
  const m = openModal(html`
    ${modalHeader('Recalcular logros')}
    <form class="adm-form" novalidate>
      <p class="adm-sub">Vuelve a calcular <strong>todos los logros de todas las temporadas</strong> a partir de las sesiones y la biblioteca, también de los jugadores que ya no están activos. Antes de aplicar nada verás qué cambiaría. <strong>No se avisa a nadie</strong>: ni por Telegram ni por la app.</p>
      <label>Jugador
        <select class="adm-input" name="user"><option value="">Todos</option>${store.users.map((u) => html`<option value="${u.id}">${u.username}</option>`)}</select>
      </label>
      <div class="adm-error" role="alert"></div>
      <div class="adm-actions"><button type="button" class="adm-btn" data-close>Cancelar</button><button class="adm-btn primary" type="submit">Ver vista previa</button></div>
    </form>`);
  const form = m.el.querySelector('form');
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const submit = form.querySelector('button[type=submit]');
    submit.disabled = true;
    submit.textContent = 'Calculando…';
    const userId = form.user.value ? Number(form.user.value) : null;
    try {
      const preview = await api(`/manage/recalculate-achievements/preview${userId ? `?user_id=${userId}` : ''}`);
      m.close();
      previewStep(userId, preview, onDone);
    } catch (err) {
      form.querySelector('.adm-error').textContent = err.message;
      submit.disabled = false;
      submit.textContent = 'Ver vista previa';
    }
  });
}

function previewStep(userId, { counts, changes }, onDone) {
  const total = changes.length;
  const m = openModal(html`
    ${modalHeader('Vista previa del recálculo')}
    <div class="adm-form">
      <div class="adm-stats adm-stats-sm">
        ${statTile('a conceder', counts.add)}
        ${statTile('a corregir', counts.date)}
        ${statTile('a revocar', counts.revoke)}
      </div>
      ${total
    ? html`<p class="adm-sub">Esto es lo que se haría ahora mismo. Las fechas que hayas editado a mano se vuelven a calcular, y lo que ya no se cumple se revoca.</p>
        ${SECTIONS.map(([action, title, when]) => {
    const rows = changes.filter((c) => c.action === action);
    return rows.length ? html`<details class="adm-details"><summary>${title} (${rows.length})</summary>
          ${rows.map((c) => html`<div class="adm-sub"><strong>${c.user}</strong> · ${c.season} · ${c.title} · ${when(c)}${c.game_after || c.game_before ? html` · ${c.game_after || c.game_before}` : ''}</div>`)}
        </details>` : '';
  })}`
    : html`<div class="adm-ok">Todo en orden: no hay nada que cambiar.</div>`}
      <div class="adm-actions">
        <button type="button" class="adm-btn" data-close>${total ? 'Cancelar' : 'Cerrar'}</button>
        ${total ? html`<button class="adm-btn danger" data-continue>Continuar…</button>` : ''}
      </div>
    </div>`, { wide: true });
  m.el.querySelector('[data-continue]')?.addEventListener('click', () => {
    m.close();
    confirmStep(userId, total, onDone);
  });
}

function confirmStep(userId, total, onDone) {
  const m = openModal(html`
    ${modalHeader('⚠️ Segunda confirmación')}
    <form class="adm-form" novalidate>
      <div class="adm-warn">
        <strong>Se aplicarán ${total} cambios en los logros</strong> de ${userId ? 'este jugador' : 'todos los jugadores'}, de todas las temporadas.
        Se vuelve a calcular en ese momento, así que puede variar si hay datos nuevos. <strong>No se notifica a nadie</strong>, pero lo que se revoque o cambie de fecha no se puede deshacer.
      </div>
      <label>Escribe <strong>${PHRASE}</strong> para habilitar el botón<input class="adm-input" name="phrase" autocomplete="off" /></label>
      <div class="adm-error" role="alert"></div>
      <div class="adm-actions">
        <button type="button" class="adm-btn" data-close>Cancelar</button>
        <button class="adm-btn danger" type="submit" disabled>Recalcular los logros</button>
      </div>
    </form>`, { wide: true });
  const form = m.el.querySelector('form');
  const go = form.querySelector('button[type=submit]');
  const typedOk = () => form.phrase.value.trim() === PHRASE;
  form.phrase.addEventListener('input', () => { go.disabled = !typedOk(); });
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!typedOk()) return;
    go.disabled = true;
    try {
      await api('/manage/recalculate-achievements', jsonRequest('POST', { user_id: userId, confirm: PHRASE }));
      m.close();
      toast('Recálculo en marcha');
      onDone?.();
    } catch (err) {
      form.querySelector('.adm-error').textContent = err.message;
      go.disabled = false;
    }
  });
  form.phrase.focus();
}
