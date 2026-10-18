// Story (#/story[/<period>[/<username>]]): the recap as full-screen slides, like the year in review of a music app.
// The same answer as the recap page (GET /statistics/recap/{period}?username=); lib/story.js decides the slides, ui/story-slides.js
// draws them and ui/story-player.js moves them. An admin can add a player's username to the address.
import { api } from '../../lib/api.js';
import { html, mount } from '../../lib/html.js';
import { lastMonth, periodLabel, recapHref } from '../../lib/recap.js';
import { buildSlides, parseStoryHash } from '../../lib/story.js';
import { SHARE_FILENAME, canShare, shareCard } from '../../lib/story-share.js';
import { shareImage } from '../../ui/story-image.js';
import { dismissRecapInvite } from '../../ui/recap-invite.js';
import { createStoryPlayer } from '../../ui/story-player.js';
import { animateCounts, renderSlide } from '../../ui/story-slides.js';
import { toast } from '../../ui/toast.js';

export const active = null; // it belongs to no item of the top bar

let player = null;
let period;
let other = null; // the player asked for, when it is not the user

const leave = () => { location.hash = recapHref(period, other); };

async function share(slide) {
  try {
    const card = shareCard(slide, `${periodLabel(period)} · La Viciación`);
    const result = await shareImage(card, { filename: SHARE_FILENAME(slide, period), title: `Mi resumen de ${periodLabel(period)}` });
    if (result === 'saved') toast('Imagen guardada');
  } catch (err) {
    console.error(err);
    toast('No se ha podido crear la imagen', 'err');
  }
}

export async function render({ user, main }) {
  dispose();
  const asked = parseStoryHash(location.hash);
  period = asked.period || lastMonth();
  other = user.is_admin && asked.username && asked.username !== user.username ? asked.username : null;
  if (!other) dismissRecapInvite(period); // the story is open: the notice of the first days of the month has done its job
  mount(main, html`<div class="st-overlay" id="stRoot"><div class="st-stage"><div class="st-slide"><div class="st-hint">Preparando tu resumen…</div></div></div></div>`);
  const root = main.querySelector('#stRoot');

  let data;
  try {
    data = await api(`/statistics/recap/${period}?username=${encodeURIComponent(other || user.username)}`);
  } catch (err) {
    mount(root, html`
      <div class="st-stage" data-theme="night"><div class="st-slide">
        <h2 class="st-title">No se ha podido cargar</h2><div class="st-line">${err.message}</div>
        <div class="st-actions"><button type="button" class="st-btn" data-act="close">Cerrar</button></div>
      </div></div>`);
    root.onclick = (event) => { if (event.target.closest('[data-act="close"]')) leave(); };
    return;
  }

  const slides = buildSlides(data);
  player = createStoryPlayer({
    container: root,
    slides,
    render: renderSlide,
    onClose: leave,
    onChange: () => animateCounts(root.querySelector('.st-slide')),
    onShare: share,
    shareable: canShare,
  });
  root.onclick = (event) => {
    const act = event.target.closest('[data-act]')?.dataset.act;
    if (act === 'close') leave();
    else if (act === 'replay') player.go(0);
    else if (act === 'share') share(slides.find((slide) => slide.id === 'hours') || slides[0]); // the goodbye has no picture: its button shares the hours
  };
}

export function dispose() {
  player?.destroy();
  player = null;
}
