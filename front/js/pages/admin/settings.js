// Settings pages of the admin panel: general switches, weekly summary schedule, the Telegram bot
// (token, group, admin chat), the AI that writes the notices (provider, key, model), push and mail.
// They are all one form split in cards; each page (see entities.js) shows the cards listed in its
// `sections`, and saving sends only the fields on screen that changed.
// Values live in the app_settings table; the API never returns a secret (the Telegram
// token, the AI key), only whether it is set.
import { api, jsonRequest } from '../../lib/api.js';
import { saveFile } from '../../lib/download.js';
import { formatDateTime } from '../../lib/format.js';
import { html, mount } from '../../lib/html.js';
import { toast } from '../../ui/toast.js';
import { errorState } from './components.js';
import { confirmDialog } from './dialogs.js';

const SECRETS = ['telegram.token', 'ai.api_key']; // never loaded back: sent only when something is typed
const READ_ONLY = ['mail', 'backup']; // cards with nothing to save
const AI_PROVIDERS = [['google', 'Google (Gemini)'], ['openai', 'OpenAI']];

const WEEKDAYS = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo'];

let panel;
let sections = []; // cards of the page on screen
let loaded = {}; // values as the server has them
let aiUses = []; // where the AI writes: label, original prompt and whether it was changed

const check = (name, label, hint) => html`
  <label class="adm-check adm-set-check"><input type="checkbox" name="${name}" /> <span><strong>${label}</strong><span class="adm-sub">${hint}</span></span></label>`;

function lastRun(job) {
  if (!job) return 'Todavía no se ha enviado ninguno.';
  return `Último envío: ${formatDateTime(job.last_run_at)}${job.last_status ? ` (${job.last_status})` : ''}.`;
}

function mailStatus(mail) {
  if (!mail.configured) return `Sin configurar: faltan ${mail.missing.join(', ')} en el .env.`;
  return `Configurado: envía como ${mail.from} por ${mail.host}:${mail.port} (${mail.security}); los enlaces apuntan a ${mail.public_url}.`;
}

// One notice that can use the AI: its own switch (a fragment has none) and its editable instructions.
function aiUse(use) {
  return html`
    <div class="adm-ai-use">
      ${use.switchable
    ? check(`ai.use.${use.id}`, use.label, use.help)
    : html`<div><strong>${use.label}</strong><span class="adm-sub">${use.help}</span></div>`}
      <details class="adm-details">
        <summary>Instrucciones${use.customized ? ' (modificadas)' : ''}</summary>
        <div>
          <textarea class="adm-input" name="ai.prompt.${use.id}" rows="9" spellcheck="false"></textarea>
          <button type="button" class="adm-btn" data-set-act="reset-prompt" data-use="${use.id}">Restaurar las originales</button>
        </div>
      </details>
    </div>`;
}

