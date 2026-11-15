// "Botón del chat" of the profile: whether the chat button is on this player's screens (PATCH /users/{username}/settings
// `show_chat`). Offered only while the chat works for them (GET /chat/status): with the group's chat off there is no button to
// hide. The button appears or goes away at once, without reloading.
import { api, jsonRequest } from '../../lib/api.js';
import { html, mount } from '../../lib/html.js';

export async function initChatBubble(el, { path }) {
  let status;
  try {
    status = await api('/chat/status');
  } catch {
    return; // optional: the rest of the page does not depend on it
  }
  if (!status?.available) return;

  mount(el, html`
    <form class="pf-card pf-form" novalidate>
      <label class="pf-check">
        <span class="pf-check-text">Mostrar el botón del chat
          <span class="pf-sub">Si lo desactivas, el botón del chat se oculta en tus pantallas hasta que lo vuelvas a activar.</span>
        </span>
        <input type="checkbox" name="show" ${status.bubble === false ? '' : 'checked'} />
      </label>
      <div class="pf-msg" role="status"></div>
    </form>`);

  const form = el.querySelector('form');
  const box = form.querySelector('input[name="show"]');
  const say = form.querySelector('.pf-msg');
  box.addEventListener('change', async () => {
    const shown = box.checked;
    try {
      await api(path, jsonRequest('PATCH', { show_chat: shown }));
    } catch (err) {
      box.checked = !shown;
      say.textContent = err.message;
      say.className = 'pf-msg err';
      return;
    }
    say.textContent = shown ? 'Guardado: el botón del chat se muestra' : 'Guardado: el botón del chat está oculto';
    say.className = 'pf-msg ok';
    const chat = await import('../../ui/chat.js');
    if (shown) await chat.mountChat();
    else chat.unmountChat();
  });
}
