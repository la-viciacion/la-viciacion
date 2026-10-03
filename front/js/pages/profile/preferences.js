// Personal preferences of the profile (PATCH /users/{username}/settings). An empty field means
// the default; the API says which one it is.
//  - "Avisos de timer olvidado": how many hours a timer may run before the reminder.
//  - "Jugando ahora": whether the others see you in the navbar chip while your timer runs.
import { api, jsonRequest } from '../../lib/api.js';
import { HOURS_HINT, MAX_HOURS, MIN_HOURS, parseHours } from '../../lib/hours.js';
import { html, mount } from '../../lib/html.js';

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

    ${heading('Jugando ahora')}
    <form class="pf-card pf-form" id="pfPlaying" novalidate>
      <label class="adm-check"><input type="checkbox" name="show" ${(settings.show_playing ?? settings.defaults.show_playing) ? 'checked' : ''} /> Mostrar a los demás cuándo estoy jugando</label>
      <div class="pf-sub">Si lo desactivas, el resto del grupo no te verá en «Jugando ahora» (tú sí verás el halo verde en tu avatar). Los avisos al grupo que ya existen no cambian.</div>
      <div class="pf-msg" role="status"></div>
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

  const playing = el.querySelector('#pfPlaying');
  const say = playing.querySelector('.pf-msg');
  playing.show.addEventListener('change', async () => {
    try {
      await api(path, jsonRequest('PATCH', { show_playing: playing.show.checked }));
      say.textContent = playing.show.checked ? 'Guardado: los demás te verán cuando juegues' : 'Guardado: los demás no te verán cuando juegues';
      say.className = 'pf-msg ok';
    } catch (err) {
      playing.show.checked = !playing.show.checked;
      say.textContent = err.message;
      say.className = 'pf-msg err';
    }
  });
}