function view(values, jobs, pushDevices, mail, aiUses) {
  const token = values['telegram.token'];
  const aiKey = values['ai.api_key'];
  const vapid = values['push.vapid_private'];
  const cards = {
    notifications: html`
      <section class="adm-set-card">
        <h3>Notificaciones</h3>
        ${check('notifications.enabled', 'Notificaciones activadas', 'Apagado, no se envía nada al grupo ni mensajes privados a los usuarios (resumen semanal, avisos de timer olvidado…).')}
        ${check('notifications.admin_alerts', 'Avisos a administradores', 'Errores y ejecuciones lentas, por mensaje privado a los admins con ID de Telegram. Funciona aunque las notificaciones generales estén apagadas.')}
      </section>`,

    weekly: html`
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
      </section>`,

    telegram: html`
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
      </section>`,

    ai: html`
      <section class="adm-set-card">
        <h3>Inteligencia artificial</h3>
        ${check('ai.enabled', 'Usar IA en los avisos', 'Apagada, los avisos salen con el texto original. Necesita una clave guardada para funcionar.')}
        <label>Proveedor
          <select class="adm-input" name="ai.provider">${AI_PROVIDERS.map(([id, label]) => html`<option value="${id}">${label}</option>`)}</select>
        </label>
        <label>Clave de la API
          <input class="adm-input" type="password" name="ai.api_key" autocomplete="new-password"
                 placeholder="${aiKey.is_set ? `Configurada (${aiKey.hint}). Escribe una nueva para cambiarla` : 'Sin configurar'}" />
        </label>
        <label>Modelo <input class="adm-input" type="text" name="ai.model" placeholder="Vacío: el modelo por defecto del proveedor" /></label>
        <div class="adm-sub">Se aplica al momento, sin reiniciar. La clave se guarda cifrada y no se vuelve a mostrar. Por defecto: Google <code>gemini-2.5-flash</code>, OpenAI <code>gpt-4o-mini</code>.</div>
        <div><button type="button" class="adm-btn" data-set-act="test-ai" ${aiKey.is_set ? '' : html`disabled`}>Probar la IA</button></div>
      </section>`,

    aiuses: html`
      <section class="adm-set-card">
        <h3>Avisos que usan la IA</h3>
        <div class="adm-sub">Cada aviso se puede activar o desactivar por separado (con la IA general apagada no se usa ninguno), y sus instrucciones se pueden cambiar. Mientras no las cambies, siguen las que trae la aplicación; al restaurarlas vuelven a seguirlas.</div>
        ${aiUses.map((use) => aiUse(use))}
      </section>`,

    push: html`
      <section class="adm-set-card">
        <h3>Avisos en la app (push)</h3>
        ${check('push.enabled', 'Enviar avisos a la app instalada', 'Función activa para todos por defecto; nadie recibe nada hasta que cada usuario lo active en su perfil (Ajustes → Notificaciones) y elija en qué dispositivos. Los avisos del grupo llegan a quien los marque y los privados (timer olvidado…) solo a su usuario. Necesita las notificaciones activadas y HTTPS.')}
        <label>Contacto para los servicios push
          <input class="adm-input" type="text" name="push.contact" placeholder="mailto:tu@correo.com (vacío: usa el remitente del correo o la dirección pública)" />
        </label>
        <div class="adm-sub">${vapid.is_set ? 'Las claves del servidor se crearon solas al arrancar; son las mismas para todos los usuarios.' : 'Sin claves (se crean al arrancar la API).'}</div>
        <div class="adm-sub">${pushDevices.devices} dispositivo${pushDevices.devices === 1 ? '' : 's'} suscrito${pushDevices.devices === 1 ? '' : 's'} (${pushDevices.users} usuario${pushDevices.users === 1 ? '' : 's'}).</div>
        <div class="adm-sub">Para redactar y enviar avisos (o probarlos en tus dispositivos) usa <strong>Redactar aviso</strong>.</div>
        <div><button type="button" class="adm-btn" data-set-act="push-keys">Regenerar claves…</button></div>
      </section>`,

    backup: html`
      <section class="adm-set-card">
        <h3>Copia de seguridad</h3>
        <div class="adm-sub">Descarga toda la base de datos en un archivo .sql.gz (un .sql comprimido): usuarios, sesiones, biblioteca, logros, ajustes y fotos. Se restaura en una base vacía con el cliente de MariaDB (mira docs/deployment.md). Contiene las contraseñas cifradas y los ajustes protegidos, así que guárdala como lo que es: fuera del repositorio y sin compartirla.</div>
        <div><button type="button" class="adm-btn" data-set-act="backup">Descargar copia (.sql.gz)</button></div>
      </section>`,

    mail: html`
      <section class="adm-set-card">
        <h3>Correo (recuperar contraseña)</h3>
        <div class="adm-sub">${mailStatus(mail)}</div>
        <div class="adm-sub">Se configura en el <code>.env</code> (<code>PUBLIC_URL</code>, <code>SMTP_*</code>) y se aplica al reiniciar la API. El inicio de sesión ofrece «¿Has olvidado tu contraseña?» y este correo es el que lleva el enlace.</div>
        <div class="adm-sub">${mail.test_recipient ? `La prueba se envía a tu email: ${mail.test_recipient}.` : 'Tu cuenta no tiene email: añádelo en Usuarios → Editar para poder recibir la prueba.'}</div>
        <div><button type="button" class="adm-btn" data-set-act="test-email" ${mail.configured && mail.test_recipient ? '' : html`disabled`}>Enviar correo de prueba a mi cuenta</button></div>
      </section>`,
  };
  const editable = sections.some((id) => !READ_ONLY.includes(id));
  return html`
    <form class="adm-settings" id="admSettings" novalidate>
      ${sections.map((id) => cards[id])}
      ${editable ? html`
        <div class="adm-error" role="alert"></div>
        <div class="adm-actions adm-set-actions"><button class="adm-btn primary" type="submit">Guardar cambios</button></div>` : ''}
    </form>`;
}

function fill(form, values) {
  for (const [key, value] of Object.entries(values)) {
    const field = form.elements[key];
    if (!field || SECRETS.includes(key)) continue;
    if (field.type === 'checkbox') field.checked = Boolean(value);
    else field.value = value ?? '';
  }
}

