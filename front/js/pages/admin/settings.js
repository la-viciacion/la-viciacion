// Settings pages of the admin panel: general switches, weekly summary schedule, the Telegram bot
// (token, group, admin chat), the AI that writes the notices (the provider among those with a key in the .env, and its model, picked
// from the provider's live list), the chat (its own switch and instructions; it shares the AI's provider and key, and its model may
// be its own), push and mail.
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
import { cardTitle } from '../../ui/info-tip.js';
import { searchable } from '../../ui/combobox.js';
import { renderBudgets } from './ai-budgets.js';
import { renderWallet } from './ai-wallet.js';

const SECRETS = []; // never loaded back: sent only when something is typed (the keys of outside services are not: they are in the server's .env)
const AI_IDS = ['openai', 'google', 'anthropic', 'openrouter']; // api/src/utils/settings.py AI_PROVIDERS: each has its own keys in the .env
const LOCKED = ['telegram.token', 'telegram.group_id', 'telegram.admin_chat_id', 'ai.openai_admin_key', 'ai.anthropic_admin_key', ...AI_IDS.flatMap((p) => [`ai.${p}.api_key`, `ai.${p}.model`, `ai.${p}.chat_model`])]; // shown only as set or not, never editable
// What the AI does and what each one follows when nothing is picked for it: the notices, the chat (follows the notices) and the guide
// (follows the chat). `prefix` is the start of its settings: `<prefix>.provider` and `<prefix>.model.<provider>` (api/src/utils/ai_providers.py)
const AI_USES = [
  { use: 'notices', prefix: 'ai', label: 'avisos', of: 'de los avisos', follows: null },
  { use: 'chat', prefix: 'chat', label: 'chat', of: 'del chat', follows: 'notices' },
  { use: 'guide', prefix: 'guide', label: 'guía', of: 'de la guía', follows: 'chat' },
];
const isPick = (key) => /^(ai|chat|guide)\.model\./.test(key) || key === 'chat.provider' || key === 'guide.provider'; // an empty choice goes back to following
// the questions the chat answers, per player and for the whole group (api/src/utils/settings.py chat.limit_*)
const CHAT_LIMITS = [
  ['chat.limit_user_minute', 'Por jugador, por minuto'],
  ['chat.limit_user_hour', 'Por jugador, por hora'],
  ['chat.limit_user_day', 'Por jugador, por día'],
  ['chat.limit_group_minute', 'Grupo, por minuto'],
  ['chat.limit_group_day', 'Grupo, por día'],
];
// the questions the game guide answers (api/src/utils/settings.py guide.limit_*): fewer, a search costs more than a chat question
const GUIDE_LIMITS = [
  ['guide.limit_user_hour', 'Por jugador, por hora'],
  ['guide.limit_user_day', 'Por jugador, por día'],
  ['guide.limit_group_day', 'Grupo, por día'],
];
// whose key pays for a feature (api/src/utils/ai_source.py): what each player may have saved in Ajustes → Mi IA, and the group's
const KEY_SOURCES = [
  ['user_only', 'Solo la clave del propio jugador'],
  ['group_then_user', 'Primero la del grupo; al agotarse el saldo del jugador o su tope mensual, la del jugador'],
  ['group_only', 'Siempre la del grupo (ignora las claves de los jugadores)'],
];
const keySource = (name, label) => html`
  <label>${label}
    <select class="adm-input" name="${name}">${KEY_SOURCES.map(([id, label]) => html`<option value="${id}">${label}</option>`)}</select>
  </label>`;
const READ_ONLY = ['mail', 'backup']; // cards with nothing to save
const AI_PROVIDERS = [['google', 'Google (Gemini)'], ['openai', 'OpenAI'], ['anthropic', 'Anthropic (Claude)'], ['openrouter', 'OpenRouter']];
const providerName = (id) => AI_PROVIDERS.find(([known]) => known === id)?.[1] ?? id;
const keyVariable = (id) => `${id.toUpperCase()}_AI_API_KEY`;

