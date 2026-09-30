// "Avisos" tab: write a push notification and send it to your own devices (to
// try it), to one user, to the devices that want group notices or to everybody.
// Plain text only; the preview shows roughly what a phone will display.
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
  ['#/profile/juegos', 'Mis juegos'],
];
const AUDIENCES = [
  ['me', 'Mis dispositivos (prueba)'],
  ['user', 'Un usuario…'],
  ['group', 'Quienes reciben los avisos del grupo'],
  ['all', 'Todos los dispositivos suscritos'],
];

let panel;
let audience; // counts from the API

const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

function reach(form) {
  const kind = form.querySelector('#annAudience').value;
  if (kind === 'all') return audience.all;
  if (kind === 'group') return audience.group;
  const id = kind === 'me' ? store.me : Number(form.querySelector('#annUser').value);
  return { devices: audience.users[id] || 0, users: audience.users[id] ? 1 : 0 };
}

function view() {
  return html`
    <form class="adm-settings" id="annForm" novalidate>
      <section class="adm-set-card">
        <h3>Redactar aviso</h3>
        <label>Título <input class="adm-input" type="text" name="title" maxlength="${TITLE_MAX}" required placeholder="Lo primero que se lee" /></label>
        <label>Mensaje <textarea class="adm-input" name="body" rows="3" maxlength="${BODY_MAX}" placeholder="Opcional. Texto plano: sin formato ni enlaces"></textarea></label>
        <div class="adm-sub" id="annCount"></div>
        <div class="adm-set-row">
          <label>Al pulsarlo abre
            <select class="adm-input" name="url">${LINKS.map(([value, label]) => html`<option value="${value}">${label}</option>`)}</select>
          </label>
          <label>Imagen (URL https, opcional)
            <input class="adm-input" type="url" name="image" placeholder="https://…" />
          </label>
        </div>
        <div class="adm-sub">La imagen se muestra grande en Android y en escritorio; iPhone y iPad la ignoran.</div>
      </section>

      <section class="adm-set-card">
        <h3>Destinatarios</h3>
        <div class="adm-set-row">
          <label>Enviar a
            <select class="adm-input" id="annAudience">${AUDIENCES.map(([value, label]) => html`<option value="${value}">${label}</option>`)}</select>
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
          <div class="adm-notif-app">La Viciación · ahora</div>
          <div class="adm-notif-title" id="annPreviewTitle"></div>
          <div class="adm-notif-body" id="annPreviewBody"></div>
          <img class="adm-notif-image" id="annPreviewImage" alt="" hidden />
        </div>
        <div class="adm-sub">Texto plano. En el móvil el mensaje se recorta a unas líneas hasta que se despliega; lo importante, en el título.</div>
      </section>

      <div class="adm-error" role="alert"></div>
      <div class="adm-actions adm-set-actions"><button class="adm-btn primary" type="submit">Enviar aviso</button></div>
    </form>`;
}

function refresh(form) {
  const title = form.title.value.trim();
  const body = form.body.value.trim();
  const image = form.image.value.trim();
  form.querySelector('#annPreviewTitle').textContent = title || 'Título del aviso';
  form.querySelector('#annPreviewBody').textContent = body;
  const img = form.querySelector('#annPreviewImage');
  img.hidden = !/^https:\/\//.test(image);
  if (!img.hidden && img.getAttribute('src') !== image) img.setAttribute('src', image);
  form.querySelector('#annCount').textContent = `Título ${title.length}/${TITLE_MAX} · Mensaje ${body.length}/${BODY_MAX}`;
  form.querySelector('#annUserWrap').hidden = form.querySelector('#annAudience').value !== 'user';
  const { devices, users } = reach(form);
  form.querySelector('#annReach').textContent = devices
    ? `Llegará a ${plural(devices, 'dispositivo', 'dispositivos')}${users > 1 ? ` de ${users} usuarios` : ''}.`
    : 'No hay ningún dispositivo suscrito en ese destino.';
}

async function submit(form) {
  const errorEl = form.querySelector('.adm-error');
  errorEl.textContent = '';
  const kind = form.querySelector('#annAudience').value;
  const payload = {
    title: form.title.value.trim(),
    body: form.body.value.trim() || null,
    url: form.url.value,
    image: form.image.value.trim() || null,
    audience: kind,
    user_id: kind === 'user' ? Number(form.querySelector('#annUser').value) : null,
  };
  if (!payload.title) { errorEl.textContent = 'Escribe un título'; return; }
  if (kind === 'group' || kind === 'all') {
    const { devices, users } = reach(form);
    const ok = await confirmDialog('Enviar aviso', html`
      <p><strong>${payload.title}</strong></p>
      ${payload.body ? html`<p>${payload.body}</p>` : ''}
      <p>Se enviará a ${plural(devices, 'dispositivo', 'dispositivos')} (${plural(users, 'usuario', 'usuarios')}). No se puede deshacer.</p>`, { ok: 'Enviar' });
    if (!ok) return;
  }
  try {
    const { sent, failed } = await api('/manage/push/announce', jsonRequest('POST', payload));
    toast(`Aviso enviado a ${plural(sent, 'dispositivo', 'dispositivos')}${failed ? ` (${failed} fallaron)` : ''}`);
  } catch (err) {
    errorEl.textContent = err.message;
  }
}

export async function render(target) {
  panel = target;
  try {
    audience = await api('/manage/push/audience');
    if (!audience.ready) {
      mount(panel, errorState('Los avisos push no están activados (actívalos en Avisos en la app).'));
      return;
    }
    mount(panel, view());
    const form = panel.querySelector('#annForm');
    refresh(form);
    form.addEventListener('input', () => refresh(form));
    form.addEventListener('change', () => refresh(form));
    form.addEventListener('submit', (e) => { e.preventDefault(); submit(form); });
  } catch (err) {
    mount(panel, errorState(err.message));
  }
}
