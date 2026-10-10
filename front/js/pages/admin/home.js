// Home of the panel: figures, what needs attention and the state of the integrations.
// Everything is read when the page opens (/manage/overview, /manage/attention, /manage/settings).
import { api } from '../../lib/api.js';
import { formatTimestamp } from '../../lib/format.js';
import { html, mount } from '../../lib/html.js';
import { badge, errorState, overviewStats } from './components.js';

const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

// Each problem: what is wrong, and where to look at it.
function attentionItems(att) {
  const items = [];
  if (att.stale_timers) {
    items.push({
      text: `${plural(att.stale_timers, 'sesión lleva', 'sesiones llevan')} en curso más de ${att.stale_timer_hours} h (probablemente olvidadas)`,
      detail: att.stale_timers_oldest.map((t) => `${t.user} · ${t.game} · desde ${formatTimestamp(t.start_time)}`),
      go: 'Ver sesiones',
      tab: 'timers',
      filters: { active: true },
    });
  }
  if (att.users_without_telegram) {
    items.push({
      text: `${plural(att.users_without_telegram, 'jugador activo no tiene', 'jugadores activos no tienen')} Telegram ID: el bot no puede escribirles`,
      go: 'Ver usuarios',
      tab: 'users',
    });
  }
  if (att.games_without_rawg) {
    items.push({
      text: `${plural(att.games_without_rawg, 'juego no tiene', 'juegos no tienen')} ID de RAWG (sincronízalos para completar portada y metadatos)`,
      go: 'Ver juegos',
      tab: 'games',
      filters: { rawg: 'unlinked' },
    });
  }
  return items;
}

function integrations(cfg) {
  const v = cfg.values;
  const telegram = !v['telegram.token'].is_set
    ? ['red', 'Sin configurar', 'Falta TELEGRAM_TOKEN en el .env del servidor: no se envía nada por Telegram']
    : !v['telegram.group_id'].is_set ? ['orange', 'Sin grupo', 'Falta TELEGRAM_GROUP_ID en el .env del servidor: los avisos del grupo no salen']
    : v['notifications.enabled'] ? ['green', 'Activo', 'Bot configurado y notificaciones activadas'] : ['orange', 'Notificaciones apagadas', 'El bot está configurado, pero no se envía nada'];
  const ai = !v['ai.enabled'] ? ['gray', 'Apagada', 'Los avisos salen con el texto original']
    : v['ai.api_key'].is_set ? ['green', 'Activa', `${v['ai.provider']}${v['ai.model'] ? ` (${v['ai.model']})` : ''}`] : ['orange', 'Sin clave', 'Está activada, pero falta AI_API_KEY en el .env del servidor'];
  const push = v['push.enabled']
    ? ['green', 'Activos', `${plural(cfg.push_devices.devices, 'dispositivo suscrito', 'dispositivos suscritos')}`] : ['gray', 'Apagados', 'Nadie recibe avisos en la app'];
  const mail = cfg.mail.configured ? ['green', 'Configurado', `Envía como ${cfg.mail.from}`] : ['gray', 'Sin configurar', 'Nadie puede recuperar su contraseña por correo'];
  return [
    { name: 'Telegram', tab: 'notifications', state: telegram },
    { name: 'Inteligencia artificial', tab: 'system', state: ai },
    { name: 'Avisos en la app', tab: 'notifications', state: push },
    { name: 'Correo', tab: 'system', state: mail },
  ];
}

function view(ov, att, cfg) {
  const items = attentionItems(att);
  return html`
    <div class="adm-home">
      <div class="adm-stats">${overviewStats(ov)}</div>

      <section class="adm-card">
        <h2>Requiere atención</h2>
        ${items.length ? items.map((item, i) => html`
          <div class="adm-attn">
            <div>
              <div>${item.text}</div>
              ${(item.detail || []).map((line) => html`<div class="adm-sub">${line}</div>`)}
            </div>
            <button class="adm-btn sm" data-go="${i}">${item.go}</button>
          </div>`) : html`<div class="adm-ok">Todo en orden: nada que revisar.</div>`}
      </section>

      <section class="adm-card">
        <h2>Integraciones</h2>
        ${integrations(cfg).map((it, i) => html`
          <div class="adm-attn">
            <div><strong>${it.name}</strong> ${badge(it.state[1], it.state[0])}<div class="adm-sub">${it.state[2]}</div></div>
            <button class="adm-btn sm" data-setup="${i}">Configurar</button>
          </div>`)}
      </section>
    </div>`;
}

export async function render(panel, { admin }) {
  try {
    const [ov, att, cfg] = await Promise.all([api('/manage/overview'), api('/manage/attention'), api('/manage/settings')]);
    mount(panel, view(ov, att, cfg));
    const items = attentionItems(att);
    const setups = integrations(cfg);
    panel.querySelector('.adm-home').addEventListener('click', async (e) => {
      const button = e.target.closest('button');
      if (!button) return;
      const { go, setup } = button.dataset;
      if (go != null) admin.jumpTo(items[Number(go)].tab, items[Number(go)].filters || {});
      else if (setup != null) admin.open(setups[Number(setup)].tab);
    });
  } catch (err) {
    mount(panel, errorState(err.message));
  }
}
