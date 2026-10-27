// What the world outside says about a game, on its page: the description under the title (Steam's, in Spanish; RAWG's, in
// English, when Steam has none), the publisher and the platforms, a few small facts (Metacritic and the age rating, beside
// the RAWG button) and a "Multimedia" card with the trailer and a carousel of screenshots.
// On a wide screen the trailer sits beside the header and the carousel runs below it (profile.css); on a phone the
// card is one folded block. GET /games/{id}/extras asks Steam and RAWG (the API keeps the answer for a day), so it is loaded apart,
// after the page is drawn; a game neither knows, or a failure, shows nothing. The card starts folded and the trailer
// only loads when it is played, so opening a game costs no video.
import { api } from '../lib/api.js';
import { createFolds, toggleFold } from '../lib/fold.js';
import { html, mount } from '../lib/html.js';
import { iconChevron } from './icons.js';

const KEY = 'media';

// The API only sends https links from the hosts it trusts; this keeps the page safe whatever it is given
const safe = (url) => (typeof url === 'string' && url.startsWith('https://') ? url : null);

// Metacritic's own bands: green from 75, yellow from 50, red below
const metaTone = (score) => (score >= 75 ? 'good' : score >= 50 ? 'mid' : 'bad');
const ESRB_CODES = { Everyone: 'E', 'Everyone 10+': 'E10+', Teen: 'T', Mature: 'M', 'Adults Only': 'AO', 'Rating Pending': 'RP' };

const facts = (x) => [
  x.metacritic ? html`<span class="gm-fact" title="Nota de la crítica en Metacritic"><b class="gm-badge ${metaTone(x.metacritic)}">${x.metacritic}</b><span>Metacritic</span></span>` : '',
  x.esrb ? html`<span class="gm-fact" title="Clasificación por edades (ESRB)"><b class="gm-badge age">${ESRB_CODES[x.esrb] || '?'}</b><span>${x.esrb}</span></span>` : '',
];

// The publisher only when it is not the developer too ("Rockstar Games" under "Rockstar Studios" says something; "Hades" by itself does not)
const metaLines = (x, dev) => {
  const publishers = (x.publishers || []).filter((p) => !dev || !dev.toLowerCase().includes(p.toLowerCase()));
  return [
    publishers.length ? `Editor: ${publishers.join(', ')}` : '',
    x.platforms?.length ? `Disponible en: ${x.platforms.join(' · ')}` : '',
  ].filter(Boolean);
};

const hasFacts = (x) => x.metacritic || x.esrb;
const hasMedia = (x) => (x.trailer && safe(x.trailer.url)) || x.screenshots?.some((s) => safe(s.full));

function trailerButton(trailer) {
  const poster = safe(trailer.poster);
  return html`
    <button type="button" class="gm-trailer" data-trailer aria-label="Ver el tráiler">
      ${poster ? html`<img src="${poster}" alt="" loading="lazy" />` : ''}
      <span class="gm-play" aria-hidden="true">▶</span>
    </button>`;
}

/** Fills `head` (the small facts) and `media` (the card) for the game; nothing at all when there is nothing to say. */
export async function showExtras({ head, desc, meta, media }, game) {
  let x;
  try {
    x = await api(`/games/${encodeURIComponent(game.id)}/extras`);
  } catch {
    return;
  }
  if (!x?.available) return;
  if (hasFacts(x)) mount(head, html`${facts(x)}`);
  if (x.description) {
    mount(desc, html`<p class="gm-desc" title="Pulsa para ver todo el texto">${x.description_lang === 'en' ? html`<span class="pf-tag muted" title="RAWG la tiene solo en inglés">En inglés</span> ` : ''}${x.description}</p>`);
    desc.onclick = () => desc.firstElementChild.classList.add('open');
  }
  const lines = metaLines(x, game.dev);
  if (lines.length) mount(meta, html`<div class="pf-sub gm-meta">${lines.map((line) => html`<div>${line}</div>`)}</div>`);
  if (!hasMedia(x)) return;

  const trailer = x.trailer && safe(x.trailer.url) ? x.trailer : null;
  if (trailer) media.closest('.gm-top')?.classList.add('has-trailer'); // only then the wide header makes room for it
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
          ${trailer ? trailerButton(trailer) : ''}
          ${shots.length ? html`
            <div class="gm-carousel">
              <button type="button" class="gm-nav prev" data-shots="-1" aria-label="Capturas anteriores">‹</button>
              <div class="gm-shots">${shots.map((s) => html`
                <a href="${s.full}" target="_blank" rel="noopener noreferrer"><img src="${safe(s.thumb) || s.full}" alt="Captura del juego" loading="lazy" /></a>`)}</div>
              <button type="button" class="gm-nav next" data-shots="1" aria-label="Capturas siguientes">›</button>
            </div>` : ''}
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
    const nav = e.target.closest('[data-shots]');
    if (nav) {
      const row = media.querySelector('.gm-shots');
      row.scrollBy({ left: Number(nav.dataset.shots) * row.clientWidth * 0.8, behavior: 'smooth' });
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
