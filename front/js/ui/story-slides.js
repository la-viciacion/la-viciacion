// What each kind of slide of a story looks like (the slides come from lib/story.js). One function per kind, each
// gives the markup of one slide; the frame, the bar and the movement are the player's (story-player.js).
import { formatDuration } from '../lib/format.js';
import { html } from '../lib/html.js';
import { bigDuration, longDate } from '../lib/story.js';

const MEDALS = ['🥇', '🥈', '🥉'];
const WEEKDAY_LETTERS = ['L', 'M', 'X', 'J', 'V', 'S', 'D'];

const kicker = (text) => html`<div class="st-kicker">${text}</div>`;
const cover = (game, size = '') => (game.image_url
  ? html`<img class="st-cover ${size}" src="${game.image_url}" alt="" crossorigin="anonymous" />`
  : html`<div class="st-cover ${size} st-cover-empty" aria-hidden="true">🎮</div>`);

/** A figure that counts up when the slide appears (see animateCounts); it already holds the final value. */
const counter = (value, unit) => html`<div class="st-big"><span class="st-count" data-count="${value}">${value}</span><span class="st-unit">${unit}</span></div>`;

const trend = ({ text, trend: direction }) => html`<span class="st-trend ${direction}">${text}</span>`;

const bar = (label, share, { highlight = false, value = '' } = {}) => html`
  <div class="st-row ${highlight ? 'hl' : ''}">
    <div class="st-row-label"><span>${label}</span><span>${value}</span></div>
    <div class="st-meter"><div style="--w:${Math.max(2, Math.round(share * 100))}%"></div></div>
  </div>`;

