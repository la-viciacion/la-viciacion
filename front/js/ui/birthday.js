// The birthday of the player: the logo wears a cake all day and, the first time the app opens that day on this device,
// a modal greets them with confetti. Only the player themself ever sees it, and it never says their age.
import { api } from '../lib/api.js';
import { hasGreeted, isBirthday, markGreeted } from '../lib/easter-eggs.js';
import { html } from '../lib/html.js';
import { openModal } from './modal.js';

const CONFETTI_COUNT = 60;
const CONFETTI_MS = 5500;

// the birth date of each player this session, so the navbar (drawn again by every page) can wear the cake at once
const birthDates = new Map();

/** The birth date already read for this player, or null (not read yet, or none set). */
export const knownBirthDate = (user) => birthDates.get(user.username) ?? null;

function confetti() {
  if (document.querySelector('.birthday-confetti')) return;
  const rain = document.createElement('div');
  rain.className = 'birthday-confetti';
  rain.setAttribute('aria-hidden', 'true');
  for (let i = 0; i < CONFETTI_COUNT; i++) {
    const piece = document.createElement('span');
    piece.style.left = `${Math.random() * 100}%`;
    piece.style.setProperty('--drift', `${Math.round(Math.random() * 120 - 60)}px`);
    piece.style.animationDelay = `${Math.random() * 1.2}s`;
    piece.style.animationDuration = `${2.5 + Math.random() * 2}s`;
    rain.appendChild(piece);
  }
  document.body.appendChild(rain);
  setTimeout(() => rain.remove(), CONFETTI_MS);
}

function greet(user) {
  openModal(html`
    <div class="birthday-modal" role="alertdialog" aria-labelledby="birthdayTitle">
      <div class="birthday-cake" aria-hidden="true">🎂</div>
      <h3 id="birthdayTitle">¡Feliz cumpleaños, ${user.name || user.username}!</h3>
      <p>Hoy es tu día. Que no se te acaben ni las partidas ni la batería.</p>
      <button class="pf-btn primary" type="button" data-close>¡Gracias!</button>
    </div>`, { onClose: () => document.querySelector('.birthday-confetti')?.remove() });
  confetti();
}

/** Put the cake on the logo if today is the player's birthday and greet them the first time that day. A player who
 * set no birth date costs one request per session and sees nothing. */
export async function celebrateBirthday(user, now = new Date()) {
  if (!birthDates.has(user.username)) {
    const settings = await api(`/users/${encodeURIComponent(user.username)}/settings`);
    birthDates.set(user.username, settings?.birth_date ?? null);
  }
  if (!isBirthday(knownBirthDate(user), now)) return;
  document.querySelector('.navbar-brand')?.classList.add('skin-birthday');
  if (hasGreeted(user.username, now)) return;
  markGreeted(user.username, now);
  greet(user);
}
