// "Redactar aviso": write a notice and send it through ONE channel at a time, Telegram (the default) or the app (push),
// so each can be tried on its own. Telegram takes Markdown (lib/announce-format.js draws the preview); the app's
// notifications are plain text. Whatever is sent here goes only through the chosen channel.
import { api, jsonRequest } from '../../lib/api.js';
import { BODY_MAX as TELEGRAM_BODY_MAX, MESSAGE_MAX, blocks, drawnLength } from '../../lib/announce-format.js';
import { html, mount } from '../../lib/html.js';
import { toast } from '../../ui/toast.js';
import { errorState, store } from './components.js';
import { confirmDialog } from './dialogs.js';

const TITLE_MAX = 80;
const BODY_MAX = 240; // the app's notifications; Telegram has TELEGRAM_BODY_MAX
const LINKS = [
  ['#/notifications', 'Avisos'],
  ['/', 'Inicio'],
  ['#/profile', 'Mi perfil'],
];
const CHANNELS = [
  ['telegram', 'Telegram'],
  ['push', 'Aviso en la app (PWA)'],
];
const SYNTAX = '# Título · **negrita** · *cursiva* · ~~tachado~~ · `código` · [texto](https://…) · - viñeta · 1. lista · > cita · ---';
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
  const channel = form.elements.channel.value;
  const kind = form.querySelector('#annAudience').value;
  const id = kind === 'me' ? store.me : form.querySelector('#annUser').value;
  if (channel === 'telegram') {
    if (!audience.telegram.ready) return { ok: false, text: 'Telegram no está configurado: falta el token del bot (Avisos → Canales).' };
    if (kind === 'group') {
      return audience.telegram.group
        ? { ok: true, text: 'Llegará al grupo de Telegram.' }
        : { ok: false, text: 'Falta el ID del grupo de Telegram (Avisos → Canales).' };
    }
    const target = userById(id);
    return target?.telegram_id
      ? { ok: true, text: `Llegará por mensaje privado a ${target.username}.` }
      : { ok: false, text: `${target?.username || 'El usuario'} no tiene Telegram ID.` };
  }
  if (!audience.ready) return { ok: false, text: 'Los avisos en la app no están activados (Avisos → Canales).' };
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
        <label>Mensaje <textarea class="adm-input adm-ann-body" name="body" rows="8" maxlength="${TELEGRAM_BODY_MAX}" placeholder="Opcional"></textarea></label>
        <div class="adm-sub" id="annCount"></div>
        <div class="adm-sub" id="annSyntax"></div>
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
        <div class="adm-notif" id="annPreview" aria-hidden="true">
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
  const options = AUDIENCES[form.elements.channel.value];
  mount(select, html`${options.map(([value, label]) => html`<option value="${value}">${label}</option>`)}`);
  select.value = options.some(([value]) => value === before) ? before : options[0][0];
}

const piece = (p) => {
  if (p.href) return html`<a href="${p.href}" target="_blank" rel="noopener noreferrer">${p.text}</a>`;
  if (p.style === 'b') return html`<strong>${p.text}</strong>`;
  if (p.style === 'i') return html`<em>${p.text}</em>`;
  if (p.style === 's') return html`<s>${p.text}</s>`;
  if (p.style === 'code') return html`<code>${p.text}</code>`;
  return p.text;
};
const pieces = (list) => list.map(piece);

// The message as Telegram will show it: what lib/announce-format.js understands, drawn; the rest stays text.
const markdownPreview = (body) => blocks(body).map((b) => {
  if (b.type === 'gap') return html`<div class="adm-md-gap"></div>`;
  if (b.type === 'rule') return html`<div class="adm-md-rule"></div>`;
  if (b.type === 'code') return html`<pre class="adm-md-code">${b.text}</pre>`;
  if (b.type === 'quote') return html`<blockquote class="adm-md-quote">${b.lines.map((line, i) => html`${i ? html`<br />` : ''}${pieces(line)}`)}</blockquote>`;
  if (b.type === 'heading') return html`<div><strong>${pieces(b.pieces)}</strong></div>`;
  if (b.type === 'item') return html`<div class="adm-md-item" style="padding-left: ${b.level * 1.2}em">${b.mark} ${pieces(b.pieces)}</div>`;
  return html`<div>${pieces(b.pieces)}</div>`;
});

