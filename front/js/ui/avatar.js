// A player's avatar: the initial first and the photo when it arrives (GET /users/photo/{id}, any logged-in user).
// `aura`: 'live' (green, playing now), 'dim' (grey, a timer that is probably forgotten) or '' for none.
import { api } from '../lib/api.js';
import { html } from '../lib/html.js';

const photos = new Map(); // player id -> Promise<object URL | null>, kept while the app is open

const photo = (id) => {
  if (!photos.has(id)) {
    photos.set(id, api(`/users/photo/${id}`)
      .then((blob) => (blob instanceof Blob && blob.size ? URL.createObjectURL(blob) : null))
      .catch(() => null));
  }
  return photos.get(id);
};

/** `player` needs `user_id` and `name`. Call hydratePhotos on the container after mounting it. */
export const playerAvatar = (player, aura = '') =>
  html`<span class="pl-avatar ${aura}" data-photo="${player.user_id}" aria-hidden="true">${player.name[0].toUpperCase()}</span>`;

export function hydratePhotos(root) {
  root.querySelectorAll('[data-photo]').forEach((el) => {
    photo(Number(el.dataset.photo)).then((url) => {
      if (!url || !el.isConnected) return;
      el.style.backgroundImage = `url("${url}")`;
      el.textContent = '';
    });
  });
}
