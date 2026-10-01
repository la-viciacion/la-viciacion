// Personal preferences of the profile (PATCH /users/{username}/settings). An empty field means
// the default; the API says which one it is.
//  - "Avisos de timer olvidado": how many hours a timer may run before the reminder.
//  - "Notificación del timer": every how many minutes the pinned push notification is refreshed.
import { api, jsonRequest } from '../../lib/api.js';
import { HOURS_HINT, MAX_HOURS, MIN_HOURS, parseHours } from '../../lib/hours.js';
import { html, mount } from '../../lib/html.js';
import { MAX_MINUTES, MIN_MINUTES, MINUTES_HINT, parseMinutes } from '../../lib/minutes.js';

const heading = (text) => html`<div class="section-header"><h2 class="section-title">${text}</h2><div class="section-line"></div></div>`;

/** Wire one settings form: parse its field, PATCH the one setting, report in its message line. */
function bindForm(form, { field, parse, invalid, setting, saved }, path) {
  const msg = form.querySelector('.pf-msg');
  const say = (text, ok = false) => {
    msg.textContent = text;
    msg.className = `pf-msg ${text ? (ok ? 'ok' : 'err') : ''}`;
  };
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const value = parse(form[field].value);
    if (value === undefined) return say(invalid);
    try {
      await api(path, jsonRequest('PATCH', { [setting]: value }));
      say(saved(value), true);
    } catch (err) {
      say(err.message);
    }
  });
}

export async function initPreferences(el, { path }) {
  const settings = await api(path);
  if (!settings) return;
  const hoursDefault = settings.defaults.forgotten_timer_hours;
  const minutesDefault = settings.defaults.timer_notice_minutes;

  mount(el, html`
    ${heading('Timer olvidado')}
    <form class="pf-card pf-form" id="pfForgotten" novalidate>
      <label>Avisarme si un timer lleva activo más de (horas)
        <input class="adm-input" type="number" name="hours" inputmode="numeric" step="1" min="${MIN_HOURS}" max="${MAX_HOURS}"
          value="${settings.forgotten_timer_hours ?? ''}" placeholder="${hoursDefault}" />
      </label>
      <div class="pf-sub">${HOURS_HINT} Si lo dejas vacío, te avisamos a las ${hoursDefault} horas. El aviso se comprueba cada hora, así que puede llegar hasta una hora después.</div>
      <div class="pf-msg" role="status"></div>
      <div><button class="pf-btn primary" type="submit">Guardar</button></div>
    </form>
    ${heading('Notificación del timer')}
    <form class="pf-card pf-form" id="pfNotice" novalidate>
      <label>Actualizar la notificación del timer cada (minutos)
        <input class="adm-input" type="number" name="minutes" inputmode="numeric" step="1" min="${MIN_MINUTES}" max="${MAX_MINUTES}"
          value="${settings.timer_notice_minutes ?? ''}" placeholder="${minutesDefault}" />
      </label>
      <div class="pf-sub">${MINUTES_HINT} Si lo dejas vacío, se actualiza cada ${minutesDefault} minutos. Solo afecta a la notificación fija de la app mientras tienes un timer en marcha.</div>
      <div class="pf-msg" role="status"></div>
      <div><button class="pf-btn primary" type="submit">Guardar</button></div>
    </form>`);

  bindForm(
    el.querySelector('#pfForgotten'),
    {
      field: 'hours',
      parse: parseHours,
      invalid: `Las horas deben ser un número entero entre ${MIN_HOURS} y ${MAX_HOURS}`,
      setting: 'forgotten_timer_hours',
      saved: (hours) => (hours === null ? `Guardado: se usarán las ${hoursDefault} horas por defecto` : 'Guardado'),
    },
    path,
  );
  bindForm(
    el.querySelector('#pfNotice'),
    {
      field: 'minutes',
      parse: parseMinutes,
      invalid: `Los minutos deben ser un número entero entre ${MIN_MINUTES} y ${MAX_MINUTES}`,
      setting: 'timer_notice_minutes',
      saved: (minutes) => (minutes === null ? `Guardado: se usarán los ${minutesDefault} minutos por defecto` : 'Guardado'),
    },
    path,
  );
}
