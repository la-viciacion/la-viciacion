// "Mis datos" and "Cambiar contraseña" forms of the Ajustes tab.
import { api, jsonRequest } from '../../lib/api.js';
import { PASSWORD_HINT, isValidPassword } from '../../lib/password.js';
import { flash } from './flash.js';

// `user` is the session user: it is updated in place after saving so the rest of the app sees the change.
// `about` gives the city and birth date block (about.js, null until it has loaded), which is saved with the rest.
export function initAccount(main, { user, userPath, about = () => null }) {
  main.querySelector('#pfData').addEventListener('submit', async (e) => {
    e.preventDefault();
    const form = e.currentTarget;
    const msg = main.querySelector('#pfDataMsg');
    // The email identifies the account, so it is only sent when filled in. The Telegram ID is not edited here: it is linked
    // with /activate in the group, and this form only unlinks it (below).
    const changes = { name: form.name.value };
    if (form.email.value.trim()) changes.email = form.email.value;
    try {
      await about()?.save();
      const updated = await api(userPath('profile'), jsonRequest('PATCH', changes));
      Object.assign(user, { name: updated.name, email: updated.email });
      const shown = updated.name || updated.username;
      main.querySelector('.pf-title').textContent = shown;
      const navName = document.querySelector('.navbar-username');
      if (navName) navName.textContent = shown;
      flash(msg, 'Datos guardados', true);
    } catch (err) {
      flash(msg, err.message);
    }
  });

  main.querySelector('#pfTelegramUnlink').addEventListener('click', async (e) => {
    const button = e.currentTarget;
    const msg = main.querySelector('#pfDataMsg');
    if (user.telegram_id == null) return flash(msg, 'No tienes ningún Telegram vinculado');
    button.disabled = true;
    try {
      const updated = await api(userPath('profile'), jsonRequest('PATCH', { telegram_id: null }));
      user.telegram_id = updated.telegram_id;
      main.querySelector('#pfData').telegram_id.value = '';
      flash(msg, 'Telegram desvinculado. Para volver a vincularlo escribe /activate al bot en el grupo', true);
    } catch (err) {
      flash(msg, err.message);
    } finally {
      button.disabled = false;
    }
  });

  main.querySelector('#pfTelegramTest').addEventListener('click', async (e) => {
    const button = e.currentTarget;
    const msg = main.querySelector('#pfDataMsg');
    if (user.telegram_id == null) return flash(msg, 'No tienes ningún Telegram vinculado: escribe /activate al bot en el grupo');
    button.disabled = true;
    try {
      await api(userPath('telegram-test'), { method: 'POST' });
      flash(msg, 'Mensaje enviado: mira tu Telegram', true);
    } catch (err) {
      flash(msg, err.message);
    } finally {
      button.disabled = false;
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
