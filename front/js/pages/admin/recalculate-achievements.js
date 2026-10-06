// Recalculating the achievements.
// It works everything out again from the sessions and the library, silently (nobody is notified), and it
// adds, corrects and revokes, so it takes two explicit steps: a preview of exactly what would change and
// a typed phrase. The players, the seasons and the achievements can be chosen (all by default; the ones that
// are switched off are left alone). The API enforces the phrase too.
import { api, jsonRequest } from '../../lib/api.js';
import { formatDate } from '../../lib/format.js';
import { html } from '../../lib/html.js';
import { modalHeader, openModal } from '../../ui/modal.js';
import { toast } from '../../ui/toast.js';
import { seasonYears, statTile, store } from './components.js';

const PHRASE = 'RECALCULAR';

const SECTIONS = [
  ['add', 'Se concederán', (c) => formatDate(c.date_after)],
  ['date', 'Cambiarán de fecha o de juego', (c) => `${formatDate(c.date_before)} → ${formatDate(c.date_after)}`],
  ['revoke', 'Se revocarán', (c) => formatDate(c.date_before)],
];

/** What was ticked in a group of checkboxes: null when everything is (no filter), else the values. */
const chosen = (form, name, parse = Number) => {
  const boxes = [...form.querySelectorAll(`input[name=${name}]`)];
  const ticked = boxes.filter((box) => box.checked).map((box) => parse(box.value));
  return ticked.length === boxes.length ? null : ticked;
};

/** A block of options to tick (all ticked to begin with): its title and how many are ticked, a button for all or
 *  none, and a grid of equal columns; a long list (`long`) scrolls inside its own block. */
const choices = (title, name, options, { long = false } = {}) => html`
  <section class="adm-pick" data-pick="${name}">
    <div class="adm-pick-head">
      <strong>${title}</strong>
      <span class="adm-pick-count" data-count="${name}">${options.length} de ${options.length}</span>
      <span class="adm-pick-tools">
        <button type="button" class="adm-btn sm" data-all="${name}">Todos</button>
        <button type="button" class="adm-btn sm" data-none="${name}">Ninguno</button>
      </span>
    </div>
    <div class="adm-pick-grid${long ? ' long' : ''}">
      ${options.map(([value, label]) => html`<label class="adm-pick-item" title="${label}"><input type="checkbox" name="${name}" value="${value}" checked /><span>${label}</span></label>`)}
    </div>
  </section>`;

const GROUPS = [['user', 'jugador', 'jugadores'], ['season', 'temporada', 'temporadas'], ['achievement', 'logro', 'logros']];

/** Shows how many are ticked in each block and in the summary, and does not let go on with a block empty. */
function refreshPicks(form) {
  const parts = [];
  let empty = false;
  for (const [name, one, many] of GROUPS) {
    const boxes = [...form.querySelectorAll(`input[name=${name}]`)];
    const ticked = boxes.filter((box) => box.checked).length;
    form.querySelector(`[data-count=${name}]`).textContent = `${ticked} de ${boxes.length}`;
    parts.push(`${ticked} ${ticked === 1 ? one : many}`);
    if (!ticked) empty = true;
  }
  form.querySelector('.adm-pick-summary').textContent = empty ? 'Elige al menos uno de cada' : `Se recalcularán ${parts.join(' · ')}`;
  form.querySelector('button[type=submit]').disabled = empty;
}

const query = ({ userIds, seasonList, achievementKeys }) => {
  const params = new URLSearchParams();
  (userIds || []).forEach((id) => params.append('user_ids', id));
  (seasonList || []).forEach((season) => params.append('season_list', season));
  (achievementKeys || []).forEach((key) => params.append('achievement_keys', key));
  const text = params.toString();
  return text ? `?${text}` : '';
};

const describe = ({ userIds, seasonList, achievementKeys }) => {
  const who = userIds ? `${userIds.length} ${userIds.length === 1 ? 'jugador' : 'jugadores'}` : 'todos los jugadores';
  const when = seasonList ? `la${seasonList.length === 1 ? '' : 's'} temporada${seasonList.length === 1 ? '' : 's'} ${seasonList.join(', ')}` : 'todas las temporadas';
  const which = achievementKeys ? `${achievementKeys.length} ${achievementKeys.length === 1 ? 'logro' : 'logros'}` : 'todos los logros activos';
  return `${who}, ${when}, ${which}`;
};

/** Entry point. onDone() runs when the recalculation has been launched. */
export function recalculateAchievementsFlow({ onDone } = {}) {
  const m = openModal(html`
    ${modalHeader('Recalcular logros')}
    <form class="adm-form" novalidate>
      <p class="adm-sub">Vuelve a calcular los logros a partir de las sesiones y la biblioteca, también los de los jugadores que ya no están activos. Los logros inactivos no se tocan. Antes de aplicar nada verás qué cambiaría. <strong>No se avisa a nadie</strong>, ni por Telegram ni por la app.</p>
      ${choices('Jugadores', 'user', store.users.map((u) => [u.id, u.username]))}
      ${choices('Temporadas', 'season', seasonYears().map((year) => [year, year]))}
      ${choices('Logros', 'achievement', store.achievements.filter((a) => a.active).map((a) => [a.key, a.title]), { long: true })}
      <div class="adm-pick-summary" role="status"></div>
      <div class="adm-error" role="alert"></div>
      <div class="adm-actions"><button type="button" class="adm-btn" data-close>Cancelar</button><button class="adm-btn primary" type="submit">Ver vista previa</button></div>
    </form>`, { wide: true });
  const form = m.el.querySelector('form');
  form.addEventListener('click', (e) => {
    const { all, none } = e.target.dataset;
    const name = all || none;
    if (!name) return;
    form.querySelectorAll(`input[name=${name}]`).forEach((box) => { box.checked = Boolean(all); });
    refreshPicks(form);
  });
  form.addEventListener('change', () => refreshPicks(form));
  refreshPicks(form);
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const error = form.querySelector('.adm-error');
    const selection = { userIds: chosen(form, 'user'), seasonList: chosen(form, 'season'), achievementKeys: chosen(form, 'achievement', String) };
    if (selection.userIds?.length === 0 || selection.seasonList?.length === 0 || selection.achievementKeys?.length === 0) return;
    error.textContent = '';
    const submit = form.querySelector('button[type=submit]');
    submit.disabled = true;
    submit.textContent = 'Calculando…';
    try {
      const preview = await api(`/manage/recalculate-achievements/preview${query(selection)}`);
      m.close();
      previewStep(selection, preview, onDone);
    } catch (err) {
      error.textContent = err.message;
      submit.disabled = false;
      submit.textContent = 'Ver vista previa';
    }
  });
}

function previewStep(selection, { counts, changes }, onDone) {
  const total = changes.length;
  const m = openModal(html`
    ${modalHeader('Vista previa del recálculo')}
    <div class="adm-form">
      <p class="adm-sub">${describe(selection)}</p>
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
    confirmStep(selection, total, onDone);
  });
}

function confirmStep(selection, total, onDone) {
  const m = openModal(html`
    ${modalHeader('⚠️ Segunda confirmación')}
    <form class="adm-form" novalidate>
      <div class="adm-warn">
        <strong>Se aplicarán ${total} cambios en los logros</strong> de ${describe(selection)}.
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
      await api('/manage/recalculate-achievements', jsonRequest('POST', {
        user_ids: selection.userIds, season_list: selection.seasonList, achievement_keys: selection.achievementKeys, confirm: PHRASE,
      }));
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