function collect(form) {
  const changes = {};
  for (const [key, before] of Object.entries(loaded)) {
    const field = form.elements[key];
    if (!field) continue;
    if (SECRETS.includes(key)) {
      if (field.value.trim()) changes[key] = field.value.trim();
      continue;
    }
    const isNumber = typeof before === 'number';
    const now = field.type === 'checkbox' ? field.checked : field.type === 'select-one' && isNumber ? Number(field.value) : field.value.trim();
    if (key.startsWith('ai.prompt.')) {
      // the original text (or nothing) is not an override: it goes back to following the application's prompt
      const use = aiUses.find((u) => `ai.prompt.${u.id}` === key);
      if (now === '' || now === use.default_prompt.trim()) {
        if (use.customized) changes[key] = null;
      } else if (now !== before) {
        changes[key] = now;
      }
      continue;
    }
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
    await render(panel, { entity: { sections } });
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

async function downloadBackup(button) {
  const ok = await confirmDialog('Copia de seguridad', html`<p>Se descargará toda la base de datos, con las contraseñas cifradas de todos los usuarios. Queda anotado en el registro.</p>`, { ok: 'Descargar' });
  if (!ok) return;
  button.disabled = true;
  try {
    const backup = await api('/manage/backup', { method: 'POST' });
    saveFile(`laviciacion-backup-${new Date().toLocaleDateString('sv-SE')}.sql.gz`, backup, 'application/gzip');
    toast('Copia descargada');
  } catch (err) {
    toast(err.message, 'err');
  } finally {
    button.disabled = false;
  }
}

async function sendTestEmail(mail) {
  const ok = await confirmDialog('Correo de prueba', html`<p>Se enviará un correo de prueba a <strong>${mail.test_recipient}</strong> desde ${mail.from}.</p>`, { ok: 'Enviar' });
  if (!ok) return;
  try {
    const result = await api('/manage/settings/test-email', { method: 'POST' });
    toast(result.message);
  } catch (err) {
    toast(err.message, 'err');
  }
}

// What was typed but not saved yet is not what the test uses: it asks the API, which uses what is stored.
async function testAi(form) {
  // the prompts and the per-notice switches are not part of the test
  if (Object.keys(collect(form)).some((key) => key.startsWith('ai.') && !key.startsWith('ai.prompt.') && !key.startsWith('ai.use.'))) {
    return toast('Guarda los cambios antes de probar la IA', 'err');
  }
  toast('Probando la IA…');
  try {
    const result = await api('/manage/settings/test-ai', { method: 'POST' });
    toast(`${result.provider} (${result.model}) responde: ${result.reply}`);
  } catch (err) {
    toast(err.message, 'err');
  }
}

// Puts the original instructions back in the box; they take effect when the changes are saved.
function resetPrompt(form, id) {
  form.elements[`ai.prompt.${id}`].value = aiUses.find((u) => u.id === id).default_prompt.trim();
  toast('Instrucciones originales restauradas: guarda los cambios para aplicarlo');
}

async function generateKeys(replace) {
  if (replace) {
    const ok = await confirmDialog('Regenerar claves', html`<p>Todos los dispositivos suscritos dejarán de recibir avisos y cada usuario tendrá que volver a activarlos.</p>`, { danger: true, ok: 'Regenerar' });
    if (!ok) return;
  }
  try {
    await api(`/manage/settings/push-keys${replace ? '?replace=true' : ''}`, { method: 'POST' });
    toast('Claves generadas');
    await render(panel, { entity: { sections } });
  } catch (err) {
    toast(err.message, 'err');
  }
}

export async function render(target, { entity }) {
  panel = target;
  sections = entity.sections;
  try {
    const { values, jobs, push_devices: pushDevices, mail, ai_uses: uses } = await api('/manage/settings');
    aiUses = uses;
    loaded = Object.fromEntries(Object.entries(values).filter(([key]) => !SECRETS.includes(key) && !key.startsWith('push.vapid')));
    for (const key of SECRETS) loaded[key] = null;
    mount(panel, view(values, jobs, pushDevices, mail, aiUses));
    const form = panel.querySelector('#admSettings');
    fill(form, values);
    form.addEventListener('submit', (e) => { e.preventDefault(); save(form); });
    form.addEventListener('click', (e) => {
      const act = e.target.closest('[data-set-act]')?.dataset.setAct;
      if (act === 'test') sendTest();
      else if (act === 'backup') downloadBackup(e.target.closest('[data-set-act]'));
      else if (act === 'test-email') sendTestEmail(mail);
      else if (act === 'test-ai') testAi(form);
      else if (act === 'reset-prompt') resetPrompt(form, e.target.closest('[data-use]').dataset.use);
      else if (act === 'push-keys') generateKeys(values['push.vapid_private'].is_set);
    });
  } catch (err) {
    mount(panel, errorState(err.message));
  }
}
