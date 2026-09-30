// "Avisos de timer olvidado": how many hours a timer may run before the reminder.
// Empty means the default; the API says which one it is.
import { api, jsonRequest } from '../../lib/api.js';
import { HOURS_HINT, MAX_HOURS, MIN_HOURS, parseHours } from '../../lib/hours.js';
import { html, mount } from '../../lib/html.js';

const title = html`<div class="section-header"><h2 class="section-title">Timer olvidado</h2><div class="section-line"></div></div>`;

export async function initPreferences(el, { path }) {
  const settings = await api(path);
  if (!settings) return;
  const fallback = settings.defaults.forgotten_timer_hours;

  mount(el, html`
    ${title}
    <form class="pf-card pf-form" novalidate>
      <label>Avisarme si un timer lleva activo más de (horas)
        <input class="adm-input" type="number" name="hours" inputmode="numeric" step="1" min="${MIN_HOURS}" max="${MAX_HOURS}"
          value="${settings.forgotten_timer_hours ?? ''}" placeholder="${fallback}" />
      </label>
      <div class="pf-sub">${HOURS_HINT} Si lo dejas vacío, te avisamos a las ${fallback} horas. El aviso se comprueba cada hora, así que puede llegar hasta una hora después.</div>
      <div class="pf-msg" role="status"></div>
      <div><button class="pf-btn primary" type="submit">Guardar</button></div>
    </form>`);

  const form = el.querySelector('form');
  const msg = el.querySelector('.pf-msg');
  const say = (text, ok = false) => {
    msg.textContent = text;
    msg.className = `pf-msg ${text ? (ok ? 'ok' : 'err') : ''}`;
  };

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const hours = parseHours(form.hours.value);
    if (hours === undefined) return say(`Las horas deben ser un número entero entre ${MIN_HOURS} y ${MAX_HOURS}`);
    try {
      await api(path, jsonRequest('PATCH', { forgotten_timer_hours: hours }));
      say(hours === null ? `Guardado: se usarán las ${fallback} horas por defecto` : 'Guardado', true);
    } catch (err) {
      say(err.message);
    }
  });
}
