// Settings pages of the admin panel: general switches, weekly summary schedule, the Telegram bot
// (token, group, admin chat), the AI that writes the notices (provider, key, model), the chat (its own switch and instructions;
// it shares the AI's provider and key, and its model may be its own), push and mail.
// They are all one form split in cards; each page (see entities.js) shows the cards listed in its
// `sections`, and saving sends only the fields on screen that changed.
// Values live in the app_settings table; the API never returns a secret (the AI key), only whether it is set.
// The Telegram token and chats are not in it: they come from the server's .env and only whether they are set is shown.
import { api, jsonRequest } from '../../lib/api.js';
import { saveFile } from '../../lib/download.js';
import { formatDateTime } from '../../lib/format.js';
import { html, mount } from '../../lib/html.js';
import { toast } from '../../ui/toast.js';
import { errorState } from './components.js';
import { confirmDialog } from './dialogs.js';

const SECRETS = []; // never loaded back: sent only when something is typed (the keys of outside services are not: they are in the server's .env)
const LOCKED = ['telegram.token', 'telegram.group_id', 'telegram.admin_chat_id', 'ai.api_key', 'ai.provider', 'ai.model', 'chat.model']; // shown only as set or not, never editable
// the questions the chat answers, per player and for the whole group (api/src/utils/settings.py chat.limit_*)
const CHAT_LIMITS = [
  ['chat.limit_user_minute', 'Por jugador, por minuto'],
  ['chat.limit_user_hour', 'Por jugador, por hora'],
  ['chat.limit_user_day', 'Por jugador, por día'],
  ['chat.limit_group_minute', 'Grupo, por minuto'],
  ['chat.limit_group_day', 'Grupo, por día'],
];
const READ_ONLY = ['mail', 'backup']; // cards with nothing to save
const AI_PROVIDERS = [['google', 'Google (Gemini)'], ['openai', 'OpenAI']];

const ANNUAL_MONTHS = [[12, 'Diciembre'], [1, 'Enero']];
// the days the annual recap can go out on, by month (api/src/utils/settings.py ANNUAL_DAYS)
export const ANNUAL_DAYS = { 12: [20, 28], 1: [1, 5] };

// how the group hears about the wished games that come out (api/src/utils/settings.py WISHLIST_GROUP_NOTICES)
const WISHLIST_NOTICES = [['eve', 'La víspera de cada estreno'], ['weekly', 'Una vez por semana'], ['off', 'Ninguno']];

const WEEKDAYS = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo'];

let panel;
let sections = []; // cards of the page on screen
let loaded = {}; // values as the server has them
let aiUses = []; // where the AI writes: label, original prompt and whether it was changed
let chatInfo = {}; // the chat: the provider and model it uses (and whether the model is its own), original instructions and whether they were changed

const check = (name, label, hint, tag = '') => html`
  <label class="adm-check adm-set-check"><input type="checkbox" name="${name}" /> <span><strong>${label}${tag}</strong><span class="adm-sub">${hint}</span></span></label>`;

function lastRun(job) {
  if (!job) return 'Todavía no se ha enviado ninguno.';
  return `Último envío: ${formatDateTime(job.last_run_at)}${job.last_status ? ` (${job.last_status})` : ''}.`;
}

function mailStatus(mail) {
  if (!mail.configured) return `Sin configurar: faltan ${mail.missing.join(', ')} en el .env.`;
  return `Configurado: envía como ${mail.from} por ${mail.host}:${mail.port} (${mail.security}); los enlaces apuntan a ${mail.public_url}.`;
}

// What the chat still needs in the server's .env: the AI's provider and key, and a model (its own, or the AI's)
function chatMissing(values, chat) {
  return [
    !chat.provider && 'AI_PROVIDER',
    !values['ai.api_key'].is_set && 'AI_API_KEY',
    !chat.model && 'AI_MODEL (o CHAT_AI_MODEL)',
  ].filter(Boolean);
}

