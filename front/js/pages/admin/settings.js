// "Notificaciones" tab: general switches, weekly summary schedule and the
// Telegram bot (token, group, admin chat). Values live in the app_settings
// table; the API never returns the token, only whether it is set.
import { api, jsonRequest } from '../../lib/api.js';
import { formatDateTime } from '../../lib/format.js';
import { html, mount } from '../../lib/html.js';
import { toast } from '../../ui/toast.js';
import { errorState, store } from './components.js';
import { confirmDialog } from './dialogs.js';

const WEEKDAYS = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo'];

let panel;
let loaded = {}; // values as the server has them

const check = (name, label, hint) => html`
  <label class="adm-check adm-set-check"><input type="checkbox" name="${name}" /> <span><strong>${label}</strong><span class="adm-sub">${hint}</span></span></label>`;

function lastRun(job) {
  if (!job) return 'Todavía no se ha enviado ninguno.';
  return `Último envío: ${formatDateTime(job.last_run_at)}${job.last_status ? ` (${job.last_status})` : ''}.`;
}

function view(values, jobs, pushDevices) {
  const token = values['telegram.token'];
  const vapid = values['push.vapid_private'];
  return html`
    <form class="adm-settings" id="admSettings" novalidate>
      <section class="adm-set-card">
        <h3>Notificaciones</h3>
        ${check('notifications.enabled', 'Notificaciones activadas', 'Apagado, no se envía nada al grupo ni mensajes privados a los usuarios (resumen semanal, avisos de timer olvidado…).')}
        ${check('notifications.admin_alerts', 'Avisos a administradores', 'Errores y ejecuciones lentas, por mensaje privado a los admins con ID de Telegram. Funciona aunque las notificaciones generales estén apagadas.')}
      </section>

      <section class="adm-set-card">
        <h3>Resumen semanal</h3>
        ${check('weekly.enabled', 'Enviar el resumen semanal', 'Mensaje privado a cada usuario activo con ID de Telegram. Necesita las notificaciones activadas.')}
        <div class="adm-set-row">
          <label>Día
            <select class="adm-input" name="weekly.weekday">${WEEKDAYS.map((d, i) => html`<option value="${i}">${d}</option>`)}</select>
          </label>
          <label>Hora <input class="adm-input" type="time" name="weekly.time" required /></label>
        </div>
        <div class="adm-sub">Si el servidor está apagado a esa hora, se envía al volver siempre que no hayan pasado más de 6 horas. ${lastRun(jobs.weekly_summary)}</div>
      </section>

      <section class="adm-set-card">
        <h3>Telegram</h3>
        <label>Token del bot
          <input class="adm-input" type="password" name="telegram.token" autocomplete="new-password"
                 placeholder="${token.is_set ? `Configurado (${token.hint}). Escribe uno nuevo para cambiarlo` : 'Sin configurar'}" />
        </label>
        <label>ID del canal o grupo <input class="adm-input" type="text" name="telegram.group_id" inputmode="numeric" /></label>
        <label>ID del chat de administración <input class="adm-input" type="text" name="telegram.admin_chat_id" inputmode="numeric" /></label>
        <div class="adm-sub">El bot se reinicia solo (en un minuto aproximadamente) cuando cambia alguno de estos valores. Los grupos tienen IDs negativos.</div>
        <div><button type="button" class="adm-btn" data-set-act="test">Enviar mensaje de prueba al grupo</button></div>
      </section>

      <section class="adm-set-card">
        <h3>Avisos en la app (push)</h3>
        ${check('push.enabled', 'Enviar avisos a la app instalada', 'Función activa para todos por defecto; nadie recibe nada hasta que cada usuario lo active en su perfil («Avisos en la app») y elija en qué dispositivos. Los avisos del grupo llegan a quien los marque y los privados (timer olvidado…) solo a su usuario. Necesita las notificaciones activadas y HTTPS.')}
        <label>Contacto para los servicios push
          <input class="adm-input" type="text" name="push.contact" placeholder="mailto:tu@correo.com (vacío: usa el correo SMTP)" />
        </label>
        <div class="adm-sub">${vapid.is_set ? 'Las claves del servidor se crearon solas al arrancar; son las mismas para todos los usuarios.' : 'Sin claves (se crean al arrancar la API).'}</div>
        <div class="adm-sub">${pushDevices.devices} dispositivo${pushDevices.devices === 1 ? '' : 's'} suscrito${pushDevices.devices === 1 ? '' : 's'} (${pushDevices.users} usuario${pushDevices.users === 1 ? '' : 's'}).</div>
        <div class="adm-set-row">
          <label>Enviar aviso de prueba a
            <select class="adm-input" id="admPushTarget">
              <option value="me">Mis dispositivos</option>
              <option value="user">Un usuario…</option>
              <option value="all">Todos los dispositivos suscritos</option>
            </select>
          </label>
          <label id="admPushUserWrap" hidden>Usuario
            <select class="adm-input" id="admPushUser">${store.users.map((u) => html`<option value="${u.id}">${u.username}</option>`)}</select>
          </label>
        </div>
        <label>Mensaje <input class="adm-input" type="text" id="admPushMessage" maxlength="200" placeholder="Si lo lees, las notificaciones push funcionan." /></label>
        <div class="adm-set-row">
          <button type="button" class="adm-btn" data-set-act="push-test">Enviar aviso de prueba</button>
          <button type="button" class="adm-btn" data-set-act="push-keys">Regenerar claves…</button>
        </div>
      </section>

      <div class="adm-error" role="alert"></div>
      <div class="adm-actions adm-set-actions"><button class="adm-btn primary" type="submit">Guardar cambios</button></div>
    </form>`;
}

