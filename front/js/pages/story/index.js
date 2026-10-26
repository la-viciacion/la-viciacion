// Story (#/story[/<period>[/<username>]]): the recap as full-screen slides, like the year in review of a music app.
// The same answer as the recap page (GET /statistics/recap/{period}?username=); lib/story.js decides the slides, ui/story-slides.js
// draws them and ui/story-player.js moves them. An admin can add a player's username to the address.
import { api } from '../../lib/api.js';
import { html, mount } from '../../lib/html.js';
import { clampPick, lastMonth, periodKey, periodLabel, pickOf, recapHref } from '../../lib/recap.js';
import { buildSlides, parseStoryHash } from '../../lib/story.js';
import { SHARE_FILENAME, canShare, shareCard } from '../../lib/story-share.js';
import { shareImage } from '../../ui/story-image.js';
import { dismissRecapInvite } from '../../ui/recap-invite.js';
import { createStoryPlayer } from '../../ui/story-player.js';
import { animateCounts, renderSlide } from '../../ui/story-slides.js';
import { toast } from '../../ui/toast.js';

export const active = null; // it belongs to no item of the top bar

// api/src/utils/messages.py RECAP_SEASON_LOCKED: told apart from any other failure to show a friendlier single slide
const SEASON_LOCKED = 'El resumen de esta temporada todavía no está disponible';

let player = null;
let period;
let named = null; // the player an admin's address names, even themselves
let other = null; // the player asked for, when it is not the user

const leave = () => { location.hash = recapHref(period, named); };

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
  // the same bounds as the recap page: a month that has not finished (the running one) falls back to the one before
  period = periodKey(clampPick(pickOf(asked.period || lastMonth())));
  named = user.is_admin ? asked.username : null; // an admin naming a player (the panel's links) sees it without a player's limits
  other = named && named !== user.username ? named : null;
  if (!other) dismissRecapInvite(period); // the story is open: the notice of the first days of the month has done its job
  mount(main, html`<div class="st-overlay" id="stRoot"><div class="st-stage"><div class="st-slide"><div class="st-hint">Preparando tu resumen…</div></div></div></div>`);
  const root = main.querySelector('#stRoot');

  let data;
  try {
    data = await api(`/statistics/recap/${period}?username=${encodeURIComponent(named || user.username)}${named ? '&unrestricted=true' : ''}`);
  } catch (err) {
    const locked = err.detail === SEASON_LOCKED;
    mount(root, html`
      <div class="st-stage" data-theme="night"><div class="st-slide">
        ${locked ? html`
          <div class="st-emoji">⏳</div>
          <h2 class="st-title">Cargando…</h2>
          <div class="st-line">No, en serio: no seas ansia y espera a que acabe el año.</div>
        ` : html`
          <h2 class="st-title">No se ha podido cargar</h2><div class="st-line">${err.message}</div>
        `}
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
