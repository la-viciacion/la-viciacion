// Login page (the only page that does not need a session).
import { login } from '../lib/api.js';
import { html, mount } from '../lib/html.js';
import { iconEye, iconEyeOff, iconLock, iconUser } from '../ui/icons.js';

/** Render the login form; onSuccess runs once the token is stored. */
export function showLogin(onSuccess) {
  mount(document.getElementById('app'), html`
    <div class="login-page">
      <div class="login-card">
        <div class="login-brand">
          <img src="icon-192.png" alt="La Viciación logo" class="login-logo" />
          <h1>La Viciación</h1>
          <p>Accede a tu cuenta de gamer</p>
        </div>

        <form id="loginForm" novalidate>
          <div class="form-group">
            <label for="username">Usuario</label>
            <div class="input-wrap">
              ${iconUser()}
              <input type="text" id="username" name="username" placeholder="tu_usuario" autocomplete="username" required />
            </div>
          </div>

          <div class="form-group">
            <label for="password">Contraseña</label>
            <div class="input-wrap">
              ${iconLock()}
              <input type="password" id="password" name="password" placeholder="••••••••••••" autocomplete="current-password" required />
              <button type="button" class="password-toggle" id="pwToggle" aria-label="Mostrar/ocultar contraseña">${iconEye()}</button>
            </div>
          </div>

          <div class="login-error" id="loginError" role="alert"></div>

          <button type="submit" class="btn-primary" id="loginBtn">
            <span class="btn-text">Entrar</span>
            <div class="btn-spinner"></div>
          </button>
        </form>
      </div>
    </div>`);

  const password = document.getElementById('password');
  const toggle = document.getElementById('pwToggle');
  toggle.addEventListener('click', () => {
    const show = password.type === 'password';
    password.type = show ? 'text' : 'password';
    mount(toggle, show ? iconEyeOff() : iconEye());
  });

  document.getElementById('loginForm').addEventListener('submit', (e) => submit(e, onSuccess));
}

function showError(message) {
  const el = document.getElementById('loginError');
  if (!el) return;
  el.textContent = message;
  el.classList.add('visible');
}

async function submit(e, onSuccess) {
  e.preventDefault();
  const button = document.getElementById('loginBtn');
  const username = document.getElementById('username').value.trim();
  const password = document.getElementById('password').value;

  const error = document.getElementById('loginError');
  error.textContent = '';
  error.classList.remove('visible');

  if (!username || !password) return showError('Rellena todos los campos');

  button.disabled = true;
  button.classList.add('loading');
  try {
    await login(username, password);
    await onSuccess();
  } catch (err) {
    showError(err.message);
    button.disabled = false;
    button.classList.remove('loading');
  }
}
