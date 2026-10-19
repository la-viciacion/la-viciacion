// "Recap": look at the recap of any month or season before it goes out, see the notice that tells it is ready (the
// same on Telegram and on the app's devices), send it now and set when the monthly and the annual ones go out (the same
// settings form as the rest of the notifications, only its cards for the recap). The page itself (#/recap) opens from
// here for any player. Sending goes through the same code as the jobs.
import { api, jsonRequest } from '../../lib/api.js';
import { html, mount } from '../../lib/html.js';
import { clampPick, lastMonth, monthChoices, periodKey, pickOf, recapHref, withKind, yearChoices } from '../../lib/recap.js';
import { storyHref } from '../../lib/story.js';
import { toast } from '../../ui/toast.js';
import { errorState, store } from './components.js';
import { confirmDialog } from './dialogs.js';
import { render as renderSettings } from './settings.js';

let panel;
let pick = clampPick(pickOf(lastMonth())); // what is being looked at: monthly or annual, the year and, for a month, the month
let userId = null;
let navigation = 0; // only the latest preview may draw

const period = () => periodKey(pick);
const userById = (id) => store.users.find((u) => u.id === Number(id));

// Monthly or annual, then the year (and the month): a short list at each step instead of one that grows every month
function pickerView() {
  const selected = (on) => (on ? 'selected' : '');
  return html`
    <label>Resumen
      <select class="adm-input" id="rcaKind">
        <option value="month" ${selected(pick.kind === 'month')}>Mensual</option>
        <option value="year" ${selected(pick.kind === 'year')}>Anual</option>
      </select>
    </label>
    <label>Año
      <select class="adm-input" id="rcaYear">${yearChoices().map((year) => html`<option value="${year}" ${selected(year === pick.year)}>${year}</option>`)}</select>
    </label>
    ${pick.kind === 'month' ? html`
      <label>Mes
        <select class="adm-input" id="rcaMonth">${monthChoices(pick.year).map(({ value, label }) => html`<option value="${value}" ${selected(value === pick.month)}>${label}</option>`)}</select>
      </label>` : ''}
    <label>Jugador
      <select class="adm-input" id="rcaUser">${store.users.map((u) => html`<option value="${u.id}" ${selected(u.id === userId)}>${u.username}</option>`)}</select>
    </label>`;
}

function view() {
  return html`
    <div class="adm-settings" id="rcAdmin">
      <section class="adm-set-card">
        <h3>Previsualizar</h3>
        <div class="adm-set-row" id="rcaPicker">${pickerView()}</div>
        <div class="adm-sub">Un mes solo se puede ver cuando ha terminado; la temporada en curso enseña lo que hay hasta hoy. El jugador solo cambia a quién abren los botones: el aviso es el mismo para todos.</div>
        <div class="adm-actions">
          <a class="adm-btn" id="rcaOpen" href="#">Abrir la página del resumen</a>
          <a class="adm-btn" id="rcaStory" href="#">Abrir la historia</a>
        </div>
      </section>

      <section class="adm-set-card">
        <h3>El aviso</h3>
        <div class="adm-sub">Un solo aviso, el mismo en el grupo de Telegram y en las notificaciones de la app (a quien tenga activados los avisos del grupo). Solo dice que el resumen está disponible y lleva el enlace a la historia: las cifras no van en el aviso.</div>
        <div class="adm-sub">Telegram</div>
        <pre class="rc-preview" id="rcaTelegram">Cargando…</pre>
        <div class="adm-sub">En la app (al pulsarlo abre la historia)</div>
        <div class="adm-notif" aria-hidden="true">
          <div class="adm-notif-app">La Viciación · ahora</div>
          <div class="adm-notif-title" id="rcaPushTitle"></div>
          <div class="adm-notif-body" id="rcaPushBody"></div>
        </div>
        <div class="adm-sub">Enviarlo ahora es lo mismo que hacen los envíos automáticos, para el periodo elegido. Respeta el interruptor general de notificaciones y, si nadie jugó en ese periodo, no se envía.</div>
        <div class="adm-actions">
          <button type="button" class="adm-btn" data-send="me">Enviármelo (prueba)</button>
          <button type="button" class="adm-btn" data-send="group">Enviarlo al grupo…</button>
        </div>
        <div class="adm-error" role="alert"></div>
      </section>
    </div>
    <div class="section-header"><h2 class="section-title">Envío automático</h2><div class="section-line"></div></div>
    <div id="rcaSettings"></div>`;
}

// Where the buttons open: the page and the story of the period, for the player chosen
function links() {
  const target = userById(userId);
  const username = target && target.id !== store.me ? target.username : null;
  panel.querySelector('#rcaOpen').setAttribute('href', recapHref(period(), username));
  panel.querySelector('#rcaStory').setAttribute('href', storyHref(period(), username));
}

async function refresh() {
  const id = ++navigation;
  links();
  const telegram = panel.querySelector('#rcaTelegram');
  const title = panel.querySelector('#rcaPushTitle');
  const body = panel.querySelector('#rcaPushBody');
  telegram.textContent = 'Cargando…';
  title.textContent = body.textContent = '';
  try {
    const preview = await api(`/manage/recap/preview?period=${period()}`);
    if (id !== navigation) return;
    if (preview.nobody_played) {
      telegram.textContent = 'Nadie jugó en este periodo: no se enviaría nada.';
      return;
    }
    telegram.textContent = preview.telegram;
    title.textContent = preview.push.title;
    body.textContent = preview.push.body;
  } catch (err) {
    if (id !== navigation) return;
    telegram.textContent = err.message;
  }
}

// What the selects of the picker changed; the months on offer depend on the year and the selects on the kind
function onPicker(event) {
  const { id, value } = event.target;
  if (id === 'rcaUser') {
    userId = Number(value);
    return links();
  }
  if (id === 'rcaKind') pick = withKind(pick, value);
  else if (id === 'rcaYear') pick = clampPick({ ...pick, year: Number(value) });
  else if (id === 'rcaMonth') pick = { ...pick, month: Number(value) };
  else return;
  mount(panel.querySelector('#rcaPicker'), pickerView());
  refresh();
}

const WHO = {
  me: null,
  group: 'Se enviará el aviso al grupo de Telegram y a las notificaciones de la app que tengan activados los avisos del grupo.',
};

async function send(audience) {
  const errorEl = panel.querySelector('.adm-error');
  errorEl.textContent = '';
  if (WHO[audience] && !(await confirmDialog('Enviar el resumen', html`<p>${WHO[audience]}</p><p>No se puede deshacer.</p>`, { ok: 'Enviar' }))) return;
  try {
    const result = await api('/manage/recap/send', jsonRequest('POST', { period: period(), audience }));
    toast(result.message);
  } catch (err) {
    errorEl.textContent = err.message;
  }
}

export async function render(target) {
  panel = target;
  pick = clampPick(pickOf(lastMonth())); // each visit starts on the last month, for yourself
  userId = store.me;
  try {
    mount(panel, view());
    panel.onchange = onPicker; // not addEventListener: the panel is reused, and a second listener would act twice
    panel.onclick = (e) => {
      const button = e.target.closest('[data-send]');
      if (button) send(button.dataset.send);
    };
    await Promise.all([refresh(), renderSettings(panel.querySelector('#rcaSettings'), { entity: { sections: ['monthly', 'annual'] } })]);
  } catch (err) {
    mount(panel, errorState(err.message));
  }
}
