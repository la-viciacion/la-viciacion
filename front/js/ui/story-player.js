// The player of a story: the progress bars, the slide on screen and how it is moved. It knows nothing about what a
// slide shows: `render(slide, index)` gives the markup and the page decides the rest.
//
//   phone:    tap the right third (or anywhere but the left third) for the next one, the left third for the one before,
//             hold to pause, swipe sideways to change slide
//   desktop:  click the same zones, ← → or space to move, Esc to leave, the pointer over the story pauses it
//
// The bar of the slide on screen fills with a CSS animation (--st-duration); when it ends the next slide comes up. The last
// slide does not move on by itself.
import { html, mount } from '../lib/html.js';

const HOLD_MS = 180; // a press longer than this is a pause, not a tap
const SWIPE_PX = 50;
const LEFT_ZONE = 0.33;

export function createStoryPlayer({ container, slides, render, duration = 6000, onClose, onChange }) {
  let index = 0;
  let held = false; // paused by a press
  let hovered = false; // paused by the pointer being over the story
  let hidden = false; // paused by the tab being in the background
  let pressedAt = null;
  let holdTimer = null;

  mount(container, html`
    <div class="st-stage" style="--st-duration:${duration}ms" tabindex="-1">
      <div class="st-bars" aria-hidden="true">${slides.map(() => html`<div class="st-bar"><i></i></div>`)}</div>
      <button type="button" class="st-close" aria-label="Cerrar">×</button>
      <div class="st-slide" aria-live="polite"></div>
    </div>`);
  const stage = container.querySelector('.st-stage');
  const bars = [...container.querySelectorAll('.st-bar')];
  const slot = container.querySelector('.st-slide');

  const paused = () => held || hovered || hidden;
  const last = () => index === slides.length - 1;

  function paint() {
    stage.dataset.theme = slides[index].theme;
    stage.dataset.slide = slides[index].id;
    bars.forEach((bar, i) => {
      const fill = bar.firstElementChild;
      bar.className = `st-bar${i < index ? ' done' : ''}${i === index ? (last() ? ' done' : ' active') : ''}`;
      fill.style.animationPlayState = paused() ? 'paused' : 'running';
      if (i === index) { // the bar starts again, also when the slide is the same one (back on the first)
        fill.style.animation = 'none';
        void fill.offsetWidth;
        fill.style.animation = '';
      }
    });
    mount(slot, render(slides[index], index));
    onChange?.(index, slides[index]);
  }

  function setPaused() {
    const active = bars[index].firstElementChild;
    active.style.animationPlayState = paused() ? 'paused' : 'running';
    stage.classList.toggle('paused', paused());
  }

  function go(to) {
    if (to < 0 || to >= slides.length || to === index) return;
    index = to;
    paint();
  }

  const next = () => go(index + 1);
  const previous = () => (index === 0 ? paint() : go(index - 1)); // on the first slide it starts over

  // the animation of the bar on screen ended: the slide's time is up
  stage.addEventListener('animationend', (event) => {
    if (event.target.parentElement === bars[index] && !last()) next();
  });

  const interactive = (event) => event.target.closest('button, a, input, select, textarea');

  stage.addEventListener('pointerdown', (event) => {
    if (interactive(event)) return;
    pressedAt = { x: event.clientX, time: Date.now() };
    holdTimer = setTimeout(() => {
      held = true;
      setPaused();
    }, HOLD_MS);
  });

  stage.addEventListener('pointerup', (event) => {
    if (!pressedAt) return;
    clearTimeout(holdTimer);
    const { x } = pressedAt;
    const wasHeld = held;
    pressedAt = null;
    held = false;
    setPaused();
    if (wasHeld) return;
    const moved = event.clientX - x;
    if (Math.abs(moved) >= SWIPE_PX) return moved < 0 ? next() : previous();
    const { left, width } = stage.getBoundingClientRect();
    return (event.clientX - left) / (width || 1) < LEFT_ZONE ? previous() : next();
  });

  stage.addEventListener('pointercancel', () => {
    clearTimeout(holdTimer);
    pressedAt = null;
    held = false;
    setPaused();
  });

  // only a mouse pauses by hovering: on a touch screen the pointer "enters" with every tap and would never leave
  stage.addEventListener('pointerenter', (event) => {
    if (event.pointerType !== 'mouse') return;
    hovered = true;
    setPaused();
  });
  stage.addEventListener('pointerleave', (event) => {
    if (event.pointerType !== 'mouse') return;
    hovered = false;
    setPaused();
  });
  container.querySelector('.st-close').addEventListener('click', () => onClose?.());

  const onKey = (event) => {
    if (event.key === 'ArrowRight' || event.key === ' ') {
      event.preventDefault();
      next();
    } else if (event.key === 'ArrowLeft') {
      event.preventDefault();
      previous();
    } else if (event.key === 'Escape') onClose?.();
  };
  const onVisibility = () => {
    hidden = document.hidden;
    setPaused();
  };
  document.addEventListener('keydown', onKey);
  document.addEventListener('visibilitychange', onVisibility);

  paint();

  return {
    get index() { return index; },
    next,
    previous,
    go,
    destroy() {
      clearTimeout(holdTimer);
      document.removeEventListener('keydown', onKey);
      document.removeEventListener('visibilitychange', onVisibility);
    },
  };
}