function fill(form, values) {
  for (const [key, value] of Object.entries(values)) {
    const field = form.elements[key];
    if (!field || key === 'telegram.token') continue;
    if (field.type === 'checkbox') field.checked = Boolean(value);
    else field.value = value ?? '';
  }
}

function collect(form) {
  const changes = {};
  for (const [key, before] of Object.entries(loaded)) {
    const field = form.elements[key];
    if (!field) continue;
    if (key === 'telegram.token') {
      if (field.value.trim()) changes[key] = field.value.trim();
      continue;
    }
    const now = field.type === 'checkbox' ? field.checked : field.type === 'select-one' ? Number(field.value) : field.value.trim();
    if (now === '' && before == null) continue; // an optional text left empty
    if (now !== before) changes[key] = now;
  }
  return changes;
}

async function save(form) {
  const errorEl = form.querySelector('.adm-error');
  errorEl.textContent = '';
  const changes = collect(form);
  if (!Object.keys(changes).length) return toast('No hay cambios');
  try {
    await api('/manage/settings', jsonRequest('PUT', { values: changes }));
    toast('Ajustes guardados');
    await render(panel);
  } catch (err) {
    errorEl.textContent = err.message;
  }
}

async function sendTest() {
  const ok = await confirmDialog('Mensaje de prueba', html`<p>Se enviará un mensaje de prueba al grupo de Telegram configurado, aunque las notificaciones estén apagadas.</p>`, { ok: 'Enviar' });
  if (!ok) return;
  try {
    await api('/manage/settings/test-message', { method: 'POST' });
    toast('Mensaje de prueba enviado');
  } catch (err) {
    toast(err.message, 'err');
  }
}

async function generateKeys(replace) {
  if (replace) {
    const ok = await confirmDialog('Regenerar claves', html`<p>Todos los dispositivos suscritos dejarán de recibir avisos y cada usuario tendrá que volver a activarlos.</p>`, { danger: true, ok: 'Regenerar' });
    if (!ok) return;
  }
  try {
    await api(`/manage/settings/push-keys${replace ? '?replace=true' : ''}`, { method: 'POST' });
    toast('Claves generadas');
    await render(panel);
  } catch (err) {
    toast(err.message, 'err');
  }
}

async function sendTestPush(form) {
  const target = form.querySelector('#admPushTarget').value;
  const body = { target, message: form.querySelector('#admPushMessage').value.trim() || null };
  if (target === 'user') body.user_id = Number(form.querySelector('#admPushUser').value);
  if (target === 'all') {
    const ok = await confirmDialog('Aviso de prueba', html`<p>Se enviará a <strong>todos</strong> los dispositivos suscritos, de todos los usuarios.</p>`, { ok: 'Enviar' });
    if (!ok) return;
  }
  try {
    const { sent } = await api('/manage/settings/test-push', jsonRequest('POST', body));
    toast(`Aviso enviado a ${sent} dispositivo${sent === 1 ? '' : 's'}`);
  } catch (err) {
    toast(err.message, 'err');
  }
}

export async function render(target) {
  panel = target;
  try {
    const { values, jobs, push_devices: pushDevices } = await api('/manage/settings');
    loaded = Object.fromEntries(Object.entries(values).filter(([key]) => key !== 'telegram.token' && !key.startsWith('push.vapid')));
    loaded['telegram.token'] = null;
    mount(panel, view(values, jobs, pushDevices));
    const form = panel.querySelector('#admSettings');
    fill(form, values);
    form.addEventListener('submit', (e) => { e.preventDefault(); save(form); });
    form.addEventListener('click', (e) => {
      const act = e.target.closest('[data-set-act]')?.dataset.setAct;
      if (act === 'test') sendTest();
      else if (act === 'push-keys') generateKeys(values['push.vapid_private'].is_set);
      else if (act === 'push-test') sendTestPush(form);
    });
    form.addEventListener('change', (e) => {
      if (e.target.id === 'admPushTarget') form.querySelector('#admPushUserWrap').hidden = e.target.value !== 'user';
    });
  } catch (err) {
    mount(panel, errorState(err.message));
  }
}
