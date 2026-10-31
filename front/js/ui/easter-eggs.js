// Hidden surprises. Mounted once for the whole app: the listeners sit on the document, so they outlive the
// navbar, which every page draws again.
import { KONAMI_KEYS, KONAMI_SWIPES, keyStep, sequenceMatcher, swipeStep, tapCounter } from '../lib/easter-eggs.js';
import { toast } from './toast.js';

export const LOGO_MESSAGES = [
  'Tranquilo, el home no se va a ir a ningún sitio',
  '¿Buscas algo? Aquí solo hay vicio',
  'Un clic más y te pongo un timer',
  'El logo ya no aguanta más, déjalo respirar',
];

const RAIN = ['🎮', '🕹️', '👾', '🎲', '🏆'];
const RAIN_COUNT = 36;
const RAIN_MS = 5000;

function rainOfGames() {
  if (document.querySelector('.konami-rain')) return;
  const rain = document.createElement('div');
  rain.className = 'konami-rain';
  rain.setAttribute('aria-hidden', 'true');
  for (let i = 0; i < RAIN_COUNT; i++) {
    const piece = document.createElement('span');
    piece.textContent = RAIN[i % RAIN.length];
    piece.style.left = `${Math.random() * 100}%`;
    piece.style.animationDelay = `${Math.random() * 1.5}s`;
    piece.style.animationDuration = `${2.5 + Math.random() * 2}s`;
    rain.appendChild(piece);
  }
  document.body.appendChild(rain);
  setTimeout(() => rain.remove(), RAIN_MS);
}

function konami() {
  rainOfGames();
  toast('↑↑↓↓←→←→BA · +30 vidas');
}

let mounted = false;

export function mountEasterEggs() {
  if (mounted) return;
  mounted = true;

  const typing = (el) => el?.closest?.('input, textarea, select, [contenteditable]');
  const keys = sequenceMatcher(KONAMI_KEYS);
  document.addEventListener('keydown', (e) => {
    if (e.repeat || typing(e.target)) return;
    const step = keyStep(e.key);
    if (step && keys(step)) konami();
  });

  const swipes = sequenceMatcher(KONAMI_SWIPES);
  let start = null;
  document.addEventListener('touchstart', (e) => {
    start = e.touches.length === 1 ? { x: e.touches[0].clientX, y: e.touches[0].clientY } : null;
  }, { passive: true });
  document.addEventListener('touchend', (e) => {
    const end = e.changedTouches[0];
    if (!start || !end) return;
    const step = swipeStep(end.clientX - start.x, end.clientY - start.y);
    start = null;
    if (swipes(step)) konami();
  }, { passive: true });

  // the logo keeps taking you home; this only counts the clicks
  const logoClicks = tapCounter();
  document.addEventListener('click', (e) => {
    if (e.target.closest?.('.navbar-brand') && logoClicks()) {
      toast(LOGO_MESSAGES[Math.floor(Math.random() * LOGO_MESSAGES.length)]);
    }
  });
}
