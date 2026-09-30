// "Avisos en la app": each user chooses here whether this device (and which of
// their devices) receives push notifications. The admin only turns the feature
// on for everybody (Notificaciones tab); nobody is subscribed without asking.
import { api } from '../../lib/api.js';
import { formatDate } from '../../lib/format.js';
import { html, mount } from '../../lib/html.js';
import { currentSubscription, deviceLabel, enablePush, needsInstall, pushSupported, removeDevice, setReceiveGroup } from '../../lib/push.js';

const isStandalone = () => window.matchMedia?.('(display-mode: standalone)').matches || navigator.standalone === true;

const title = html`<div class="section-header"><h2 class="section-title">Avisos en la app</h2><div class="section-line"></div></div>`;

const notice = (text) => html`${title}<div class="pf-card"><div class="pf-sub">${text}</div></div>`;

/** Why this device cannot turn notifications on, or null. */
function blocker(config) {
  if (needsInstall(navigator.userAgent, isStandalone())) return 'En iPhone y iPad hay que instalar la app primero: en Safari pulsa Compartir y «Añadir a pantalla de inicio», y actívalos desde la app instalada.';
  if (!pushSupported()) return 'Este navegador no admite notificaciones de la app.';
  if (!config.enabled) return 'El administrador todavía no ha activado los avisos en la app.';
  if (Notification.permission === 'denied') return 'Has bloqueado las notificaciones para este sitio en el navegador. Permítelas en los ajustes del sitio y vuelve aquí.';
  return null;
}

export async function initPush(el) {
  const config = await api('/push/config');
  if (!config) return;

  const say = (text, ok = false) => {
    const message = el.querySelector('#pfPushMsg');
    if (!message) return;
    message.textContent = text;
    message.className = `pf-msg ${text ? (ok ? 'ok' : 'err') : ''}`;
  };

  const draw = async () => {
    const blocked = blocker(config);
    const current = pushSupported() ? await currentSubscription() : null;
    const here = current && config.devices.find((d) => d.endpoint === current.endpoint);
    if (blocked && !config.devices.length) return mount(el, notice(blocked));

    mount(el, html`
      ${title}
      <div class="pf-card pf-form">
        <div class="pf-sub">Recibe los avisos de La Viciación como notificaciones, aunque la app esté cerrada. Los avisos privados (por ejemplo, un timer olvidado) llegan siempre a los dispositivos activados; los del grupo, solo a los que lo marquen.</div>
        ${blocked ? html`<div class="pf-msg err">${blocked}</div>` : ''}
        ${config.devices.map((d, i) => html`
          <div class="pf-row">
            <div class="pf-row-main">
              <strong>${deviceLabel(d.user_agent)}</strong>${here?.endpoint === d.endpoint ? html` <span class="pf-sub">(este dispositivo)</span>` : ''}
              <div class="pf-sub">Activado el ${formatDate(d.created_at)}</div>
            </div>
            <label class="adm-check"><input type="checkbox" data-act="group" data-i="${i}" ${d.receive_group ? html`checked` : ''} /> Avisos del grupo</label>
            <button class="pf-btn" type="button" data-act="remove" data-i="${i}">Quitar</button>
          </div>`)}
        <div class="pf-msg" id="pfPushMsg" role="status"></div>
        ${!blocked && !here ? html`<div><button class="pf-btn primary" data-act="enable" type="button">Activar avisos en este dispositivo</button></div>` : ''}
      </div>`);
  };

  const refresh = async () => {
    Object.assign(config, await api('/push/config'));
    await draw();
  };

  // one set of listeners for the life of the card: draw() replaces the markup, not `el`
  el.addEventListener('click', async (e) => {
    const button = e.target.closest('button[data-act]');
    if (!button) return;
    try {
      if (button.dataset.act === 'enable') await enablePush({ publicKey: config.public_key, receiveGroup: true });
      else await removeDevice(config.devices[Number(button.dataset.i)].endpoint);
      await refresh();
    } catch (err) { say(err.message); }
  });
  el.addEventListener('change', async (e) => {
    const box = e.target.closest('input[data-act="group"]');
    if (!box) return;
    const device = config.devices[Number(box.dataset.i)];
    try {
      await setReceiveGroup(device.endpoint, box.checked);
      device.receive_group = box.checked;
      say('Guardado', true);
    } catch (err) {
      box.checked = !box.checked;
      say(err.message);
    }
  });

  await draw();
}