/** Whether the players get the chat button now, and if not why (what is saved, not what is typed). */
function chatState(values, chat) {
  const reasons = [
    !values['chat.enabled'] && 'el chat está apagado',
    chatMissing(values, chat).length && `falta ${chatMissing(values, chat).join(', ')} en el .env`,
  ].filter(Boolean);
  return reasons.length ? `No disponible: ${reasons.join('; ')}.` : 'Disponible: los jugadores ven el botón del chat.';
}

const customizedTag = (use) => (use.customized ? html`<span class="adm-tag">Personalizado</span>` : '');

// One notice that can use the AI: its own switch, a "Personalizado" tag when its instructions were changed and the
// instructions behind a button. The fragments of a notice are drawn inside it; their switch is not an AI one.
function aiUse(use, fragments) {
  return html`
    <div class="adm-ai-use ${use.parent ? 'adm-ai-fragment' : ''}">
      ${check(use.switch, use.label, use.help, customizedTag(use))}
      <details class="adm-details adm-ai-prompt">
        <summary class="adm-btn sm">Instrucciones</summary>
        <div>
          <textarea class="adm-input" name="ai.prompt.${use.id}" rows="9" spellcheck="false"></textarea>
          ${use.customized ? html`<button type="button" class="adm-btn sm" data-set-act="reset-prompt" data-use="${use.id}">Restaurar las originales</button>` : ''}
        </div>
      </details>
      ${fragments.map((fragment) => aiUse(fragment, []))}
    </div>`;
}

const telegramReady = (values) => values['telegram.token'].is_set && values['telegram.group_id'].is_set;

/** What the notices' AI still needs in the server's .env. */
const aiMissing = (values, aiModel) => [
  !aiModel.provider && 'AI_PROVIDER',
  !values['ai.api_key'].is_set && 'AI_API_KEY',
  !aiModel.model && 'AI_MODEL',
].filter(Boolean);

