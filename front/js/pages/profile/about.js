// The city and the birth date of the player: two more personal data inside the "Mis datos" form of the Ajustes tab,
// next to the name, the email and the Telegram ID, saved with the same button (PATCH /users/{username}/settings).
// Both are optional and private, and nothing here says what they are for.
//  - The city is searched by name (GET /users/places/search, Open-Meteo's geocoding) and picked from the answers:
//    what is saved is the name and the coordinates of the city's centre, never a GPS fix.
// `initAbout` fills `el` (a block inside that form, so no <form> of its own) and returns `save()`, which the form's
// submit calls before it saves the rest: it sends only what changed.
import { api, jsonRequest } from '../../lib/api.js';
import { html, mount } from '../../lib/html.js';

const today = () => new Date().toLocaleDateString('sv-SE');

const HELP = 'Busca tu ciudad y elígela de la lista. Solo se guarda su nombre y su centro, nunca tu ubicación exacta.';

export async function initAbout(el, { path }) {
  const saved = await api(path);
  if (!saved) return null;
  let place = saved.place_name ? { name: saved.place_name, latitude: saved.place_latitude, longitude: saved.place_longitude } : null;
  let found = [];

  mount(el, html`
    <label>Ciudad
      <span class="pf-place-current" data-current></span>
      <span class="pf-place-search">
        <input class="adm-input" type="search" name="place_query" placeholder="Busca tu ciudad" autocomplete="off" aria-label="Buscar ciudad" />
        <button class="pf-btn" type="button" data-search>Buscar</button>
        <button class="pf-btn" type="button" data-remove>Quitar</button>
      </span>
    </label>
    <ul class="pf-place-results" data-results></ul>
    <div class="pf-sub" data-help>${HELP}</div>
    <label>Fecha de nacimiento
      <input class="adm-input" type="date" name="birth_date" min="1900-01-01" max="${today()}" value="${saved.birth_date ?? ''}" />
    </label>
    <div class="pf-sub">Solo la ven tú y los administradores.</div>`);

  const current = el.querySelector('[data-current]');
  const results = el.querySelector('[data-results]');
  const help = el.querySelector('[data-help]');
  const query = el.querySelector('[name="place_query"]');
  const birth = el.querySelector('[name="birth_date"]');
  const remove = el.querySelector('[data-remove]');

  const showCurrent = () => {
    current.textContent = place ? place.name : 'Sin ciudad';
    remove.hidden = !place;
  };
  const showResults = () => mount(results, html`${found.map((item, index) => html`
    <li><button class="pf-btn" type="button" data-pick="${index}">${item.name}</button></li>`)}`);
  showCurrent();

  async function search() {
    const text = query.value.trim();
    if (text.length < 2) return void (help.textContent = 'Escribe al menos dos letras');
    try {
      found = await api(`/users/places/search?q=${encodeURIComponent(text)}`);
      showResults();
      help.textContent = found.length ? 'Elige tu ciudad de la lista y pulsa Guardar datos.' : 'No he encontrado esa ciudad';
    } catch (err) {
      help.textContent = err.message;
    }
  }

  el.querySelector('[data-search]').addEventListener('click', search);
  // Enter here must search, not save the whole form
  query.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter') return;
    e.preventDefault();
    search();
  });
  results.addEventListener('click', (e) => {
    const button = e.target.closest('[data-pick]');
    if (!button) return;
    place = found[Number(button.dataset.pick)];
    found = [];
    showResults();
    showCurrent();
    help.textContent = 'Pulsa Guardar datos para guardarla.';
  });
  remove.addEventListener('click', () => {
    place = null;
    showCurrent();
    help.textContent = 'Pulsa Guardar datos para quitarla.';
  });

  return {
    // Sends what changed since it was loaded or last saved; throws what the API answers.
    async save() {
      const changes = {};
      if ((place?.name ?? null) !== saved.place_name) {
        Object.assign(changes, { place_name: place?.name ?? null, place_latitude: place?.latitude ?? null, place_longitude: place?.longitude ?? null });
      }
      if ((birth.value || null) !== saved.birth_date) changes.birth_date = birth.value || null;
      if (!Object.keys(changes).length) return;
      Object.assign(saved, await api(path, jsonRequest('PATCH', changes)));
      help.textContent = HELP;
    },
  };
}
