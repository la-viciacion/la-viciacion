// "Recap": look at the recap of any month or season before it goes out, see the notice that tells it is ready (the
// same on Telegram and on the app's devices), send it now and set when the monthly and the annual ones go out (the same
// settings form as the rest of the notifications, only its cards for the recap). The page itself (#/recap) opens from
// here for any player. Sending goes through the same code as the jobs.
import { api, jsonRequest } from '../../lib/api.js';
import { html, mount } from '../../lib/html.js';
import { lastMonth, periodChoices, recapHref } from '../../lib/recap.js';
import { storyHref } from '../../lib/story.js';
import { toast } from '../../ui/toast.js';
import { errorState, store } from './components.js';
import { confirmDialog } from './dialogs.js';
import { render as renderSettings } from './settings.js';

let panel;
let period = lastMonth();
let userId = null;
let navigation = 0; // only the latest preview may draw

const userById = (id) => store.users.find((u) => u.id === Number(id));

function view() {
  const { months, seasons } = periodChoices();
  const option = ({ value, label }) => html`<option value="${value}" ${value === period ? 'selected' : ''}>${label}</option>`;
  return html`
    <div class="adm-settings" id="rcAdmin">
      <section class="adm-set-card">
        <h3>Qué ver</h3>
        <div class="adm-set-row">
          <label>Periodo
            <select class="adm-input" id="rcaPeriod">
              <optgroup label="Meses">${months.map(option)}</optgroup>
              <optgroup label="Temporadas">${seasons.map(option)}</optgroup>
            </select>
          </label>
          <label>Jugador
            <select class="adm-input" id="rcaUser">${store.users.map((u) => html`<option value="${u.id}" ${u.id === userId ? 'selected' : ''}>${u.username}</option>`)}</select>
          </label>
        </div>
        <div class="adm-sub">El periodo en curso enseña lo que hay hasta hoy. Es el mismo cálculo para meses y temporadas. El jugador solo cambia a quién enseñan los botones: el aviso es el mismo para todos.</div>
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
      </section>

      <section class="adm-set-card">
        <h3>Enviar ahora</h3>
        <div class="adm-sub">Lo mismo que hacen los envíos automáticos, para el periodo elegido (un mes o una temporada). Respeta el interruptor general de notificaciones. Si nadie jugó en ese periodo, no se envía.</div>
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
  panel.querySelector('#rcaOpen').setAttribute('href', recapHref(period, username));
  panel.querySelector('#rcaStory').setAttribute('href', storyHref(period, username));
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
    const preview = await api(`/manage/recap/preview?period=${period}`);
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

const WHO = {
  me: null,
  group: 'Se enviará el aviso al grupo de Telegram y a las notificaciones de la app que tengan activados los avisos del grupo.',
};

async function send(audience) {
  const errorEl = panel.querySelector('.adm-error');
  errorEl.textContent = '';
  if (WHO[audience] && !(await confirmDialog('Enviar el resumen', html`<p>${WHO[audience]}</p><p>No se puede deshacer.</p>`, { ok: 'Enviar' }))) return;
  try {
    const result = await api('/manage/recap/send', jsonRequest('POST', { period, audience }));
    toast(result.message);
  } catch (err) {
    errorEl.textContent = err.message;
  }
}

export async function render(target) {
  panel = target;
  userId ??= store.me;
  try {
    mount(panel, view());
    panel.querySelector('#rcaPeriod').addEventListener('change', (e) => { period = e.target.value; refresh(); });
    panel.querySelector('#rcaUser').addEventListener('change', (e) => { userId = Number(e.target.value); links(); });
    panel.onclick = (e) => { // not addEventListener: the panel is reused, and a second listener would send twice
      const button = e.target.closest('[data-send]');
      if (button) send(button.dataset.send);
    };
    await Promise.all([refresh(), renderSettings(panel.querySelector('#rcaSettings'), { entity: { sections: ['monthly', 'annual'] } })]);
  } catch (err) {
    mount(panel, errorState(err.message));
  }
}