function view(values, jobs, pushDevices, mail, aiUses, aiModel, chat) {
  const state = (key) => (values[key].is_set ? 'Configurado' : 'Sin configurar');
  const aiKey = values['ai.api_key'];
  const vapid = values['push.vapid_private'];
  const cards = {
    notifications: html`
      <section class="adm-set-card">
        <h3>Notificaciones</h3>
        ${check('notifications.enabled', 'Notificaciones activadas', 'Apagado, no se envía nada al grupo ni mensajes privados a los usuarios (resumen semanal, avisos de timer olvidado…).')}
        ${check('notifications.admin_alerts', 'Avisos a administradores', 'Errores y ejecuciones lentas, por mensaje privado a los admins con ID de Telegram. Funciona aunque las notificaciones generales estén apagadas.')}
      </section>`,

    inbox: html`
      <section class="adm-set-card">
        <h3>Avisos en la app</h3>
        <div class="adm-sub">Cada usuario puede ver en la app (la campana de la barra superior) los avisos del grupo y los suyos, aunque tenga las notificaciones apagadas. No se guardan los del timer (inicio, fin y olvido) ni los enviados con las notificaciones desactivadas.</div>
        <label>Días que se guardan
          <input class="adm-input" type="number" name="inbox.retention_days" min="1" max="365" step="1" required />
        </label>
        <div class="adm-sub">Pasado ese tiempo se borran solos, cada madrugada.${jobs.inbox_purge ? ` Última limpieza: ${formatDateTime(jobs.inbox_purge.last_run_at)}.` : ''}</div>
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

    challenges: html`
      <section class="adm-set-card">
        <h3>Retos</h3>
        ${check('challenges.private_notices', 'Avisos privados de retos', 'Lo que afecta a cada jugador, por mensaje privado (Telegram o app, según elija cada uno en su perfil): que le han retado a un duelo, que le han rechazado uno, cómo se ha contestado una propuesta suya y cómo han terminado sus retos. Los retos personales y los duelos nunca se avisan al grupo.')}
        ${check('challenges.result_notice', 'Avisar al grupo de cómo ha terminado un reto de grupo', 'Un solo mensaje por reto, al día siguiente de su final: cuántos cumplieron su parte, si se llegó al total y quién ganó si era una competición.')}
        ${check('challenges.reminders', 'Permitir los recordatorios de retos', 'Un mensaje privado cuando a un reto le quedan 2 días, a quien no lo ha cumplido. Cada jugador lo tiene desactivado hasta que lo activa en su perfil; apagado aquí, no se envía a nadie.')}
        <div class="adm-set-row">
          <label>Hora de los resultados <input class="adm-input" type="time" name="challenges.results_time" required /></label>
          <label>Hora de los recordatorios <input class="adm-input" type="time" name="challenges.reminders_time" required /></label>
        </div>
        <div class="adm-sub">Necesitan las notificaciones activadas. Si el servidor está apagado a esa hora, se envían al volver siempre que no hayan pasado más de 3 horas. Resultados: ${lastRun(jobs.challenge_results)} Recordatorios: ${lastRun(jobs.challenge_reminders)}</div>
      </section>`,

    wishlist: html`
      <section class="adm-set-card">
        <h3>Juegos deseados que salen</h3>
        <label>Aviso al grupo
          <select class="adm-input" name="wishlist.group_notice">${WISHLIST_NOTICES.map(([value, label]) => html`<option value="${value}">${label}</option>`)}</select>
        </label>
        <div class="adm-sub">Solo uno a la vez. Necesita las notificaciones activadas. La víspera se envía cada día, y el semanal cada domingo con los juegos que salen en los 7 días siguientes.</div>
        <label>Hora <input class="adm-input" type="time" name="wishlist.time" required /></label>
        <div class="adm-sub">Mejor después de las 09:00, cuando se actualizan las fechas de salida. Si el servidor está apagado a esa hora, se envía al volver siempre que no hayan pasado más de 3 horas (la víspera) o 6 (el semanal). ${lastRun(values['wishlist.group_notice'] === 'weekly' ? jobs.wishlist_week : jobs.wishlist_eve)}</div>
      </section>`,

    monthly: html`
      <section class="adm-set-card">
        <h3>Resumen mensual</h3>
        ${check('monthly.enabled', 'Enviar el resumen del mes', 'Avisa de que el resumen del mes que acaba de terminar ya está disponible: un solo aviso, al grupo de Telegram y a las notificaciones de la app, con el enlace a la historia. Necesita las notificaciones activadas. Apagado hasta que lo actives: pruébalo antes con «Probar resumen».')}
        <div class="adm-set-row">
          <label>Día del mes
            <select class="adm-input" name="monthly.day">${[1, 2, 3, 4, 5].map((day) => html`<option value="${day}">${day}</option>`)}</select>
          </label>
          <label>Hora <input class="adm-input" type="time" name="monthly.time" required /></label>
        </div>
        <div class="adm-sub">Entre el 1 y el 5, los días en que la app también lo ofrece a quien no tiene las notificaciones. Si el servidor está apagado a esa hora, se envía al volver siempre que no hayan pasado más de 12 horas. ${lastRun(jobs.monthly_recap)}</div>
      </section>`,

    annual: html`
      <section class="adm-set-card">
        <h3>Resumen anual</h3>
        ${check('annual.enabled', 'Enviar el resumen de la temporada', 'Aparte del mensual: el mismo aviso de que el resumen de la temporada ya está disponible, al grupo de Telegram y a las notificaciones de la app. En diciembre cuenta lo jugado hasta ese día; en enero, la temporada completa. Necesita las notificaciones activadas.')}
        <div class="adm-set-row">
          <label>Mes
            <select class="adm-input" name="annual.month">${ANNUAL_MONTHS.map(([value, label]) => html`<option value="${value}">${label}</option>`)}</select>
          </label>
          <label>Día
            <select class="adm-input" name="annual.day">${Array.from({ length: 28 }, (_, i) => html`<option value="${i + 1}">${i + 1}</option>`)}</select>
          </label>
          <label>Hora <input class="adm-input" type="time" name="annual.time" required /></label>
        </div>
        <div class="adm-sub">En diciembre, entre el 20 y el 28; en enero, entre el 1 y el 5. ${lastRun(jobs.annual_recap)}</div>
      </section>`,

    access: html`
      <section class="adm-set-card">
        <h3>Acceso a los resúmenes</h3>
        ${check('recap.always_available', 'Resumen siempre disponible', 'Apagado, un resumen solo se puede abrir los primeros días tras terminar el mes (o la temporada, en enero); después, ni por un enlace directo. Encendido, la tarjeta del perfil está siempre y se puede elegir cualquier resumen ya terminado (tipo, año y mes). Los administradores ven lo mismo que un jugador, para poder probarlo.')}
        <label class="adm-check adm-set-check">
          <input type="checkbox" id="annualUnlock" name="annualUnlock" />
          <span><strong>Mostrar el resumen de la temporada en curso</strong><span class="adm-sub">Mientras esté apagado, nadie puede abrir ese resumen, ni por un enlace directo: así no se puede ir consultando día a día. Se enciende solo en cuanto el aviso llega al grupo (el envío automático o el manual); también lo puedes encender tú a mano. Los administradores ven lo mismo que un jugador, salvo en las herramientas del panel.</span></span>
        </label>
      </section>`,

    // Notificaciones → Canales: only what is about sending (whether it is set, and the test); the configuration is in Sistema → Servicios
    telegram: html`
      <section class="adm-set-card">
        <h3>Telegram</h3>
        ${telegramReady(values)
          ? html`<div class="adm-sub">Bot configurado: los avisos del grupo salen por Telegram.</div>`
          : html`<div class="adm-warn">Telegram no está configurado: faltan ${[['telegram.token', 'TELEGRAM_TOKEN'], ['telegram.group_id', 'TELEGRAM_GROUP_ID']].filter(([key]) => !values[key].is_set).map(([, name]) => name).join(' y ')} en el .env del servidor (ver Sistema → Servicios). La aplicación funciona, pero no envía nada por Telegram y el bot no arranca.</div>`}
        <div><button type="button" class="adm-btn" data-set-act="test" ${telegramReady(values) ? '' : html`disabled`}>Enviar mensaje de prueba al grupo</button></div>
      </section>`,

    // Notificaciones → IA: the switch and the test; the provider, key and model are in Sistema → Servicios
    ai: html`
      <section class="adm-set-card">
        <h3>Inteligencia artificial</h3>
        ${check('ai.enabled', 'Usar IA en los avisos', 'Apagada, los avisos salen con el texto original. Necesita una clave guardada para funcionar.')}
        ${aiMissing(values, aiModel).length ? html`<div class="adm-warn">Falta <code>${aiMissing(values, aiModel).join(', ')}</code> en el .env del servidor: la aplicación no tiene ningún proveedor ni modelo por defecto, así que la IA no escribe ningún aviso hasta que los definas (ver Sistema → Servicios) y reinicies la API.</div>` : html`<div class="adm-sub">Usa ${AI_PROVIDERS.find(([id]) => id === aiModel.provider)?.[1] ?? aiModel.provider} (${aiModel.model}).</div>`}
        <div><button type="button" class="adm-btn" data-set-act="test-ai" ${aiKey.is_set ? '' : html`disabled`}>Probar la IA</button></div>
      </section>`,

    // Sistema → Servicios: what comes from the server's .env, read only
    aiconfig: html`
      <section class="adm-set-card">
        <h3>Inteligencia artificial</h3>
        <label>Proveedor <input class="adm-input adm-ai-provider" type="text" value="${AI_PROVIDERS.find(([id]) => id === aiModel.provider)?.[1] ?? aiModel.provider ?? 'Sin configurar'}" disabled /></label>
        <label>Clave de la API <input class="adm-input" type="text" value="${state('ai.api_key')}" disabled /></label>
        <label>Modelo de los avisos <input class="adm-input adm-ai-model" type="text" value="${aiModel.model || 'Sin configurar'}" disabled /></label>
        <label>Modelo del chat <input class="adm-input adm-chat-model" type="text" value="${chat.model || 'Sin configurar'}" disabled /></label>
        ${aiMissing(values, aiModel).length ? html`<div class="adm-warn">Falta <code>${aiMissing(values, aiModel).join(', ')}</code> en el .env del servidor: la aplicación no tiene ningún proveedor ni modelo por defecto, así que la IA no escribe ningún aviso hasta que los definas (y reinicies la API).</div>` : ''}
        <div class="adm-sub">El proveedor (<code>AI_PROVIDER</code>), la clave (<code>AI_API_KEY</code>) y el modelo (<code>AI_MODEL</code>) están en el .env del servidor y los comparten los avisos y el chat: desde el panel solo se ven. El modelo debe ser uno del proveedor.</div>
        <div class="adm-sub">El chat usa <code>CHAT_AI_MODEL</code> si está en el .env${chat.own_model ? '' : html` (ahora no lo está: usa <code>AI_MODEL</code>)`}, para darle un modelo distinto del de los avisos.</div>
      </section>`,

    telegramconfig: html`
      <section class="adm-set-card">
        <h3>Telegram</h3>
        <label>Token del bot <input class="adm-input" type="text" value="${state('telegram.token')}" disabled /></label>
        <label>ID del canal o grupo <input class="adm-input" type="text" value="${state('telegram.group_id')}" disabled /></label>
        <label>ID del chat de administración <input class="adm-input" type="text" value="${state('telegram.admin_chat_id')}" disabled /></label>
        ${telegramReady(values) ? '' : html`<div class="adm-warn">Telegram no está configurado: faltan ${[['telegram.token', 'TELEGRAM_TOKEN'], ['telegram.group_id', 'TELEGRAM_GROUP_ID']].filter(([key]) => !values[key].is_set).map(([, name]) => name).join(' y ')} en el .env del servidor. La aplicación funciona, pero no envía nada por Telegram y el bot no arranca.</div>`}
        <div class="adm-sub">Se configuran en el .env del servidor: desde el panel solo se ve si están definidos. El mensaje de prueba está en Notificaciones → Canales.</div>
      </section>`,

    chat: html`
      <section class="adm-set-card adm-chat-card">
        <h3>Chat</h3>
        <div class="adm-sub">Un botón flotante, abajo a la derecha de cada pantalla, abre un asistente que responde solo sobre videojuegos y los datos del grupo. Usa el proveedor y la clave de la IA de los avisos y su propio modelo si lo hay (ver Sistema → Servicios). Quien ya tenga la página abierta lo ve desaparecer al preguntar o al recargar.</div>
        ${check('chat.enabled', 'Chat activado', 'Apagado, el botón desaparece para todos y el chat deja de responder.')}
        <div class="adm-sub">Preguntas que se pueden hacer al chat; 0 es sin límite. Cada pregunta gasta varias llamadas a la IA y el cupo de la IA es del proyecto entero, no de cada jugador: por eso hay un límite por jugador y otro para todo el grupo. «Día» son las últimas 24 horas, no desde medianoche. Se cuentan en memoria: reiniciar la API los pone a cero. Quien se pasa ve cuál ha superado y cuánto esperar.</div>
        <div class="adm-set-row adm-chat-limits">
          ${CHAT_LIMITS.map(([name, label]) => html`<label>${label} <input class="adm-input" type="number" name="${name}" min="0" max="100000" step="1" required /></label>`)}
        </div>
        ${chatMissing(values, chat).length ? html`<div class="adm-warn">Falta <code>${chatMissing(values, chat).join(', ')}</code> en el .env del servidor: el chat usa el proveedor y la clave de la IA de los avisos, y no tiene ningún modelo por defecto, así que no estará disponible hasta que los definas (y reinicies la API).</div>` : ''}
        <details class="adm-details adm-ai-prompt">
          <summary class="adm-btn sm">Instrucciones ${chat.customized ? html`<span class="adm-tag">Personalizado</span>` : ''}</summary>
          <div>
            <textarea class="adm-input" name="chat.prompt" rows="9" spellcheck="false"></textarea>
            ${chat.customized ? html`<button type="button" class="adm-btn sm" data-set-act="reset-prompt" data-use="chat">Restaurar las originales</button>` : ''}
          </div>
        </details>
        <div class="adm-sub adm-chat-state">${chatState(values, chat)}</div>
        <div><button type="button" class="adm-btn" data-set-act="test-chat" ${chatMissing(values, chat).length ? html`disabled` : ''}>Probar el chat</button></div>
      </section>`,

    aiuses: html`
      <section class="adm-set-card">
        <h3>Avisos que usan la IA</h3>
        <div class="adm-sub">Activa o apaga la IA aviso a aviso. Sus instrucciones se pueden cambiar; mientras no lo hagas, siguen las de la aplicación.</div>
        <div class="adm-sub adm-ai-off" hidden>La IA general está apagada: ningún aviso la usa, aunque su interruptor esté activado.</div>
        <div class="adm-ai-uses">
          ${aiUses.filter((use) => !use.parent).map((use) => aiUse(use, aiUses.filter((fragment) => fragment.parent === use.id)))}
        </div>
      </section>`,

    push: html`
      <section class="adm-set-card">
        <h3>Avisos en la app (push)</h3>
        ${check('push.enabled', 'Enviar avisos a la app instalada', 'Función activa para todos por defecto; nadie recibe nada hasta que cada usuario lo active en su perfil (Ajustes → Notificaciones) y elija en qué dispositivos. Los avisos del grupo llegan a quien los marque y los privados (timer olvidado…) solo a su usuario. Necesita las notificaciones activadas y HTTPS.')}
        <div class="adm-sub">${pushDevices.devices} dispositivo${pushDevices.devices === 1 ? '' : 's'} suscrito${pushDevices.devices === 1 ? '' : 's'} (${pushDevices.users} usuario${pushDevices.users === 1 ? '' : 's'}).</div>
        <div class="adm-sub">Para redactar y enviar avisos (o probarlos en tus dispositivos) usa la pestaña <strong>Redactar aviso</strong>.</div>
      </section>`,

    pushconfig: html`
      <section class="adm-set-card">
        <h3>Avisos en la app (push)</h3>
        <label>Contacto para los servicios push
          <input class="adm-input" type="text" name="push.contact" placeholder="mailto:tu@correo.com (vacío: usa el remitente del correo o la dirección pública)" />
        </label>
        <div class="adm-sub">${vapid.is_set ? 'Las claves del servidor se crearon solas al arrancar; son las mismas para todos los usuarios.' : 'Sin claves (se crean al arrancar la API).'}</div>
        <div><button type="button" class="adm-btn" data-set-act="push-keys">Regenerar claves…</button></div>
      </section>`,

    backup: html`
      <section class="adm-set-card">
        <h3>Copia de seguridad</h3>
        <div class="adm-sub">Descarga toda la base de datos en un archivo .sql.gz (un .sql comprimido): usuarios, sesiones, biblioteca, logros, ajustes y fotos. Se restaura en una base vacía con el cliente de MariaDB (mira docs/desarrollo/deployment.md). Contiene las contraseñas cifradas y los ajustes protegidos, así que guárdala como lo que es: fuera del repositorio y sin compartirla.</div>
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
  // not a plain bool setting: unlocked for THIS year, so a stale unlock from a season gone by reads as off
  if (form.elements.annualUnlock) form.elements.annualUnlock.checked = values['annual.unlocked_year'] === new Date().getFullYear();
}

/** Only the days the chosen month allows can be picked; a day that does not fit is moved to the first one that does. */
export function syncAnnualDay(form) {
  const month = form.elements['annual.month'];
  const day = form.elements['annual.day'];
  if (!month || !day) return;
  const [from, to] = ANNUAL_DAYS[Number(month.value)];
  for (const option of day.options) {
    option.hidden = option.disabled = Number(option.value) < from || Number(option.value) > to;
  }
  if (Number(day.value) < from || Number(day.value) > to) day.value = String(from);
}

/** The notices are dimmed, and the page says why, while the general AI switch is off. */
export function syncAiOff(form) {
  const general = form.elements['ai.enabled'];
  const list = form.querySelector('.adm-ai-uses');
  if (!general || !list) return;
  list.classList.toggle('off', !general.checked);
  form.querySelector('.adm-ai-off').hidden = general.checked;
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
    const now = field.type === 'checkbox' ? field.checked : (field.type === 'select-one' || field.type === 'number') && isNumber ? Number(field.value) : field.value.trim();
    if (key.startsWith('ai.prompt.') || key === 'chat.prompt') {
      // the original text (or nothing) is not an override: it goes back to following the application's prompt
      const use = key === 'chat.prompt' ? chatInfo : aiUses.find((u) => `ai.prompt.${u.id}` === key);
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
  // not among `loaded`'s own fields: turning it on or off means unlocking this year's season or locking it again
  if (form.elements.annualUnlock) {
    const year = new Date().getFullYear();
    const wasUnlocked = loaded['annual.unlocked_year'] === year;
    if (form.elements.annualUnlock.checked !== wasUnlocked) changes['annual.unlocked_year'] = form.elements.annualUnlock.checked ? year : 0;
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

async function testChat() {
  toast('Probando el chat…');
  try {
    const result = await api('/manage/settings/test-chat', { method: 'POST' });
    toast(`${result.provider} (${result.model}) responde: ${result.reply}`);
  } catch (err) {
    toast(err.message, 'err');
  }
}

// Puts the original instructions back in the box; they take effect when the changes are saved.
function resetPrompt(form, id) {
  const [name, use] = id === 'chat' ? ['chat.prompt', chatInfo] : [`ai.prompt.${id}`, aiUses.find((u) => u.id === id)];
  form.elements[name].value = use.default_prompt.trim();
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
    const { values, jobs, push_devices: pushDevices, mail, ai_uses: uses, ai_model: aiModel, chat } = await api('/manage/settings');
    aiUses = uses;
    chatInfo = chat;
    loaded = Object.fromEntries(Object.entries(values).filter(([key]) => !SECRETS.includes(key) && !LOCKED.includes(key) && !key.startsWith('push.vapid')));
    for (const key of SECRETS) loaded[key] = null;
    mount(panel, view(values, jobs, pushDevices, mail, aiUses, aiModel, chat));
    const form = panel.querySelector('#admSettings');
    fill(form, values);
    syncAnnualDay(form);
    syncAiOff(form);
    form.addEventListener('change', (e) => {
      if (e.target.name === 'annual.month') syncAnnualDay(form);
      if (e.target.name === 'ai.enabled') syncAiOff(form);
    });
    form.addEventListener('submit', (e) => { e.preventDefault(); save(form); });
    form.addEventListener('click', (e) => {
      const act = e.target.closest('[data-set-act]')?.dataset.setAct;
      if (act === 'test') sendTest();
      else if (act === 'backup') downloadBackup(e.target.closest('[data-set-act]'));
      else if (act === 'test-email') sendTestEmail(mail);
      else if (act === 'test-ai') testAi(form);
      else if (act === 'test-chat') testChat();
      else if (act === 'reset-prompt') resetPrompt(form, e.target.closest('[data-use]').dataset.use);
      else if (act === 'push-keys') generateKeys(values['push.vapid_private'].is_set);
    });
  } catch (err) {
    mount(panel, errorState(err.message));
  }
}
