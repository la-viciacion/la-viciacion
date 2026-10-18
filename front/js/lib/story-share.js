// What a slide looks like as a picture to share. Pure: no DOM, so it can be tested. The card is the slide reduced to what
// reads well on an image (in the first person: whoever shares it is the one talking); ui/story-image.js paints it.
import { formatDuration } from './format.js';
import { bigDuration, longDate } from './story.js';

/** The colours of each theme of a slide, as the CSS has them (css/story.css). */
export const THEMES = {
  teal: { from: '#0f5c4d', mid: '#0a2a3a', accent: '#3dd9b3' },
  gold: { from: '#6b4a06', mid: '#3a2a0a', accent: '#f5c542' },
  purple: { from: '#4a2a8f', mid: '#231a45', accent: '#a78bfa' },
  pink: { from: '#8f1f5c', mid: '#3d1233', accent: '#f472b6' },
  night: { from: '#1b2450', mid: '#0d1130', accent: '#8ab4ff' },
};

const duration = (seconds) => {
  const big = bigDuration(seconds);
  return `${big.value} ${big.unit}`;
};

const CARDS = {
  intro: (s) => ({ kicker: s.label, title: s.name, lines: [`Así fue mi ${s.span} en La Viciación`] }),
  hours: (s) => ({
    kicker: 'He jugado', title: duration(s.seconds),
    lines: [`${s.change.text} frente a ${s.previousLabel}`, `${s.sessions} ${s.sessions === 1 ? 'sesión' : 'sesiones'} en ${s.days} ${s.days === 1 ? 'día' : 'días'}`, ...(s.position ? [`Puesto ${s.position}º del grupo`] : [])],
  }),
  star: (s) => ({ kicker: 'Mi juego estrella', title: s.game.name, lines: [`${formatDuration(s.game.seconds)} · el ${s.sharePercent} de mi tiempo`], covers: [s.game.image_url] }),
  topgames: (s) => ({ kicker: 'Mi top de juegos', title: '', lines: s.games.map((game, i) => `${i + 1}. ${game.name} · ${formatDuration(game.seconds)}`), covers: s.games.map((g) => g.image_url) }),
  bestday: (s) => ({ kicker: 'Mi día más activo', title: longDate(s.day), lines: [`${formatDuration(s.seconds)} jugadas ese día`] }),
  weekday: (s) => ({ kicker: 'Mi día favorito para jugar', title: s.favorite.name, lines: [`El ${Math.round(s.favorite.share * 100)} % de mi tiempo`] }),
  daypart: (s) => ({
    kicker: 'Mi hora de jugar', title: `${s.favorite.emoji} ${s.favorite.title}`,
    lines: [`Juego sobre todo por la ${s.favorite.label}: el ${Math.round(s.favorite.share * 100)} % de mi tiempo`],
  }),
  genres: (s) => ({ kicker: 'Mis géneros', title: s.genres[0].genre, lines: s.genres.map((g) => `${g.genre} · ${formatDuration(g.seconds)}`) }),
  streak: (s) => ({ kicker: 'Mi mejor racha', title: s.streak > 1 ? `${s.streak} días seguidos` : '', lines: s.longest ? [`Mi sesión más larga: ${formatDuration(s.longest)}`] : [] }),
  playmate: (s) => ({ kicker: 'Mi compañero de partidas', title: s.playmate.name, lines: [`${formatDuration(s.playmate.seconds)} jugando juntos`] }),
  milestones: (s) => ({
    kicker: 'Lo que he conseguido', title: '',
    lines: [
      ...(s.started ? [`${s.started} ${s.started === 1 ? 'juego empezado' : 'juegos empezados'}`] : []),
      ...(s.completed ? [`${s.completed} ${s.completed === 1 ? 'completado' : 'completados'}`] : []),
      ...(s.achievements ? [`${s.achievements} ${s.achievements === 1 ? 'logro' : 'logros'}`] : []),
      ...(s.rarest ? [`El más raro: ${s.rarest.title}`] : []),
    ],
  }),
  group: (s) => ({
    kicker: 'El grupo', title: duration(s.seconds),
    lines: [`${s.change.text} frente a ${s.previousLabel}`, ...s.podium.map((row, i) => `${['🥇', '🥈', '🥉'][i]} ${row.name} · ${formatDuration(row.seconds)}`)],
  }),
};

/** Whether a slide can be shared as a picture (the goodbye and the empty one say nothing worth it). */
export const canShare = (slide) => slide.kind in CARDS;

/** The card of a slide: { theme, kicker, title, lines, covers (urls, or null for a game without cover), footer }. */
export function shareCard(slide, footer) {
  const card = CARDS[slide.kind](slide);
  return { theme: slide.theme, covers: [], ...card, footer };
}

export const SHARE_FILENAME = (slide, period) => `laviciacion-${period}-${slide.id}.png`;