const ANNUAL_MONTHS = [[12, 'Diciembre'], [1, 'Enero']];
// the days the annual recap can go out on, by month (api/src/utils/settings.py ANNUAL_DAYS)
export const ANNUAL_DAYS = { 12: [20, 28], 1: [1, 5] };

// how the group hears about the wished games that come out (api/src/utils/settings.py WISHLIST_GROUP_NOTICES)
const WISHLIST_NOTICES = [['eve', 'La víspera de cada estreno'], ['day', 'El mismo día del estreno'], ['weekly', 'Una vez por semana'], ['off', 'Ninguno']];

const WISHLIST_JOBS = { eve: 'wishlist_eve', day: 'wishlist_day', weekly: 'wishlist_week' }; // the job each mode runs

const WEEKDAYS = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo'];

let panel;
let sections = []; // cards of the page on screen
let loaded = {}; // values as the server has them
let aiUses = []; // where the AI writes: label, original prompt and whether it was changed
let guideInfo = {}; // the guide: the model it uses, original instructions and whether they were changed
let chatInfo = {}; // the chat: the provider and model it uses (and whether the model is its own), original instructions and whether they were changed
let aiProviders = { providers: [], uses: {} }; // what the .env has (providers with a key, default models) and what each use runs on now
let modelLists = new Map(); // provider -> the models it offers, asked live once per page load

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

// What the chat still needs: a provider with a key in the server's .env, and a model (picked in the panel, or the .env's)
function chatMissing(values, chat) {
  return [
    !chat.provider && AI_IDS.map(keyVariable).join(' o '),
    chat.provider && !chat.model && `un modelo (${chat.provider.toUpperCase()}_AI_MODEL en el .env, o elígelo aquí)`,
  ].filter(Boolean);
}

/** Whether the players get the chat button now, and if not why (what is saved, not what is typed). */
function chatState(values, chat) {
  const reasons = [
    !values['chat.enabled'] && 'el chat está apagado',
    chatMissing(values, chat).length && `falta ${chatMissing(values, chat).join(', ')}`,
  ].filter(Boolean);
  return reasons.length ? `No disponible: ${reasons.join('; ')}.` : 'Disponible: los jugadores ven el botón del chat.';
}

