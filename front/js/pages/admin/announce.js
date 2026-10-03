// "Redactar aviso": write a notice and send it through ONE channel at a time, the app (push) or
// Telegram, so each can be tried on its own. Plain text only; the preview shows roughly what the
// receiver will see. Whatever is sent here goes only through the chosen channel.
import { api, jsonRequest } from '../../lib/api.js';
import { html, mount } from '../../lib/html.js';
import { toast } from '../../ui/toast.js';
import { errorState, store } from './components.js';
import { confirmDialog } from './dialogs.js';

const TITLE_MAX = 80;
const BODY_MAX = 240;
const LINKS = [
  ['/', 'Inicio'],
  ['#/profile', 'Mi perfil'],
];
const CHANNELS = [
  ['push', 'Aviso en la app (PWA)'],
  ['telegram', 'Telegram'],
];
// who it can go to, by channel
const AUDIENCES = {
  push: [
    ['me', 'Mis dispositivos (prueba)'],
    ['user', 'Un usuario…'],
    ['group', 'Quienes reciben los avisos del grupo'],
    ['all', 'Todos los dispositivos suscritos'],
  ],
  telegram: [
    ['me', 'Yo, por mensaje privado (prueba)'],
    ['user', 'Un usuario…'],
    ['group', 'El grupo de Telegram'],
  ],
};

let panel;
let audience; // what the API says each channel can reach

const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;
const userById = (id) => store.users.find((u) => u.id === Number(id));

// What the chosen channel and audience would reach, and whether it can be sent at all.
function reach(form) {
  const channel = form.channel.value;
  const kind = form.querySelector('#annAudience').value;
  const id = kind === 'me' ? store.me : form.querySelector('#annUser').value;
  if (channel === 'telegram') {
    if (!audience.telegram.ready) return { ok: false, text: 'Telegram no está configurado: falta el token del bot (Notificaciones → Ajustes).' };
    if (kind === 'group') {
      return audience.telegram.group
        ? { ok: true, text: 'Llegará al grupo de Telegram.' }
        : { ok: false, text: 'Falta el ID del grupo de Telegram (Notificaciones → Ajustes).' };
    }
    const target = userById(id);
    return target?.telegram_id
      ? { ok: true, text: `Llegará por mensaje privado a ${target.username}.` }
      : { ok: false, text: `${target?.username || 'El usuario'} no tiene Telegram ID.` };
  }
  if (!audience.ready) return { ok: false, text: 'Los avisos en la app no están activados (Notificaciones → Ajustes).' };
  const { devices, users } = kind === 'all' ? audience.all : kind === 'group' ? audience.group : { devices: audience.users[id] || 0, users: audience.users[id] ? 1 : 0 };
  return devices
    ? { ok: true, text: `Llegará a ${plural(devices, 'dispositivo', 'dispositivos')}${users > 1 ? ` de ${users} usuarios` : ''}.`, devices, users }
    : { ok: false, text: 'No hay ningún dispositivo suscrito en ese destino.' };
}

function view() {
  return html`
    <form class="adm-settings" id="annForm" novalidate>
      <section class="adm-set-card">
        <h3>Canal</h3>
        <label>Enviar por
          <select class="adm-input" name="channel">${CHANNELS.map(([value, label]) => html`<option value="${value}">${label}</option>`)}</select>
        </label>
        <div class="adm-sub">Cada aviso sale solo por el canal elegido: lo que mandes por Telegram no llega a la app y al revés.</div>
      </section>

      <section class="adm-set-card">
        <h3>Redactar aviso</h3>
        <label>Título <input class="adm-input" type="text" name="title" maxlength="${TITLE_MAX}" required placeholder="Lo primero que se lee" /></label>
        <label>Mensaje <textarea class="adm-input" name="body" rows="3" maxlength="${BODY_MAX}" placeholder="Opcional. Texto plano: sin formato ni enlaces"></textarea></label>
        <div class="adm-sub" id="annCount"></div>
        <div id="annAppOnly">
          <div class="adm-set-row">
            <label>Al pulsarlo abre
              <select class="adm-input" name="url">${LINKS.map(([value, label]) => html`<option value="${value}">${label}</option>`)}</select>
            </label>
            <label>Imagen (URL https, opcional)
              <input class="adm-input" type="url" name="image" placeholder="https://…" />
            </label>
          </div>
          <div class="adm-sub">La imagen se muestra grande en Android y en escritorio; iPhone y iPad la ignoran. Solo en los avisos de la app.</div>
        </div>
      </section>

      <section class="adm-set-card">
        <h3>Destinatarios</h3>
        <div class="adm-set-row">
          <label>Enviar a
            <select class="adm-input" id="annAudience"></select>
          </label>
          <label id="annUserWrap" hidden>Usuario
            <select class="adm-input" id="annUser">${store.users.map((u) => html`<option value="${u.id}">${u.username}</option>`)}</select>
          </label>
        </div>
        <div class="adm-sub" id="annReach"></div>
      </section>

      <section class="adm-set-card">
        <h3>Así se verá</h3>
        <div class="adm-notif" aria-hidden="true">
          <div class="adm-notif-app" id="annPreviewApp"></div>
          <div class="adm-notif-title" id="annPreviewTitle"></div>
          <div class="adm-notif-body" id="annPreviewBody"></div>
          <img class="adm-notif-image" id="annPreviewImage" alt="" hidden />
        </div>
        <div class="adm-sub" id="annPreviewNote"></div>
      </section>

      <div class="adm-error" role="alert"></div>
      <div class="adm-actions adm-set-actions"><button class="adm-btn primary" type="submit">Enviar aviso</button></div>
    </form>`;
}

