// "Notificaciones" of the profile: a table with one row per private notice and, to the right, a checkbox
// per channel (Telegram, push to the user's devices) that saves as soon as it changes
// (PATCH /users/{username}/settings). A notice with neither channel checked is simply not sent.
// A notice with options (the forgotten timer's hours) opens them under its row while any channel is
// checked. The next notices are one more entry in NOTICES.
import { api, jsonRequest } from '../../lib/api.js';
import { HOURS_HINT, MAX_HOURS, MIN_HOURS, parseHours } from '../../lib/hours.js';
import { html, mount } from '../../lib/html.js';

const NOTICES = [{ id: 'forgotten_timer', name: 'Timer olvidado', hint: 'Un recordatorio si dejas un timer activo demasiado tiempo' }];

export async function initNotifications(el, { path }) {
  const settings = await api(path);
  if (!settings) return;
  const hoursDefault = settings.defaults.forgotten_timer_hours;
  const channel = (notice, name) => settings[`${notice}_${name}`] ?? settings.defaults[`${notice}_${name}`];

  mount(el, html`
    <div class="section-header"><h2 class="section-title">Notificaciones</h2><div class="section-line"></div></div>
    <div class="pf-card pf-notices">
      <div class="pf-notice-head" aria-hidden="true"><span></span><span>Telegram</span><span>Push</span></div>
      ${NOTICES.map((notice) => html`
        <div class="pf-notice" data-notice="${notice.id}">
          <div class="pf-notice-name">${notice.name}<div class="pf-sub">${notice.hint}</div></div>
          <label class="pf-notice-box"><input type="checkbox" name="${notice.id}_telegram" ${channel(notice.id, 'telegram') ? 'checked' : ''} aria-label="${notice.name} por Telegram" /></label>
          <label class="pf-notice-box"><input type="checkbox" name="${notice.id}_push" ${channel(notice.id, 'push') ? 'checked' : ''} aria-label="${notice.name} por push" /></label>
        </div>
        <form class="pf-notice-options pf-form" data-options="${notice.id}" novalidate>
          <label>Avisarme si un timer lleva activo más de (horas)
            <input class="adm-input" type="number" name="hours" inputmode="numeric" step="1" min="${MIN_HOURS}" max="${MAX_HOURS}"
              value="${settings.forgotten_timer_hours ?? ''}" placeholder="${hoursDefault}" />
          </label>
          <div class="pf-sub">${HOURS_HINT} Si lo dejas vacío, te avisamos a las ${hoursDefault} horas. El aviso se comprueba cada hora, así que puede llegar hasta una hora después.</div>
          <div><button class="pf-btn primary" type="submit">Guardar</button></div>
        </form>`)}
      <div class="pf-sub">Telegram solo llega si has vinculado tu cuenta; push, si has activado los avisos en algún dispositivo.</div>
      <div class="pf-msg" role="status"></div>
    </div>`);

  const msg = el.querySelector('.pf-msg');
  const say = (text, ok = false) => {
    msg.textContent = text;
    msg.className = `pf-msg ${text ? (ok ? 'ok' : 'err') : ''}`;
  };
  const save = async (changes, saved) => {
    try {
      await api(path, jsonRequest('PATCH', changes));
      say(saved, true);
      return true;
    } catch (err) {
      say(err.message);
      return false;
    }
  };

  for (const notice of NOTICES) {
    const boxes = [...el.querySelectorAll(`[data-notice="${notice.id}"] input`)];
    const options = el.querySelector(`[data-options="${notice.id}"]`);
    const sync = () => { options.hidden = !boxes.some((box) => box.checked); };
    sync();
    for (const box of boxes) {
      box.addEventListener('change', async () => {
        sync();
        const [telegram, push] = boxes;
        const sent = await save(
          { [`${notice.id}_telegram`]: telegram.checked, [`${notice.id}_push`]: push.checked },
          telegram.checked || push.checked ? 'Guardado' : 'Guardado: no te enviaremos este aviso',
        );
        if (!sent) {
          box.checked = !box.checked;
          sync();
        }
      });
    }
  }

  el.querySelector('[data-options="forgotten_timer"]').addEventListener('submit', async (e) => {
    e.preventDefault();
    const hours = parseHours(e.currentTarget.elements.hours.value);
    if (hours === undefined) return say(`Las horas deben ser un número entero entre ${MIN_HOURS} y ${MAX_HOURS}`);
    await save({ forgotten_timer_hours: hours }, hours === null ? `Guardado: se usarán las ${hoursDefault} horas por defecto` : 'Guardado');
  });
}
