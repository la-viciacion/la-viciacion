// "Recap": look at the recap of any month or season before it goes out, see the texts the notices would carry (the
// group's and one player's), send it now and set when the monthly and the annual ones go out automatically (the same
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
        <div class="adm-sub">El periodo en curso enseña lo que hay hasta hoy. Es el mismo cálculo para meses y temporadas.</div>
        <div class="adm-actions">
          <a class="adm-btn" id="rcaOpen" href="#">Abrir la página del resumen</a>
          <a class="adm-btn" id="rcaStory" href="#">Abrir la historia</a>
        </div>
      </section>

      <section class="adm-set-card">
        <h3>Texto para el grupo</h3>
        <pre class="rc-preview" id="rcaGroup">Cargando…</pre>
        <div class="adm-sub">Tal cual saldría sin IA; con la IA activada para este aviso (Sistema → Avisos que usan la IA) el grupo recibe una versión reescrita con las mismas cifras.</div>
      </section>

      <section class="adm-set-card">
        <h3>Texto para el jugador</h3>
        <pre class="rc-preview" id="rcaPlayer">Cargando…</pre>
        <div class="adm-sub">Mensaje privado, por Telegram y por la app. Cada jugador recibe el suyo; los que no jugaron ese periodo no reciben nada.</div>
      </section>

      <section class="adm-set-card">
        <h3>Enviar ahora</h3>
        <div class="adm-sub">Lo mismo que hacen los envíos automáticos, para el periodo elegido (un mes o una temporada). Respeta el interruptor general de notificaciones.</div>
        <div class="adm-actions">
          <button type="button" class="adm-btn" data-send="me">Enviarme mi resumen (prueba)</button>
          <button type="button" class="adm-btn" data-send="group">Enviar al grupo…</button>
          <button type="button" class="adm-btn" data-send="all">Enviar a todos…</button>
        </div>
        <div class="adm-error" role="alert"></div>
      </section>
    </div>
    <div class="section-header"><h2 class="section-title">Envío automático</h2><div class="section-line"></div></div>
    <div id="rcaSettings"></div>`;
}

async function refresh() {
  const id = ++navigation;
  const open = panel.querySelector('#rcaOpen');
  const target = userById(userId);
  const username = target && target.id !== store.me ? target.username : null;
  open.setAttribute('href', recapHref(period, username));
  panel.querySelector('#rcaStory').setAttribute('href', storyHref(period, username));
  const group = panel.querySelector('#rcaGroup');
  const player = panel.querySelector('#rcaPlayer');
  group.textContent = player.textContent = 'Cargando…';
  try {
    const preview = await api(`/manage/recap/preview?period=${period}&user_id=${userId}`);
    if (id !== navigation) return;
    group.textContent = preview.nobody_played ? 'Nadie jugó en este periodo: no se enviaría nada.' : preview.group_message;
    player.textContent = preview.nobody_played ? '—' : preview.player_message;
  } catch (err) {
    if (id !== navigation) return;
    group.textContent = player.textContent = err.message;
  }
}

const WHO = {
  me: null,
  group: 'Se enviará el resumen al grupo (Telegram y avisos del grupo de la app).',
  all: 'Se enviará el resumen al grupo y el suyo, en privado, a cada jugador activo que pueda recibirlo.',
};

async function send(audience) {
  const errorEl = panel.querySelector('.adm-error');
  errorEl.textContent = '';
  if (WHO[audience] && !(await confirmDialog('Enviar el resumen', html`<p>${WHO[audience]}</p><p>No se puede deshacer.</p>`, { ok: 'Enviar' }))) return;
  try {
    const result = await api('/manage/recap/send', jsonRequest('POST', { period, audience }));
    toast(`Resumen enviado: ${result.message}`);
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
    panel.querySelector('#rcaUser').addEventListener('change', (e) => { userId = Number(e.target.value); refresh(); });
    panel.onclick = (e) => { // not addEventListener: the panel is reused, and a second listener would send twice
      const button = e.target.closest('[data-send]');
      if (button) send(button.dataset.send);
    };
    await Promise.all([refresh(), renderSettings(panel.querySelector('#rcaSettings'), { entity: { sections: ['monthly', 'annual'] } })]);
  } catch (err) {
    mount(panel, errorState(err.message));
  }
}
