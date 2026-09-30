// "Avisos en este dispositivo": subscribe the installed PWA to push notifications.
// Hidden while the server has push off or the browser cannot do it.
import { api } from '../../lib/api.js';
import { html, mount } from '../../lib/html.js';
import { currentSubscription, disablePush, enablePush, pushSupported, setReceiveGroup } from '../../lib/push.js';

export async function initPush(el) {
  if (!pushSupported()) return;
  const config = await api('/push/config');
  if (!config?.enabled) return;

  const draw = async () => {
    const subscription = await currentSubscription();
    const device = subscription && config.devices.find((d) => d.endpoint === subscription.endpoint);
    mount(el, html`
      <div class="section-header"><h2 class="section-title">Avisos en este dispositivo</h2><div class="section-line"></div></div>
      <div class="pf-card pf-form">
        <div class="pf-sub">Recibe los avisos de La Viciación en este dispositivo aunque la app esté cerrada. Los avisos privados (por ejemplo, un timer olvidado) llegan siempre.</div>
        ${device ? html`
          <label class="adm-check"><input type="checkbox" id="pfPushGroup" ${device.receive_group ? html`checked` : ''} /> Recibir también los avisos del grupo</label>` : ''}
        <div class="pf-msg" id="pfPushMsg" role="status"></div>
        <div><button class="pf-btn ${device ? '' : 'primary'}" id="pfPushToggle" type="button">${device ? 'Desactivar avisos' : 'Activar avisos'}</button></div>
      </div>`);
    const message = el.querySelector('#pfPushMsg');
    const fail = (err) => { message.textContent = err.message; message.className = 'pf-msg err'; };
    el.querySelector('#pfPushToggle').addEventListener('click', async () => {
      try {
        if (device) await disablePush();
        else await enablePush({ publicKey: config.public_key, receiveGroup: true });
        Object.assign(config, await api('/push/config'));
        await draw();
      } catch (err) { fail(err); }
    });
    el.querySelector('#pfPushGroup')?.addEventListener('change', async (e) => {
      try {
        await setReceiveGroup(e.target.checked);
        device.receive_group = e.target.checked;
      } catch (err) { fail(err); }
    });
  };
  await draw();
}