const KINDS = {
  intro: (s) => html`
    <div class="st-emoji">🎮</div>
    ${kicker(s.label)}
    <h1 class="st-title">${s.name}, así fue tu ${s.span} en La Viciación</h1>
    <div class="st-hint">Toca para seguir</div>`,

  hours: (s) => {
    const big = bigDuration(s.seconds);
    return html`
      ${kicker('Has jugado')}
      ${counter(big.value, big.unit)}
      <div class="st-line">${trend(s.change)} frente a ${s.previousLabel} (${formatDuration(s.previous)})</div>
      <div class="st-line">${s.sessions} ${s.sessions === 1 ? 'sesión' : 'sesiones'} en ${s.days} ${s.days === 1 ? 'día' : 'días'}</div>
      ${s.position ? html`<div class="st-pill">Puesto ${s.position}º del grupo</div>` : ''}`;
  },

  star: (s) => html`
    ${kicker('Tu juego estrella')}
    ${cover(s.game, 'xl')}
    <h2 class="st-title">${s.game.name}</h2>
    <div class="st-line">${formatDuration(s.game.seconds)} · el ${s.sharePercent} de tu tiempo</div>`,

  topgames: (s) => html`
    ${kicker('Tu top de juegos')}
    <ol class="st-rank">
      ${s.games.map((game, i) => html`
        <li style="--i:${i}">
          <span class="st-rank-n">${i + 1}</span>${cover(game, 'sm')}
          <span class="st-rank-main"><strong>${game.name}</strong><small>${formatDuration(game.seconds)}</small></span>
        </li>`)}
    </ol>`,

  bestday: (s) => html`
    ${kicker('Tu día más activo')}
    <h2 class="st-title">${longDate(s.day)}</h2>
    <div class="st-line">${formatDuration(s.seconds)} jugadas ese día</div>
    ${s.grid ? html`
      <div class="st-grid" aria-hidden="true">
        ${WEEKDAY_LETTERS.map((letter) => html`<span class="st-grid-head">${letter}</span>`)}
        ${s.grid.flat().map((cell) => (cell
          ? html`<span class="st-cell l${cell.level}${cell.day === s.day ? ' best' : ''}"></span>`
          : html`<span class="st-cell blank"></span>`))}
      </div>` : ''}`,

  weekday: (s) => html`
    ${kicker('Tu día favorito para jugar')}
    <h2 class="st-title">${s.favorite.name}</h2>
    <div class="st-line">El ${Math.round(s.favorite.share * 100)} % de tu tiempo</div>
    <div class="st-columns" aria-hidden="true">
      ${s.byWeekday.map((seconds, i) => html`
        <div class="st-column ${i === s.favorite.index ? 'hl' : ''}">
          <div class="st-column-bar"><div style="--h:${Math.max(3, Math.round((seconds / s.favorite.seconds) * 100))}%"></div></div>
          <span>${WEEKDAY_LETTERS[i]}</span>
        </div>`)}
    </div>`,

  daypart: (s) => html`
    <div class="st-emoji">${s.favorite.emoji}</div>
    ${kicker('Tu hora de jugar')}
    <h2 class="st-title">${s.favorite.title}</h2>
    <div class="st-line">Juegas sobre todo por la ${s.favorite.label}: el ${Math.round(s.favorite.share * 100)} % de tu tiempo</div>
    <div class="st-rows">
      ${s.favorite.parts.map((part) => bar(part.label, part.seconds / s.favorite.seconds, { highlight: part.key === s.favorite.key, value: formatDuration(part.seconds) }))}
    </div>`,

  genres: (s) => html`
    ${kicker('Tus géneros')}
    <h2 class="st-title">${s.genres[0].genre}</h2>
    <div class="st-line">es lo que más has jugado</div>
    <div class="st-rows">
      ${s.genres.map((g, i) => bar(g.genre, g.seconds / s.genres[0].seconds, { highlight: i === 0, value: formatDuration(g.seconds) }))}
    </div>`,

  streak: (s) => html`
    ${kicker('Tu mejor racha')}
    ${s.streak > 1 ? counter(s.streak, 'días seguidos') : ''}
    ${s.longest ? html`<div class="st-line">Tu sesión más larga: <strong>${formatDuration(s.longest)}</strong></div>` : ''}`,

  playmate: (s) => html`
    <div class="st-emoji">🤝</div>
    ${kicker('Tu compañero de partidas')}
    <h2 class="st-title">${s.playmate.name}</h2>
    <div class="st-line">${formatDuration(s.playmate.seconds)} jugando juntos al mismo juego</div>`,

  milestones: (s) => html`
    ${kicker('Lo que has conseguido')}
    <div class="st-stats">
      ${s.started ? html`<div><strong>${s.started}</strong><span>${s.started === 1 ? 'juego empezado' : 'juegos empezados'}</span></div>` : ''}
      ${s.completed ? html`<div><strong>${s.completed}</strong><span>${s.completed === 1 ? 'completado' : 'completados'}</span></div>` : ''}
      ${s.achievements ? html`<div><strong>${s.achievements}</strong><span>${s.achievements === 1 ? 'logro' : 'logros'}</span></div>` : ''}
    </div>
    ${s.rarest ? html`<div class="st-line">Tu logro más raro: <strong>${s.rarest.title}</strong></div>` : ''}`,

  group: (s) => {
    const big = bigDuration(s.seconds);
    return html`
      ${kicker('Y el grupo')}
      ${counter(big.value, big.unit)}
      <div class="st-line">${trend(s.change)} frente a ${s.previousLabel} · ${s.players} ${s.players === 1 ? 'jugador' : 'jugadores'}</div>
      <ol class="st-podium">
        ${s.podium.map((row, i) => html`<li style="--i:${i}"><span>${MEDALS[i]}</span><strong>${row.name}</strong><small>${formatDuration(row.seconds)}</small></li>`)}
      </ol>
      ${s.game ? html`<div class="st-line">El juego del mes: <strong>${s.game.name || s.game.game_id}</strong></div>` : ''}`;
  },

  outro: (s) => html`
    <div class="st-emoji">✨</div>
    <h2 class="st-title">Eso fue ${s.label}</h2>
    <div class="st-line">¡Nos vemos en el siguiente!</div>
    <div class="st-actions">
      <button type="button" class="st-btn primary" data-act="share">Compartir mi resumen</button>
      <button type="button" class="st-btn" data-act="replay">Volver a ver</button>
      <button type="button" class="st-btn" data-act="close">Cerrar</button>
    </div>`,

  empty: (s) => html`
    <div class="st-emoji">🎮</div>
    ${kicker(s.label)}
    <h2 class="st-title">Este periodo no hay nada que contar</h2>
    <div class="st-line">${s.group ? 'Pero mira lo que hizo el grupo.' : 'Nadie jugó.'}</div>
    ${s.group ? '' : html`<div class="st-actions"><button type="button" class="st-btn" data-act="close">Cerrar</button></div>`}`,
};

/** The markup of a slide. */
export const renderSlide = (slide) => KINDS[slide.kind](slide);

/** Count the figures of the slide on screen up from zero. They hold their final value, so with reduced motion, or
 * no animation frames, nothing changes. */
export function animateCounts(root, { duration = 900, now = () => performance.now() } = {}) {
  const reduce = globalThis.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  if (reduce || typeof requestAnimationFrame !== 'function') return;
  for (const el of root.querySelectorAll('[data-count]')) {
    const target = Number(el.dataset.count);
    const start = now();
    const step = () => {
      if (!el.isConnected) return;
      const progress = Math.min(1, (now() - start) / duration);
      el.textContent = String(Math.round(target * (1 - (1 - progress) ** 3)));
      if (progress < 1) requestAnimationFrame(step);
    };
    el.textContent = '0';
    requestAnimationFrame(step);
  }
}
