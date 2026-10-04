// Personal preferences of the profile (PATCH /users/{username}/settings); the notices have their own
// section (notifications.js).
//  - "Jugando ahora": whether the others see you in the navbar chip while your timer runs.
import { api, jsonRequest } from '../../lib/api.js';
import { html, mount } from '../../lib/html.js';

const heading = (text) => html`<div class="section-header"><h2 class="section-title">${text}</h2><div class="section-line"></div></div>`;

export async function initPreferences(el, { path }) {
  const settings = await api(path);
  if (!settings) return;

  mount(el, html`
    ${heading('Jugando ahora')}
    <form class="pf-card pf-form" id="pfPlaying" novalidate>
      <label class="adm-check"><input type="checkbox" name="show" ${(settings.show_playing ?? settings.defaults.show_playing) ? 'checked' : ''} /> Mostrar a los demás cuándo estoy jugando</label>
      <div class="pf-sub">Si lo desactivas, el resto del grupo no te verá en «Jugando ahora» (tú sí verás el halo verde en tu avatar). Los avisos al grupo que ya existen no cambian.</div>
      <div class="pf-msg" role="status"></div>
    </form>`);

  const playing = el.querySelector('#pfPlaying');
  const say = playing.querySelector('.pf-msg');
  playing.show.addEventListener('change', async () => {
    try {
      await api(path, jsonRequest('PATCH', { show_playing: playing.show.checked }));
      say.textContent = playing.show.checked ? 'Guardado: los demás te verán cuando juegues' : 'Guardado: los demás no te verán cuando juegues';
      say.className = 'pf-msg ok';
    } catch (err) {
      playing.show.checked = !playing.show.checked;
      say.textContent = err.message;
      say.className = 'pf-msg err';
    }
  });
}
