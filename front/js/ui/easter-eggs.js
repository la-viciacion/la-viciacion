// Hidden surprises. Mounted once for the whole app: the listeners sit on the document, so they outlive the
// navbar, which every page draws again.
import { KONAMI_KEYS, KONAMI_SWIPES, keyStep, sequenceMatcher, swipeStep, tapCounter } from '../lib/easter-eggs.js';
import { toast } from './toast.js';

export const LOGO_MESSAGES = [
  '🏆 Logro oculto desbloqueado. Recompensa: nada',
  '🏆 Logro oculto desbloqueado. Recompensa: ninguna, pero con estilo',
  '🏆 Logro oculto desbloqueado. Recompensa: ¿esperabas algo?'
];

const BLAST_PARTICLES = 28;
const BLAST_MS = 1400;

// The explosion bursts from the middle of the logo and is cleared when it ends
function logoBlast(brand) {
  if (document.querySelector('.logo-blast')) return;
  const box = brand.getBoundingClientRect();
  const blast = document.createElement('div');
  blast.className = 'logo-blast';
  blast.setAttribute('aria-hidden', 'true');
  blast.style.left = `${box.left + box.width / 2}px`;
  blast.style.top = `${box.top + box.height / 2}px`;
  for (const part of ['logo-blast-flash', 'logo-blast-ring', 'logo-blast-ring logo-blast-ring-late']) {
    const el = document.createElement('span');
    el.className = part;
    blast.appendChild(el);
  }
  for (let i = 0; i < BLAST_PARTICLES; i++) {
    const angle = (i / BLAST_PARTICLES) * 2 * Math.PI + Math.random() * 0.4;
    const distance = 70 + Math.random() * 130;
    const spark = document.createElement('span');
    spark.className = 'logo-blast-spark';
    spark.style.setProperty('--dx', `${Math.cos(angle) * distance}px`);
    spark.style.setProperty('--dy', `${Math.sin(angle) * distance}px`);
    spark.style.animationDelay = `${Math.random() * 0.12}s`;
    blast.appendChild(spark);
  }
  document.body.appendChild(blast);
  brand.classList.add('logo-shake');
  setTimeout(() => {
    blast.remove();
    brand.classList.remove('logo-shake');
  }, BLAST_MS);
}

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

// Each egg is an achievement, and only goes off while its achievement can be earned (`isArmed(name)`, asked when the
// egg is about to go off; before that day a player who found it would not try again). `onEasterEgg(name)` is told
// when one went off ('logo', 'konami'), so the app can report it.
export function mountEasterEggs({ onEasterEgg = () => {}, isArmed = async () => true } = {}) {
  if (mounted) return;
  mounted = true;

  const goOff = (name, effect) => isArmed(name).then((armed) => {
    if (!armed) return;
    effect();
    onEasterEgg(name);
  }).catch(() => {});

  const typing = (el) => el?.closest?.('input, textarea, select, [contenteditable]');
  const keys = sequenceMatcher(KONAMI_KEYS);
  document.addEventListener('keydown', (e) => {
    if (e.repeat || typing(e.target)) return;
    const step = keyStep(e.key);
    if (step && keys(step)) goOff('konami', konami);
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
    if (swipes(step)) goOff('konami', konami);
  }, { passive: true });

  // the logo keeps taking you home; this only counts the clicks
  const logoClicks = tapCounter();
  document.addEventListener('click', (e) => {
    const brand = e.target.closest?.('.navbar-brand');
    if (brand && logoClicks()) {
      goOff('logo', () => {
        logoBlast(brand);
        toast(LOGO_MESSAGES[Math.floor(Math.random() * LOGO_MESSAGES.length)]);
      });
    }
  });
}
