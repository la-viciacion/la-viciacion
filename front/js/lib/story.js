// The recap as a story (#/story/<period>): the slides, built from what GET /statistics/recap/{period} answers.
// Pure: no DOM, so it can be tested. A slide is { id, kind, theme, ...what it shows }; pages/story/ draws each kind.
// A slide whose figures are missing is left out, so a quiet month or an older answer gives a shorter story.
import { monthWeeks } from './calendar.js';
import { formatDuration } from './format.js';
import { change, isMonth, periodLabel, previousPeriod } from './recap.js';

export const WEEKDAYS = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo'];

// The parts of the day, by the hour a session started in
export const DAY_PARTS = [
  { key: 'night', label: 'madrugada', title: 'Alma de la madrugada', emoji: '🌙', from: 0, to: 6 },
  { key: 'morning', label: 'mañana', title: 'Jugador de mañanas', emoji: '☀️', from: 6, to: 12 },
  { key: 'afternoon', label: 'tarde', title: 'Jugador de tardes', emoji: '🌇', from: 12, to: 20 },
  { key: 'evening', label: 'noche', title: 'Ave nocturna', emoji: '🦉', from: 20, to: 24 },
];

const sum = (values) => values.reduce((a, b) => a + b, 0);

/** The weekday with the most time: { index, name, seconds, share (0-1) }; null when nothing was played. */
export function favoriteWeekday(byWeekday) {
  const total = sum(byWeekday || []);
  if (!total) return null;
  const seconds = Math.max(...byWeekday);
  const index = byWeekday.indexOf(seconds); // the earliest weekday wins a tie
  return { index, name: WEEKDAYS[index], seconds, share: seconds / total };
}

/** The part of the day with the most time: { ...DAY_PARTS entry, seconds, share, parts: [{ key, label, seconds }] }; null when nothing. */
export function favoriteDayPart(byHour) {
  const total = sum(byHour || []);
  if (!total) return null;
  const parts = DAY_PARTS.map((part) => ({ key: part.key, label: part.label, seconds: sum(byHour.slice(part.from, part.to)) }));
  const best = parts.reduce((top, part) => (part.seconds > top.seconds ? part : top));
  return { ...DAY_PARTS.find((part) => part.key === best.key), seconds: best.seconds, share: best.seconds / total, parts };
}

/** The month as weeks of cells { day, seconds, level (0-4, by the share of the busiest day) } or null outside the month. */
export function monthGrid(period, byDay) {
  const max = Math.max(0, ...Object.values(byDay || {}));
  const level = (seconds) => (!seconds ? 0 : Math.max(1, Math.ceil((seconds / max) * 4)));
  return monthWeeks(period).map((week) => week.map((day) => (day ? { day, seconds: (byDay || {})[day] || 0, level: level((byDay || {})[day]) } : null)));
}

const percent = (share) => `${Math.round(share * 100)} %`;

function playerSlides(period, p) {
  const total = p.seconds;
  const slides = [
    { id: 'intro', kind: 'intro', theme: 'teal', label: periodLabel(period), name: p.name },
    {
      id: 'hours', kind: 'hours', theme: 'gold', seconds: total, previous: p.previous_seconds,
      previousLabel: periodLabel(previousPeriod(period)), change: change(total, p.previous_seconds, formatDuration), position: p.position,
      sessions: p.sessions, days: p.days,
    },
  ];
  if (p.star_game) {
    slides.push({ id: 'star', kind: 'star', theme: 'purple', game: p.star_game, share: p.star_game.seconds / total, sharePercent: percent(p.star_game.seconds / total) });
  }
  if (p.top_games?.length) slides.push({ id: 'topgames', kind: 'topgames', theme: 'pink', games: p.top_games });
  if (p.best_day) {
    const grid = isMonth(period) && p.by_day ? monthGrid(period, p.by_day) : null;
    slides.push({ id: 'bestday', kind: 'bestday', theme: 'teal', day: p.best_day, seconds: p.best_day_seconds, grid });
  }
  const weekday = favoriteWeekday(p.by_weekday);
  if (weekday) slides.push({ id: 'weekday', kind: 'weekday', theme: 'gold', favorite: weekday, byWeekday: p.by_weekday, weekdays: WEEKDAYS });
  const dayPart = favoriteDayPart(p.by_hour);
  if (dayPart) slides.push({ id: 'daypart', kind: 'daypart', theme: 'night', favorite: dayPart });
  if (p.genres?.length) slides.push({ id: 'genres', kind: 'genres', theme: 'purple', genres: p.genres, total: sum(p.genres.map((g) => g.seconds)) });
  if (p.best_streak > 1 || p.longest_session) {
    slides.push({ id: 'streak', kind: 'streak', theme: 'pink', streak: p.best_streak, longest: p.longest_session });
  }
  if (p.playmate) slides.push({ id: 'playmate', kind: 'playmate', theme: 'teal', playmate: p.playmate });
  if (p.games_started || p.games_completed || p.achievements) {
    slides.push({
      id: 'milestones', kind: 'milestones', theme: 'gold', started: p.games_started, completed: p.games_completed,
      achievements: p.achievements, rarest: p.rarest_achievement,
    });
  }
  return slides;
}

function groupSlide(period, g) {
  return {
    id: 'group', kind: 'group', theme: 'purple', seconds: g.seconds, previous: g.previous_seconds, change: change(g.seconds, g.previous_seconds, formatDuration),
    players: g.players, podium: g.ranking.slice(0, 3), game: g.top_games[0] || null,
  };
}

/** The story of a recap answer: the player's slides, the group's and the closing one. */
export function buildSlides(data) {
  const period = data.period;
  if (!data.player?.seconds) {
    return [{ id: 'empty', kind: 'empty', theme: 'night', label: periodLabel(period), group: data.group.seconds > 0 }, ...(data.group.seconds ? [groupSlide(period, data.group)] : [])];
  }
  return [...playerSlides(period, data.player), ...(data.group.seconds ? [groupSlide(period, data.group)] : []), { id: 'outro', kind: 'outro', theme: 'teal', label: periodLabel(period), name: data.player.name }];
}

/** The address of a story; an admin can look at another player's with `username`. */
export const storyHref = (period, username) => `#/story/${period}${username ? `/${encodeURIComponent(username)}` : ''}`;

/** What an address asks for: { period, username }; the period is null when it names none (or a wrong one). */
export function parseStoryHash(hash) {
  const match = /^#\/story(?:\/(\d{4}(?:-(?:0[1-9]|1[0-2]))?)(?:\/([^/]+))?)?\/?$/.exec(hash || '');
  return { period: match?.[1] ?? null, username: match?.[2] ? decodeURIComponent(match[2]) : null };
}