function refresh(form) {
  const telegram = form.elements.channel.value === 'telegram';
  const title = form.elements.title.value.trim();
  const body = form.elements.body.value.trim();
  const image = form.elements.image.value.trim();
  form.querySelector('#annAppOnly').hidden = telegram;
  form.querySelector('#annPreviewApp').textContent = telegram ? 'Telegram · La Viciación' : 'La Viciación · ahora';
  form.querySelector('#annPreviewTitle').textContent = title || 'Título del aviso';
  const preview = form.querySelector('#annPreviewBody');
  preview.classList.toggle('markdown', telegram);
  if (telegram) mount(preview, html`${markdownPreview(body)}`);
  else preview.textContent = body;
  form.querySelector('#annPreviewNote').textContent = telegram
    ? 'En Telegram el título sale en negrita y el mensaje debajo, con el formato que escribas. Es una vista aproximada: Telegram dibuja a su manera.'
    : 'Texto plano, sin formato. En el móvil el mensaje se recorta a unas líneas hasta que se despliega; lo importante, en el título.';
  form.querySelector('#annSyntax').textContent = telegram ? `Formato: ${SYNTAX}` : 'Los avisos de la app son texto plano: sin formato ni enlaces.';
  form.elements.body.maxLength = telegram ? TELEGRAM_BODY_MAX : BODY_MAX;
  const img = form.querySelector('#annPreviewImage');
  img.hidden = telegram || !/^https:\/\//.test(image);
  if (!img.hidden && img.getAttribute('src') !== image) img.setAttribute('src', image);
  form.querySelector('#annCount').textContent = telegram
    ? `Título ${title.length}/${TITLE_MAX} · Mensaje ${body.length}/${TELEGRAM_BODY_MAX} · Telegram: ${drawnLength(title, body)}/${MESSAGE_MAX}`
    : `Título ${title.length}/${TITLE_MAX} · Mensaje ${body.length}/${BODY_MAX}`;
  form.querySelector('#annUserWrap').hidden = form.querySelector('#annAudience').value !== 'user';
  form.querySelector('#annReach').textContent = reach(form).text;
}

async function submit(form) {
  const errorEl = form.querySelector('.adm-error');
  errorEl.textContent = '';
  const channel = form.elements.channel.value;
  const kind = form.querySelector('#annAudience').value;
  const payload = {
    title: form.elements.title.value.trim(),
    body: form.elements.body.value.trim() || null,
    audience: kind,
    user_id: kind === 'user' ? Number(form.querySelector('#annUser').value) : null,
  };
  if (!payload.title) { errorEl.textContent = 'Escribe un título'; return; }
  const telegram = channel === 'telegram';
  if ((payload.body?.length ?? 0) > (telegram ? TELEGRAM_BODY_MAX : BODY_MAX)) { errorEl.textContent = 'El mensaje es demasiado largo para este canal'; return; }
  if (telegram && drawnLength(payload.title, payload.body) > MESSAGE_MAX) { errorEl.textContent = 'Así dibujado no cabe en un mensaje de Telegram: acórtalo'; return; }
  const target = reach(form);
  if (!target.ok) { errorEl.textContent = target.text; return; }
  if (kind === 'group' || kind === 'all') {
    const ok = await confirmDialog('Enviar aviso', html`
      <p><strong>${payload.title}</strong></p>
      ${payload.body ? html`<div class="adm-notif-body markdown">${telegram ? markdownPreview(payload.body) : payload.body}</div>` : ''}
      <p>${channel === 'telegram' ? 'Se enviará al grupo de Telegram.' : `Se enviará a ${plural(target.devices, 'dispositivo', 'dispositivos')} (${plural(target.users, 'usuario', 'usuarios')}).`} No se puede deshacer.</p>`, { ok: 'Enviar' });
    if (!ok) return;
  }
  try {
    if (channel === 'telegram') {
      const { message } = await api('/manage/telegram/announce', jsonRequest('POST', payload));
      toast(`Aviso por Telegram: ${message.toLowerCase()}`);
    } else {
      const { sent, failed } = await api('/manage/push/announce', jsonRequest('POST', { ...payload, url: form.elements.url.value, image: form.elements.image.value.trim() || null }));
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
    form.elements.channel.addEventListener('change', () => fillAudiences(form));
    form.addEventListener('input', () => refresh(form));
    form.addEventListener('change', () => refresh(form));
    form.addEventListener('submit', (e) => { e.preventDefault(); submit(form); });
  } catch (err) {
    mount(panel, errorState(err.message));
  }
}
