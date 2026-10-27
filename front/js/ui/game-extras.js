// What the world outside says about a game, on its page: a few small facts under the title (Metacritic, the age rating,
// the official site) and a folded "Multimedia" card with the description in Spanish, the trailer and
// screenshots. GET /games/{id}/extras asks Steam and RAWG (the API keeps the answer for a day), so it is loaded apart,
// after the page is drawn; a game neither knows, or a failure, shows nothing. The card starts folded and the trailer
// only loads when it is played, so opening a game costs no video.
import { api } from '../lib/api.js';
import { createFolds, toggleFold } from '../lib/fold.js';
import { html, mount } from '../lib/html.js';
import { iconChevron } from './icons.js';

const KEY = 'media';

// The API only sends https links from the hosts it trusts; this keeps the page safe whatever it is given
const safe = (url) => (typeof url === 'string' && url.startsWith('https://') ? url : null);

const facts = (x) => [
  x.metacritic ? html`<span class="pf-tag muted" title="Nota de la crítica en Metacritic">Metacritic ${x.metacritic}</span>` : '',
  x.esrb ? html`<span class="pf-tag muted" title="Clasificación por edades (ESRB)">${x.esrb}</span>` : '',
  safe(x.website) ? html`<a class="game-link" href="${x.website}" target="_blank" rel="noopener noreferrer">Web oficial ↗</a>` : '',
];

const hasFacts = (x) => x.metacritic || x.esrb || safe(x.website);
const hasMedia = (x) => x.description || (x.trailer && safe(x.trailer.url)) || x.screenshots?.length;

function trailerButton(trailer) {
  const poster = safe(trailer.poster);
  return html`
    <button type="button" class="gm-trailer" data-trailer aria-label="Ver el tráiler">
      ${poster ? html`<img src="${poster}" alt="" loading="lazy" />` : ''}
      <span class="gm-play" aria-hidden="true">▶</span>
    </button>`;
}

/** Fills `head` (the small facts) and `media` (the card) for the game; nothing at all when there is nothing to say. */
export async function showExtras({ head, media }, gameId) {
  let x;
  try {
    x = await api(`/games/${encodeURIComponent(gameId)}/extras`);
  } catch {
    return;
  }
  if (!x?.available) return;
  if (hasFacts(x)) mount(head, html`<div class="gm-outside">${facts(x)}</div>`);
  if (!hasMedia(x)) return;

  const trailer = x.trailer && safe(x.trailer.url) ? x.trailer : null;
  const shots = (x.screenshots || []).filter((s) => safe(s.full));
  const folds = createFolds();
  folds.set(KEY, true); // folded until asked for
  mount(media, html`
    <section class="ach-block folded" id="gmMediaBlock">
      <button type="button" class="section-header ach-fold" data-fold aria-expanded="false">
        <h2 class="section-title">Multimedia</h2><div class="section-line"></div><span class="ach-chevron" aria-hidden="true">${iconChevron()}</span>
      </button>
      <div class="ach-content">
        <div class="pf-card gm-media">
          ${x.description ? html`<p class="gm-desc">${x.description}</p>` : ''}
          ${trailer ? trailerButton(trailer) : ''}
          ${shots.length ? html`<div class="gm-shots">${shots.map((s) => html`
            <a href="${s.full}" target="_blank" rel="noopener noreferrer"><img src="${safe(s.thumb) || s.full}" alt="Captura del juego" loading="lazy" /></a>`)}</div>` : ''}
          <div class="pf-sub gm-credit">Datos de Steam y RAWG</div>
        </div>
      </div>
    </section>`);
  media.onclick = (e) => {
    const fold = e.target.closest('[data-fold]');
    if (fold) {
      toggleFold(folds, KEY, media.querySelector('#gmMediaBlock'), fold);
      return;
    }
    const play = e.target.closest('[data-trailer]');
    if (!play || !trailer) return;
    const video = document.createElement('video');
    video.className = 'gm-trailer';
    video.controls = true;
    video.autoplay = true;
    video.playsInline = true;
    if (safe(trailer.poster)) video.poster = trailer.poster;
    video.src = trailer.url;
    play.replaceWith(video);
  };
}
