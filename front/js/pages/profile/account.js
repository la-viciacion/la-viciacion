// "Mis datos" and "Cambiar contraseña" forms of the Ajustes tab.
import { api, jsonRequest } from '../../lib/api.js';
import { PASSWORD_HINT, isValidPassword } from '../../lib/password.js';
import { flash } from './flash.js';

// `user` is the session user: it is updated in place after saving so the rest of the app sees the change.
export function initAccount(main, { user, userPath }) {
  main.querySelector('#pfData').addEventListener('submit', async (e) => {
    e.preventDefault();
    const form = e.currentTarget;
    const msg = main.querySelector('#pfDataMsg');
    // The email identifies the account, so it is only sent when filled in.
    const telegram = form.telegram_id.value.trim();
    const changes = { name: form.name.value, telegram_id: telegram === '' ? null : Number(telegram) };
    if (form.email.value.trim()) changes.email = form.email.value;
    try {
      const updated = await api(userPath('profile'), jsonRequest('PATCH', changes));
      Object.assign(user, { name: updated.name, email: updated.email, telegram_id: updated.telegram_id });
      const shown = updated.name || updated.username;
      main.querySelector('.pf-title').textContent = shown;
      const navName = document.querySelector('.navbar-username');
      if (navName) navName.textContent = shown;
      flash(msg, 'Datos guardados', true);
    } catch (err) {
      flash(msg, err.message);
    }
  });

  main.querySelector('#pfPass').addEventListener('submit', async (e) => {
    e.preventDefault();
    const form = e.currentTarget;
    const msg = main.querySelector('#pfPassMsg');
    if (!form.current.value) return flash(msg, 'Introduce tu contraseña actual');
    if (!isValidPassword(form.next.value)) return flash(msg, `La contraseña debe tener ${PASSWORD_HINT.toLowerCase()}`);
    if (form.next.value !== form.again.value) return flash(msg, 'Las contraseñas nuevas no coinciden');
    try {
      await api(userPath('password'), jsonRequest('POST', {
        current_password: form.current.value,
        new_password: form.next.value,
      }));
      form.reset();
      flash(msg, 'Contraseña actualizada', true);
    } catch (err) {
      flash(msg, err.message);
    }
  });
}