/** Whether the players get the guide on the game page now, and if not why (what is saved, not what is typed). */
function guideState(values, guide) {
  const reasons = [
    !values['guide.enabled'] && 'la guía está apagada',
    chatMissing(values, guide).length && `falta ${chatMissing(values, guide).join(', ')}`,
  ].filter(Boolean);
  return reasons.length ? `No disponible: ${reasons.join('; ')}.` : 'Disponible: los jugadores ven la guía en la página de cada juego.';
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

/** What the notices' AI still needs. */
const aiMissing = (aiModel) => [
  !aiModel.provider && AI_IDS.map(keyVariable).join(' o '),
  aiModel.provider && !aiModel.model && `un modelo (${aiModel.provider.toUpperCase()}_AI_MODEL en el .env, o elígelo aquí)`,
].filter(Boolean);

/** A model that cannot work with its provider, and why (the API says; for example an OpenRouter name without its vendor). */
const problemNote = (use) => (use?.problem ? html`<div class="adm-warn">${use.problem}. Cámbialo en el .env del servidor (y reinicia la API) o elige otro aquí.</div>` : '');

const readyProviders = () => aiProviders.providers.filter((p) => p.has_key);

/** The provider and the model of one use of the AI (notices, chat or guide): the provider among those with a key in the .env (the
 * chat and the guide may follow the one before), and the model: the .env's by default, or one from the provider's live list.
 * Both selectors are redrawn by `syncModels` when a provider changes, so the list is always the one of the provider on screen. */
function usePicker({ use, prefix, of, follows }) {
  const ready = readyProviders();
  if (!ready.length) return '';
  const info = aiProviders.uses[use] ?? {};
  const followsLabel = follows ? AI_USES.find((u) => u.use === follows).label : null;
  return html`
    <label>Proveedor ${of}
      <select class="adm-input adm-${use}-provider" name="${prefix}.provider" data-use="${use}" ${ready.length === 1 && !follows ? html`disabled` : ''}>
        ${follows ? html`<option value="">Igual que ${followsLabel === 'chat' ? 'el chat' : 'los avisos'}${info.picked ? '' : ` (${providerName(info.provider)})`}</option>` : ''}
        ${ready.map((p) => html`<option value="${p.id}">${providerName(p.id)}</option>`)}
      </select>
    </label>
    <label>Modelo ${of}
      <select class="adm-input adm-${use}-model" data-model-for="${use}" name="${prefix}.model.${info.provider ?? ''}"></select>
    </label>
    <div class="adm-sub adm-model-note" data-note-for="${use}"></div>`;
}

/** What a provider uses by default for a use: the .env's model (the chat's own if it has one). */
const defaultModelOf = (providerId, use) => {
  const info = aiProviders.providers.find((p) => p.id === providerId);
  return use === 'notices' ? info?.default_model : info?.default_chat_model;
};

function view(values, jobs, pushDevices, mail, aiUses, aiModel, chat, guide = {}) {
  const state = (key) => (values[key].is_set ? 'Configurado' : 'Sin configurar');
  const noKey = !readyProviders().length;
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
        ${cardTitle('Avisos en la app', html`Cada usuario puede ver en la app (la campana de la barra superior) los avisos del grupo y los suyos, aunque tenga las notificaciones apagadas. No se guardan los del timer (inicio, fin y olvido) ni los enviados con las notificaciones desactivadas.`)}
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
        ${check('challenges.start_notice', 'Avisar al grupo de que empieza un reto de grupo', 'Un mensaje el día que empieza un reto que se lanzó antes (con las personas apuntadas, si es voluntario). Un reto lanzado el mismo día en que empieza ya lo dijo al lanzarse. Sale a la hora de los resultados.')}
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
        <div class="adm-sub">Solo uno a la vez. Necesita las notificaciones activadas. La víspera y el mismo día se envían cada día, y el semanal cada domingo con los juegos que salen en los 7 días siguientes.</div>
        <label>Hora <input class="adm-input" type="time" name="wishlist.time" required /></label>
        <div class="adm-sub">Mejor después de las 09:00, cuando se actualizan las fechas de salida. Si el servidor está apagado a esa hora, se envía al volver siempre que no hayan pasado más de 3 horas (la víspera y el mismo día) o 6 (el semanal). ${lastRun(jobs[WISHLIST_JOBS[values['wishlist.group_notice']]])}</div>
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

    // Notificaciones → Canales: the bot as the server's .env has it (read only), and the test
    telegram: html`
      <section class="adm-set-card">
        <h3>Telegram</h3>
        <label>Token del bot <input class="adm-input" type="text" value="${state('telegram.token')}" disabled /></label>
        <label>ID del canal o grupo <input class="adm-input" type="text" value="${state('telegram.group_id')}" disabled /></label>
        <label>ID del chat de administración <input class="adm-input" type="text" value="${state('telegram.admin_chat_id')}" disabled /></label>
        ${telegramReady(values)
          ? html`<div class="adm-sub">Bot configurado: los avisos del grupo salen por Telegram.</div>`
          : html`<div class="adm-warn">Telegram no está configurado: faltan ${[['telegram.token', 'TELEGRAM_TOKEN'], ['telegram.group_id', 'TELEGRAM_GROUP_ID']].filter(([key]) => !values[key].is_set).map(([, name]) => name).join(' y ')} en el .env del servidor. La aplicación funciona, pero no envía nada por Telegram y el bot no arranca.</div>`}
        <div class="adm-sub">Se configuran en el .env del servidor: desde el panel solo se ve si están definidos.</div>
        <div><button type="button" class="adm-btn" data-set-act="test" ${telegramReady(values) ? '' : html`disabled`}>Enviar mensaje de prueba al grupo</button></div>
      </section>`,

    // IA → Avisos con IA: the switch and the test, and the provider, key and model as the server's .env has them (read only)
    ai: html`
      <section class="adm-set-card">
        <h3>Inteligencia artificial</h3>
        ${check('ai.enabled', 'Usar IA en los avisos', 'Apagada, los avisos salen con el texto original. Necesita una clave guardada para funcionar.')}
        ${noKey ? html`<div class="adm-warn">No hay ningún proveedor de IA: define <code>OPENAI_AI_API_KEY</code>, <code>GOOGLE_AI_API_KEY</code>, <code>ANTHROPIC_AI_API_KEY</code> u <code>OPENROUTER_AI_API_KEY</code> en el .env del servidor (y reinicia la API).</div>` : usePicker(AI_USES[0])}
        ${readyProviders().length === 1 ? html`<div class="adm-sub">Solo hay clave de ${providerName(readyProviders()[0].id)} en el .env: es el que se usa. Para poder elegir, define también la clave de otro proveedor.</div>` : ''}
        <label>Clave de administración de OpenAI <input class="adm-input" type="text" value="${state('ai.openai_admin_key')}" disabled /></label>
        <label>Clave de administración de Anthropic <input class="adm-input" type="text" value="${state('ai.anthropic_admin_key')}" disabled /></label>
        ${aiMissing(aiModel).length ? html`<div class="adm-warn">Falta ${aiMissing(aiModel).join(', ')}: la aplicación no tiene ningún modelo por defecto, así que la IA no escribe ningún aviso hasta que lo definas.</div>` : html`<div class="adm-sub">Usa ${providerName(aiModel.provider)} (${aiModel.model}).</div>`}
        ${problemNote(aiModel)}
        <div class="adm-sub">Las claves y los modelos por defecto de cada proveedor están en el .env del servidor (<code>OPENAI_AI_API_KEY</code>, <code>OPENAI_AI_MODEL</code>, <code>GOOGLE_AI_API_KEY</code>, <code>GOOGLE_AI_MODEL</code>, <code>ANTHROPIC_AI_API_KEY</code>, <code>ANTHROPIC_AI_MODEL</code>, <code>OPENROUTER_AI_API_KEY</code>, <code>OPENROUTER_AI_MODEL</code>): desde el panel solo se ven. La lista de modelos la da el propio proveedor en este momento, así que se puede cambiar de modelo sin redesplegar. Esa elección es solo para el proveedor en uso.</div>
        <div class="adm-sub">Las claves de administración (<code>OPENAI_ADMIN_KEY</code> y <code>ANTHROPIC_ADMIN_KEY</code>, opcionales; la de Anthropic solo la tiene una organización de su consola) solo sirven para leer el gasto en IA → Uso y coste; no escriben nada.</div>
        <div><button type="button" class="adm-btn" data-set-act="test-ai" ${noKey ? html`disabled` : ''}>Probar la IA</button></div>
      </section>`,

    chat: html`
      <section class="adm-set-card adm-chat-card">
        ${cardTitle('Chat', html`Un botón flotante, abajo a la derecha de cada pantalla, abre un asistente que responde solo sobre videojuegos y los datos del grupo. Usa el proveedor de los avisos, salvo que elijas otro aquí (con la clave de ese proveedor), y su propio modelo si se elige. Quien ya tenga la página abierta lo ve desaparecer al preguntar o al recargar.`)}
        ${usePicker(AI_USES[1])}
        <div class="adm-sub">Sin elegir otro modelo, usa <code>&lt;PROVEEDOR&gt;_CHAT_AI_MODEL</code> si está en el .env y, si no, el de los avisos. Sirve para darle un modelo más fuerte que el de los avisos.</div>
        ${check('chat.enabled', 'Chat activado', 'Apagado, el botón desaparece para todos y el chat deja de responder.')}
        ${chatMissing(values, chat).length ? html`<div class="adm-warn">Falta ${chatMissing(values, chat).join(', ')}: el chat usa el proveedor de los avisos (o el que elijas aquí) y no tiene ningún modelo por defecto, así que no estará disponible hasta que lo definas.</div>` : ''}
        ${problemNote(chat)}
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

    aicost: html`
      <section class="adm-set-card adm-aicost-card">
        ${cardTitle('Coste de la IA', html`Cada pregunta al chat o a la guía deja un registro de lo que usó (tokens, búsquedas) y lo que costó, sin guardar el texto. Lo ves arriba, en esta misma pestaña. El coste es una estimación con los precios de cada modelo, que no están en el código: se descargan de una lista pública (genai-prices) cada cierto tiempo y, si no se puede, se usan los de la versión instalada.`)}
        <div class="adm-set-row">
          <label>Actualizar los precios cada (horas, 0 = nunca) <input class="adm-input" type="number" name="ai.price_refresh_hours" min="0" max="720" step="1" required /></label>
          <label>Conservar el registro (días, 0 = siempre) <input class="adm-input" type="number" name="ai.usage_retention_days" min="0" max="3650" step="1" required /></label>
        </div>
        ${check('ai.free_plan.google', 'La clave de Google es de un plan gratuito', 'Sus llamadas se siguen estimando (sirve para saber lo que costarían), pero su coste real cuenta 0 US$ en el gasto, el presupuesto y el panel del servidor. Se apunta en cada llamada cuando se hace: cambiarlo no toca las anteriores.')}
        <div class="adm-sub">La lista incluye también lo que cobra cada proveedor por las búsquedas web de la guía, modelo a modelo. Un cambio en la frecuencia de actualización se aplica al arrancar la API.</div>
      </section>`,

    ailimitkeys: html`
      <section class="adm-set-card adm-ailimitkeys-card">
        ${cardTitle('Quién asume el coste', html`<p>Cada jugador puede guardar su propia clave de OpenAI en su perfil (Ajustes → Mi IA). Con «Primero la del grupo», todos usan la del grupo (el .env) mientras quede saldo en el monedero y el jugador no haya llegado a su tope mensual; cuando se agota alguno de los dos, quien tiene su propia clave sigue con ella (y solo le queda un límite por minuto) y quien no la tiene lo ve explicado. «Siempre la del grupo» ignora las claves de los jugadores, y «Solo la clave del propio jugador» no gasta nada del grupo.</p><p>Una pregunta de la guía hace búsquedas web y cuesta bastante más que una del chat; con «Solo la clave del propio jugador», quien no tiene clave ve cómo añadirla (Ajustes → Mi IA). Los límites de abajo son para lo que paga el grupo.</p>`)}
        <div class="adm-set-row">
          ${keySource('chat.key_source', 'Chat')}
          ${keySource('guide.key_source', 'Guía de juego')}
        </div>
      </section>`,

    ailimitq: html`
      <section class="adm-set-card adm-ailimitq-card">
        ${cardTitle('Límites de preguntas', html`<p>Preguntas que se pueden hacer al chat; 0 es sin límite. Cada pregunta gasta varias llamadas a la IA y el cupo de la IA es del proyecto entero, no de cada jugador: por eso hay un límite por jugador y otro para todo el grupo. «Día» son las últimas 24 horas, no desde medianoche. Se cuentan en memoria: reiniciar la API los pone a cero. Quien se pasa ve cuál ha superado y cuánto esperar. </p><p>Preguntas que se pueden hacer a la guía; 0 es sin límite. Cada una hace una búsqueda web y cuesta bastante más que una del chat, por eso sus límites son propios y más bajos. «Día» son las últimas 24 horas. Se cuentan en memoria: reiniciar la API los pone a cero.</p>`)}
        <strong class="adm-limit-group">Chat</strong>
        <div class="adm-set-row adm-chat-limits">
          ${CHAT_LIMITS.map(([name, label]) => html`<label>${label} <input class="adm-input" type="number" name="${name}" min="0" max="100000" step="1" required /></label>`)}
        </div>
        <strong class="adm-limit-group">Guía de juego</strong>
        <div class="adm-set-row adm-guide-limits">
          ${GUIDE_LIMITS.map(([name, label]) => html`<label>${label} <input class="adm-input" type="number" name="${name}" min="0" max="100000" step="1" required /></label>`)}
        </div>
      </section>`,

    aibudget: html`
      <section class="adm-set-card adm-aibudget-card">
        ${cardTitle('Tope mensual por jugador (dinero)', html`Cuánto puede gastar cada jugador de la clave del grupo al mes, en dólares enteros (vacío = sin límite, 0 = nada de la clave del grupo). Sirve para evitar abusos y que nadie se funda la cuota en pocos días; el grupo en conjunto se limita por el saldo del monedero. Un jugador puede tener otro tope, en la tabla de debajo. Solo cuenta lo que cubre la clave del grupo: lo que cada jugador gasta con su propia clave no suma ni se limita. Cuando un jugador llega a su tope, deja de poder usar la clave del grupo hasta el día 1, y sigue con la suya si tiene una y el modo de «Quién asume el coste» es «Primero la del grupo». El coste es una estimación y una pregunta puede pasarse del tope, porque su precio se conoce al acabar.`)}
        <div class="adm-sub">Es un límite de dinero, distinto de los límites de preguntas de arriba (que cuentan mensajes por minuto, hora y día). Debajo ves lo gastado este mes y puedes dar un tope distinto a cada jugador.</div>
        <div class="adm-set-row">
          <label>Cada jugador, por defecto (US$ al mes) <input class="adm-input" type="number" name="ai.user_budget_month" min="0" max="10000" step="1" placeholder="sin límite" /></label>
        </div>
      </section>`,

    aibudgets: html`<div id="aicBudgets"></div>`,

    aiwallet: html`<div id="aicWallet"></div>`,

    guide: html`
      <section class="adm-set-card adm-guide-card">
        ${cardTitle('Guía de juego', html`Una tarjeta en la página de cada juego donde el jugador pide ayuda con ese juego (desatascarse, consejos) y elige cuántos destripes admite. A diferencia del chat, responde buscando en la web. Usa el proveedor y el modelo del chat salvo que elijas otros aquí, y el modelo tiene que admitir la búsqueda web (con OpenAI, un modelo de la API Responses; con Google, la búsqueda de Gemini). Lo comprueba el botón de abajo.`)}
        ${usePicker(AI_USES[2])}
        <div class="adm-sub">La guía busca en la web: el modelo tiene que admitirlo. Sin elegir otro, usa el del chat.</div>
        ${check('guide.enabled', 'Guía activada', 'Apagada, la tarjeta desaparece de la página de los juegos y la guía deja de responder.')}
        <details class="adm-details adm-ai-prompt">
          <summary class="adm-btn sm">Instrucciones ${customizedTag(guide)}</summary>
          <div>
            <textarea class="adm-input" name="guide.prompt" rows="9" spellcheck="false"></textarea>
            ${guide.customized ? html`<button type="button" class="adm-btn sm" data-set-act="reset-prompt" data-use="guide">Restaurar las originales</button>` : ''}
          </div>
        </details>
        <div class="adm-sub adm-guide-state">${guideState(values, guide)}</div>
        ${problemNote(guide)}
        <div><button type="button" class="adm-btn" data-set-act="test-guide" ${chatMissing(values, guide).length ? html`disabled` : ''}>Probar la guía</button></div>
      </section>`,

    aiuses: html`
      <section class="adm-set-card">
        ${cardTitle('Avisos que usan la IA', html`Activa o apaga la IA aviso a aviso. Sus instrucciones se pueden cambiar; mientras no lo hagas, siguen las de la aplicación.`)}
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
        <label>Contacto para los servicios push
          <input class="adm-input" type="text" name="push.contact" placeholder="mailto:tu@correo.com (vacío: usa el remitente del correo o la dirección pública)" />
        </label>
        <div class="adm-sub">${vapid.is_set ? 'Las claves del servidor se crearon solas al arrancar; son las mismas para todos los usuarios.' : 'Sin claves (se crean al arrancar la API).'}</div>
        <div><button type="button" class="adm-btn" data-set-act="push-keys">Regenerar claves…</button></div>
        <div class="adm-sub">Para redactar y enviar avisos (o probarlos en tus dispositivos) usa la pestaña <strong>Comunidad → Redactar aviso</strong>.</div>
      </section>`,

    backup: html`
      <section class="adm-set-card">
        ${cardTitle('Copia de seguridad', html`Descarga toda la base de datos en un archivo .sql.gz (un .sql comprimido): usuarios, sesiones, biblioteca, logros, ajustes y fotos. Se restaura en una base vacía con el cliente de MariaDB (mira docs/desarrollo/deployment.md). Contiene las contraseñas cifradas y los ajustes protegidos, así que guárdala como lo que es: fuera del repositorio y sin compartirla.`)}
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

// Numbers that may be left empty: no value is no limit (the API takes null as "back to the default", which is that)
const OPTIONAL_NUMBERS = ['ai.user_budget_month'];

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
    const now = field.type === 'checkbox' ? field.checked : OPTIONAL_NUMBERS.includes(key) ? (field.value.trim() === '' ? null : Number(field.value)) : (field.type === 'select-one' || field.type === 'number') && isNumber ? Number(field.value) : field.value.trim();
    if (key.startsWith('ai.prompt.') || key === 'chat.prompt' || key === 'guide.prompt') {
      // the original text (or nothing) is not an override: it goes back to following the application's prompt
      const use = key === 'chat.prompt' ? chatInfo : key === 'guide.prompt' ? guideInfo : aiUses.find((u) => `ai.prompt.${u.id}` === key);
      if (now === '' || now === use.default_prompt.trim()) {
        if (use.customized) changes[key] = null;
      } else if (now !== before) {
        changes[key] = now;
      }
      continue;
    }
    if (now === '' && before == null) continue; // an optional text left empty
    if (isPick(key) && now === '') {
      changes[key] = null; // "igual que…" / "por defecto": it follows again
      continue;
    }
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
  if (Object.keys(collect(form)).some((key) => (key.startsWith('ai.') && !key.startsWith('ai.prompt.') && !key.startsWith('ai.use.')) || key.startsWith('chat.model.'))) {
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

async function testGuide() {
  toast('Probando la guía (hace una búsqueda web)…');
  try {
    const result = await api('/manage/settings/test-guide', { method: 'POST' });
    toast(`${result.provider} (${result.model}) responde: ${result.reply}`);
  } catch (err) {
    toast(err.message, 'err');
  }
}

// Puts the original instructions back in the box; they take effect when the changes are saved.
function resetPrompt(form, id) {
  const [name, use] = id === 'chat' ? ['chat.prompt', chatInfo]
    : id === 'guide' ? ['guide.prompt', guideInfo]
      : [`ai.prompt.${id}`, aiUses.find((u) => u.id === id)];
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

const option = (value, text = value) => Object.assign(document.createElement('option'), { value, textContent: text });

/** The provider each use runs on, as the form shows it now (an unpicked chat follows the notices, an unpicked guide the chat). */
function effectiveProviders(form) {
  const found = {};
  for (const { use, prefix, follows } of AI_USES) {
    const select = form.elements[`${prefix}.provider`];
    // a card that is not on this page has no selector: its use runs on what the server says
    found[use] = (select ? select.value || (follows ? found[follows] : readyProviders()[0]?.id) : aiProviders.uses[use]?.provider) || null;
  }
  return found;
}

/** What a provider offers now: asked to the provider itself, once per page load. */
function modelsOf(providerId) {
  if (!modelLists.has(providerId)) {
    modelLists.set(providerId, api(`/manage/settings/ai-models?provider=${encodeURIComponent(providerId)}`).then((r) => ({ models: r.models }), (err) => ({ error: err.message })));
  }
  return modelLists.get(providerId);
}

/** Redraws the model selectors for the providers on screen: each one is named after its provider (so it saves under the right
 * setting) and lists that provider's models, the .env's one first. Called when the page opens and whenever a provider changes. */
async function syncModels(form) {
  const providers = effectiveProviders(form);
  await Promise.all(AI_USES.map(async ({ use, prefix, label }) => {
    const select = form.querySelector(`select[data-model-for="${use}"]`);
    const note = form.querySelector(`[data-note-for="${use}"]`);
    const providerId = providers[use];
    if (!select || !providerId) return;
    select.name = `${prefix}.model.${providerId}`;
    const stored = loaded[select.name] ?? '';
    const fallback = defaultModelOf(providerId, use) ?? '';
    const combo = searchable(select); // the select stays the field of the form; the admin sees a box that searches its options
    const draw = (models) => {
      select.replaceChildren(option('', fallback ? `Por defecto (${fallback})` : 'Sin modelo por defecto'));
      const groups = new Map(); // OpenRouter names a model vendor/model and offers hundreds: one group per vendor keeps the list usable
      for (const id of new Set([stored, ...models].filter(Boolean))) {
        const vendor = id.includes('/') ? id.slice(0, id.indexOf('/')) : '';
        if (!groups.has(vendor)) groups.set(vendor, []);
        groups.get(vendor).push(id);
      }
      for (const [vendor, ids] of groups) {
        if (!vendor) { select.append(...ids.map((id) => option(id))); continue; }
        const group = document.createElement('optgroup');
        group.label = vendor;
        group.append(...ids.map((id) => option(id)));
        select.append(group);
      }
      select.value = stored;
      combo.refresh();
    };
    draw([]);
    note.textContent = '';
    const result = await modelsOf(providerId);
    if (select.name !== `${prefix}.model.${providerId}`) return; // the provider changed again while the list came
    draw(result.models ?? []);
    note.textContent = result.models
      ? `${result.models.length} modelos disponibles en ${providerName(providerId)} ahora mismo (${label}).`
      : `No se ha podido consultar la lista de modelos: ${result.error}`;
  }));
}

export async function render(target, { entity }) {
  panel = target;
  sections = entity.sections;
  try {
    const { values, jobs, push_devices: pushDevices, mail, ai_uses: uses, ai_model: aiModel, ai_providers: providers, chat, guide } = await api('/manage/settings');
    aiUses = uses;
    aiProviders = providers ?? { providers: [], uses: {} };
    modelLists = new Map();
    chatInfo = chat;
    guideInfo = guide ?? {};
    loaded = Object.fromEntries(Object.entries(values).filter(([key]) => !SECRETS.includes(key) && !LOCKED.includes(key) && !key.startsWith('push.vapid')));
    for (const key of SECRETS) loaded[key] = null;
    loaded['ai.provider'] = aiProviders.uses.notices?.provider ?? null; // the one in use, so that saving without touching it does not store a pick
    mount(panel, view(values, jobs, pushDevices, mail, aiUses, aiModel, chat, guideInfo));
    const form = panel.querySelector('#admSettings');
    fill(form, values);
    if (form.elements['ai.provider']) form.elements['ai.provider'].value = aiProviders.uses.notices?.provider ?? '';
    for (const { prefix, use } of AI_USES.slice(1)) {
      if (form.elements[`${prefix}.provider`]) form.elements[`${prefix}.provider`].value = aiProviders.uses[use]?.picked ?? '';
    }
    syncModels(form);
    syncAnnualDay(form);
    syncAiOff(form);
    const budgets = panel.querySelector('#aicBudgets');
    if (budgets) renderBudgets(budgets); // the players' table of the money budget belongs with the limits, not with the usage
    const wallet = panel.querySelector('#aicWallet');
    if (wallet) renderWallet(wallet);
    form.addEventListener('change', (e) => {
      if (e.target.name === 'annual.month') syncAnnualDay(form);
      if (e.target.name === 'ai.enabled') syncAiOff(form);
      if (e.target.dataset?.use) syncModels(form); // a provider changed: every model list follows
    });
    form.addEventListener('submit', (e) => { e.preventDefault(); save(form); });
    form.addEventListener('click', (e) => {
      const act = e.target.closest('[data-set-act]')?.dataset.setAct;
      if (act === 'test') sendTest();
      else if (act === 'backup') downloadBackup(e.target.closest('[data-set-act]'));
      else if (act === 'test-email') sendTestEmail(mail);
      else if (act === 'test-ai') testAi(form);
      else if (act === 'test-chat') testChat();
      else if (act === 'test-guide') testGuide();
      else if (act === 'reset-prompt') resetPrompt(form, e.target.closest('[data-use]').dataset.use);
      else if (act === 'push-keys') generateKeys(values['push.vapid_private'].is_set);
    });
  } catch (err) {
    mount(panel, errorState(err.message));
  }
}