// The audiences depend on the channel: rebuild the list keeping the choice when it still exists.
function fillAudiences(form) {
  const select = form.querySelector('#annAudience');
  const before = select.value;
  const options = AUDIENCES[form.channel.value];
  mount(select, html`${options.map(([value, label]) => html`<option value="${value}">${label}</option>`)}`);
  select.value = options.some(([value]) => value === before) ? before : options[0][0];
}

function refresh(form) {
  const telegram = form.channel.value === 'telegram';
  const title = form.title.value.trim();
  const body = form.body.value.trim();
  const image = form.image.value.trim();
  form.querySelector('#annAppOnly').hidden = telegram;
  form.querySelector('#annPreviewApp').textContent = telegram ? 'Telegram · La Viciación' : 'La Viciación · ahora';
  form.querySelector('#annPreviewTitle').textContent = title || 'Título del aviso';
  form.querySelector('#annPreviewBody').textContent = body;
  form.querySelector('#annPreviewNote').textContent = telegram
    ? 'En Telegram el título sale en negrita y el mensaje debajo, en texto plano.'
    : 'Texto plano. En el móvil el mensaje se recorta a unas líneas hasta que se despliega; lo importante, en el título.';
  const img = form.querySelector('#annPreviewImage');
  img.hidden = telegram || !/^https:\/\//.test(image);
  if (!img.hidden && img.getAttribute('src') !== image) img.setAttribute('src', image);
  form.querySelector('#annCount').textContent = `Título ${title.length}/${TITLE_MAX} · Mensaje ${body.length}/${BODY_MAX}`;
  form.querySelector('#annUserWrap').hidden = form.querySelector('#annAudience').value !== 'user';
  form.querySelector('#annReach').textContent = reach(form).text;
}

async function submit(form) {
  const errorEl = form.querySelector('.adm-error');
  errorEl.textContent = '';
  const channel = form.channel.value;
  const kind = form.querySelector('#annAudience').value;
  const payload = {
    title: form.title.value.trim(),
    body: form.body.value.trim() || null,
    audience: kind,
    user_id: kind === 'user' ? Number(form.querySelector('#annUser').value) : null,
  };
  if (!payload.title) { errorEl.textContent = 'Escribe un título'; return; }
  const target = reach(form);
  if (!target.ok) { errorEl.textContent = target.text; return; }
  if (kind === 'group' || kind === 'all') {
    const ok = await confirmDialog('Enviar aviso', html`
      <p><strong>${payload.title}</strong></p>
      ${payload.body ? html`<p>${payload.body}</p>` : ''}
      <p>${channel === 'telegram' ? 'Se enviará al grupo de Telegram.' : `Se enviará a ${plural(target.devices, 'dispositivo', 'dispositivos')} (${plural(target.users, 'usuario', 'usuarios')}).`} No se puede deshacer.</p>`, { ok: 'Enviar' });
    if (!ok) return;
  }
  try {
    if (channel === 'telegram') {
      const { message } = await api('/manage/telegram/announce', jsonRequest('POST', payload));
      toast(`Aviso por Telegram: ${message.toLowerCase()}`);
    } else {
      const { sent, failed } = await api('/manage/push/announce', jsonRequest('POST', { ...payload, url: form.url.value, image: form.image.value.trim() || null }));
      toast(`Aviso enviado a ${plural(sent, 'dispositivo', 'dispositivos')}${failed ? ` (${failed} fallaron)` : ''}`);
    }
  } catch (err) {
    errorEl.textContent = err.message;
  }
}

export async function render(target) {
  panel = target;
  try {
    audience = await api('/manage/push/audience');
    mount(panel, view());
    const form = panel.querySelector('#annForm');
    fillAudiences(form);
    refresh(form);
    form.channel.addEventListener('change', () => fillAudiences(form));
    form.addEventListener('input', () => refresh(form));
    form.addEventListener('change', () => refresh(form));
    form.addEventListener('submit', (e) => { e.preventDefault(); submit(form); });
  } catch (err) {
    mount(panel, errorState(err.message));
  }
}
