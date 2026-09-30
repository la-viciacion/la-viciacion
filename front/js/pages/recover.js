// Password recovery (public pages, like the login): ask for the link by email, and choose the new
// password with it. The flow is in the API (routers/basic.py); the link is `#/reset-password?token=`.
import { api, jsonRequest } from '../lib/api.js';
import { html, mount } from '../lib/html.js';
import { PASSWORD_HINT, isValidPassword } from '../lib/password.js';
import { iconLock, iconUser } from '../ui/icons.js';

const card = (subtitle, body) => html`
  <div class="login-page">
    <div class="login-card">
      <div class="login-brand">
        <img src="icon-192.png" alt="La Viciación logo" class="login-logo" />
        <h1>La Viciación</h1>
        <p>${subtitle}</p>
      </div>
      ${body}
    </div>
  </div>`;

function show(subtitle, body) {
  mount(document.getElementById('app'), card(subtitle, body));
}

function message(kind, text) {
  const el = document.getElementById('recoverMessage');
  el.textContent = text;
  el.className = `login-${kind} visible`;
}

async function send(button, request) {
  button.disabled = true;
  button.classList.add('loading');
  document.getElementById('recoverMessage').className = 'login-error';
  try {
    await request();
  } catch (err) {
    message('error', err.message);
    button.disabled = false;
    button.classList.remove('loading');
    return false;
  }
  return true;
}

/** Ask for the recovery email. `back` returns to the login. */
export function showForgotPassword(back) {
  show('Te enviaremos un enlace para elegir una nueva contraseña', html`
    <form id="recoverForm" novalidate>
      <div class="form-group">
        <label for="recoverLogin">Email o usuario</label>
        <div class="input-wrap">
          ${iconUser()}
          <input type="text" id="recoverLogin" placeholder="tu@email.com o usuario" autocomplete="username" required />
        </div>
      </div>
      <div class="login-error" id="recoverMessage" role="alert"></div>
      <button type="submit" class="btn-primary" id="recoverBtn">
        <span class="btn-text">Enviar enlace</span>
        <div class="btn-spinner"></div>
      </button>
    </form>
    <button type="button" class="login-link" id="recoverBack">Volver a entrar</button>`);

  document.getElementById('recoverBack').addEventListener('click', back);
  document.getElementById('recoverForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const login = document.getElementById('recoverLogin').value.trim();
    const button = document.getElementById('recoverBtn');
    if (!login) return message('error', 'Escribe tu email o usuario');
    let answer;
    const ok = await send(button, async () => {
      answer = await api('/auth/forgot-password', jsonRequest('POST', { login }));
    });
    if (ok) {
      message('info', answer.message);
      button.classList.remove('loading');
      button.textContent = 'Enlace enviado';
    }
  });
}

/** Choose the new password. `token` comes from the link (null when it is missing). */
export function showResetPassword(token, back, askAgain) {
  if (!token) {
    show('Enlace no válido', html`
      <div class="login-error visible" role="alert">El enlace no es válido o ha caducado.</div>
      <button type="button" class="btn-primary" id="resetAgain"><span class="btn-text">Pedir un enlace nuevo</span></button>`);
    document.getElementById('resetAgain').addEventListener('click', askAgain);
    return;
  }
  show('Elige tu nueva contraseña', html`
    <form id="resetForm" novalidate>
      <div class="form-group">
        <label for="resetPassword">Nueva contraseña</label>
        <div class="input-wrap">
          ${iconLock()}
          <input type="password" id="resetPassword" autocomplete="new-password" required />
        </div>
      </div>
      <div class="form-group">
        <label for="resetRepeat">Repítela</label>
        <div class="input-wrap">
          ${iconLock()}
          <input type="password" id="resetRepeat" autocomplete="new-password" required />
        </div>
      </div>
      <p class="login-hint">${PASSWORD_HINT}</p>
      <div class="login-error" id="recoverMessage" role="alert"></div>
      <button type="submit" class="btn-primary" id="resetBtn">
        <span class="btn-text">Cambiar contraseña</span>
        <div class="btn-spinner"></div>
      </button>
    </form>`);

  document.getElementById('resetForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const password = document.getElementById('resetPassword').value;
    if (!isValidPassword(password)) return message('error', `La contraseña debe tener ${PASSWORD_HINT.toLowerCase()}`);
    if (password !== document.getElementById('resetRepeat').value) return message('error', 'Las dos contraseñas no coinciden');
    let answer;
    const ok = await send(document.getElementById('resetBtn'), async () => {
      answer = await api('/auth/reset-password', jsonRequest('POST', { token, new_password: password }));
    });
    if (!ok) return;
    show('Listo', html`
      <div class="login-info visible" role="status">${answer.message}</div>
      <button type="button" class="btn-primary" id="resetDone"><span class="btn-text">Entrar</span></button>`);
    document.getElementById('resetDone').addEventListener('click', back);
  });
}
