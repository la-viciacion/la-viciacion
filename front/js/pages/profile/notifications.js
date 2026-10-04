// "Notificaciones" of the profile: which private notices the user wants, through which channel
// (PATCH /users/{username}/settings). Each notice is a card: an on/off switch and, once on, its
// channels (Telegram and/or the devices with push) and its own options. A notice is off when both
// channels are off, so there is no separate "enabled" setting. The next notices are one more card.
import { api, jsonRequest } from '../../lib/api.js';
import { HOURS_HINT, MAX_HOURS, MIN_HOURS, parseHours } from '../../lib/hours.js';
import { html, mount } from '../../lib/html.js';

/** A notice is on when at least one of its channels is (an unset channel uses the default). */
export function noticeOn(settings, notice) {
  const channel = (name) => settings[`${notice}_${name}`] ?? settings.defaults[`${notice}_${name}`];
  return Boolean(channel('telegram') || channel('push'));
}

export async function initNotifications(el, { path }) {
  const settings = await api(path);
  if (!settings) return;
  const hoursDefault = settings.defaults.forgotten_timer_hours;
  const channel = (name) => settings[`forgotten_timer_${name}`] ?? settings.defaults[`forgotten_timer_${name}`];
  const on = noticeOn(settings, 'forgotten_timer');

  mount(el, html`
    <div class="section-header"><h2 class="section-title">Notificaciones</h2><div class="section-line"></div></div>
    <form class="pf-card pf-form" id="pfForgotten" novalidate>
      <label class="adm-check"><input type="checkbox" name="enabled" ${on ? 'checked' : ''} /> Avisarme si me dejo un timer activo</label>
      <div class="pf-options" ${on ? '' : 'hidden'}>
        <label class="adm-check"><input type="checkbox" name="telegram" ${channel('telegram') ? 'checked' : ''} /> Por Telegram</label>
        <label class="adm-check"><input type="checkbox" name="push" ${channel('push') ? 'checked' : ''} /> En mis dispositivos (push)</label>
        <label>Avisarme si un timer lleva activo más de (horas)
          <input class="adm-input" type="number" name="hours" inputmode="numeric" step="1" min="${MIN_HOURS}" max="${MAX_HOURS}"
            value="${settings.forgotten_timer_hours ?? ''}" placeholder="${hoursDefault}" />
        </label>
        <div class="pf-sub">${HOURS_HINT} Si lo dejas vacío, te avisamos a las ${hoursDefault} horas. El aviso se comprueba cada hora, así que puede llegar hasta una hora después. Solo llega por los canales que tengas disponibles: Telegram si has activado el bot, push si has activado los avisos en algún dispositivo.</div>
        <div><button class="pf-btn primary" type="submit">Guardar</button></div>
      </div>
      <div class="pf-msg" role="status"></div>
    </form>`);

  const form = el.querySelector('#pfForgotten');
  const { enabled, telegram, push, hours: hoursField } = form.elements;
  const options = form.querySelector('.pf-options');
  const msg = form.querySelector('.pf-msg');
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

  enabled.addEventListener('change', async () => {
    const turnedOn = enabled.checked;
    if (turnedOn && !telegram.checked && !push.checked) telegram.checked = push.checked = true;
    options.hidden = !turnedOn;
    const changes = turnedOn
      ? { forgotten_timer_telegram: telegram.checked, forgotten_timer_push: push.checked }
      : { forgotten_timer_telegram: false, forgotten_timer_push: false };
    if (!(await save(changes, turnedOn ? 'Guardado: te avisaremos' : 'Guardado: no te avisaremos'))) {
      enabled.checked = !turnedOn;
      options.hidden = turnedOn;
    }
  });

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!telegram.checked && !push.checked) return say('Elige al menos un canal, o desactiva el aviso');
    const hours = parseHours(hoursField.value);
    if (hours === undefined) return say(`Las horas deben ser un número entero entre ${MIN_HOURS} y ${MAX_HOURS}`);
    await save(
      { forgotten_timer_telegram: telegram.checked, forgotten_timer_push: push.checked, forgotten_timer_hours: hours },
      hours === null ? `Guardado: se usarán las ${hoursDefault} horas por defecto` : 'Guardado',
    );
  });
}
