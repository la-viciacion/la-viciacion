// One-time invitation to turn on push notifications on this device.
// Browsers only allow asking for the permission after a click, so the server cannot
// subscribe anybody by itself; this banner is the shortest way to that click.
import { api } from '../lib/api.js';
import { html, mount } from '../lib/html.js';
import { currentSubscription, enablePush, needsInstall, pushSupported } from '../lib/push.js';
import { toast } from './toast.js';

const DISMISSED = 'lv-push-invite';

const remembered = () => {
  try { return localStorage.getItem(DISMISSED) === '1'; } catch { return false; }
};
const remember = () => {
  try { localStorage.setItem(DISMISSED, '1'); } catch { /* private mode: it will ask again next time */ }
};

export async function inviteToPush() {
  const standalone = window.matchMedia?.('(display-mode: standalone)').matches || navigator.standalone === true;
  if (document.querySelector('.push-invite') || remembered() || needsInstall(navigator.userAgent, standalone) || !pushSupported() || Notification.permission !== 'default') return;
  const config = await api('/push/config');
  if (!config?.enabled || (await currentSubscription())) return;

  const banner = document.createElement('div');
  banner.className = 'push-invite';
  banner.setAttribute('role', 'dialog');
  banner.setAttribute('aria-label', 'Activar avisos');
  document.body.appendChild(banner);
  mount(banner, html`
    <div class="push-invite-text"><strong>¿Quieres recibir los avisos en este dispositivo?</strong><span>Rankings, logros y recordatorios como notificaciones. Puedes cambiarlo cuando quieras en tu perfil.</span></div>
    <div class="push-invite-actions">
      <button class="pf-btn primary" data-act="yes" type="button">Activar</button>
      <button class="pf-btn" data-act="no" type="button">Ahora no</button>
    </div>`);
  banner.addEventListener('click', async (e) => {
    const act = e.target.closest('button[data-act]')?.dataset.act;
    if (!act) return;
    remember();
    banner.remove();
    if (act !== 'yes') return;
    try {
      await enablePush({ publicKey: config.public_key, receiveGroup: true });
      toast('Avisos activados en este dispositivo');
    } catch (err) {
      toast(err.message, 'err');
    }
  });
}
