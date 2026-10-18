import assert from 'node:assert/strict';
import { test } from 'node:test';
import { bigDuration, buildSlides, favoriteDayPart, favoriteWeekday, monthGrid, parseStoryHash, storyHref } from '../js/lib/story.js';

const HOUR = 3600;

const PLAYER = {
  name: 'Ana', seconds: 10 * HOUR, previous_seconds: 4 * HOUR, sessions: 5, days: 4, games: 3, best_day: '2026-09-10', best_day_seconds: 4 * HOUR,
  best_streak: 3, longest_session: 3 * HOUR, position: 1, star_game: { id: 'a', name: 'A', image_url: null, seconds: 5 * HOUR },
  top_games: [{ id: 'a', name: 'A', image_url: null, seconds: 5 * HOUR }, { id: 'b', name: 'B', image_url: null, seconds: 2 * HOUR }],
  by_weekday: [0, 0, 0, 6 * HOUR, 4 * HOUR, 0, 0], by_hour: Array.from({ length: 24 }, (_, h) => (h === 21 ? 7 * HOUR : h === 14 ? 3 * HOUR : 0)),
  by_day: { '2026-09-10': 4 * HOUR, '2026-09-11': 2 * HOUR }, genres: [{ genre: 'RPG', seconds: 6 * HOUR }, { genre: 'Action', seconds: 4 * HOUR }],
  games_started: 1, games_completed: 1, achievements: 2, rarest_achievement: { title: 'X', holders: 1 }, playmate: { name: 'Biel', seconds: HOUR },
};
const GROUP = { seconds: 30 * HOUR, previous_seconds: 20 * HOUR, players: 3, ranking: [{ name: 'Ana', seconds: 10 * HOUR }, { name: 'Biel', seconds: 8 * HOUR }, { name: 'Cris', seconds: 7 * HOUR }, { name: 'Dani', seconds: HOUR }], top_games: [{ name: 'A', seconds: 12 * HOUR }] };
const DATA = { period: '2026-09', player: PLAYER, group: GROUP };

test('the favourite weekday is the one with the most time, the earliest on a tie', () => {
  assert.deepEqual(favoriteWeekday([0, 0, 0, 6, 4, 0, 0]), { index: 3, name: 'jueves', seconds: 6, share: 0.6 });
  assert.equal(favoriteWeekday([2, 0, 0, 0, 0, 0, 2]).name, 'lunes');
  assert.equal(favoriteWeekday([0, 0, 0, 0, 0, 0, 0]), null);
  assert.equal(favoriteWeekday(undefined), null);
});

test('the part of the day adds the hours of each part', () => {
  const byHour = Array(24).fill(0);
  byHour[21] = 7;
  byHour[22] = 1;
  byHour[14] = 2;
  const part = favoriteDayPart(byHour);
  assert.equal(part.key, 'evening');
  assert.equal(part.title, 'Ave nocturna');
  assert.equal(part.seconds, 8);
  assert.equal(part.share, 0.8);
  assert.deepEqual(part.parts.map((p) => [p.key, p.seconds]), [['night', 0], ['morning', 0], ['afternoon', 2], ['evening', 8]]);
  assert.equal(favoriteDayPart(Array(24).fill(0)), null);
});

test('the midnight hour belongs to the madrugada and 20:00 to the night', () => {
  const at = (hour) => favoriteDayPart(Object.assign(Array(24).fill(0), { [hour]: 1 })).key;
  assert.deepEqual([0, 5, 6, 11, 12, 19, 20, 23].map(at), ['night', 'night', 'morning', 'morning', 'afternoon', 'afternoon', 'evening', 'evening']);
});

test('the month grid has the weeks Monday first and a level by the busiest day', () => {
  const grid = monthGrid('2026-09', { '2026-09-10': 4 * HOUR, '2026-09-11': 2 * HOUR, '2026-09-12': 1 });
  assert.equal(grid.every((week) => week.length === 7), true);
  const cells = grid.flat().filter(Boolean);
  assert.equal(cells.length, 30);
  const level = (day) => cells.find((c) => c.day === day).level;
  assert.deepEqual([level('2026-09-10'), level('2026-09-11'), level('2026-09-12'), level('2026-09-13')], [4, 2, 1, 0]);
  assert.equal(grid[0][0], null); // September 2026 starts on a Tuesday
  assert.equal(grid[0][1].day, '2026-09-01');
});

test('a full month tells the whole story in order and ends with the group and the goodbye', () => {
  const slides = buildSlides(DATA);
  assert.deepEqual(slides.map((s) => s.kind), ['intro', 'hours', 'star', 'topgames', 'bestday', 'weekday', 'daypart', 'genres', 'streak', 'playmate', 'milestones', 'group', 'outro']);
  assert.equal(new Set(slides.map((s) => s.id)).size, slides.length);
  const hours = slides.find((s) => s.kind === 'hours');
  assert.deepEqual(hours.change, { text: '+6 h', trend: 'up' });
  assert.equal(hours.previousLabel, 'agosto de 2026');
  assert.equal(slides.find((s) => s.kind === 'star').sharePercent, '50 %');
  assert.equal(slides.find((s) => s.kind === 'bestday').grid.length, 5);
  assert.deepEqual(slides.find((s) => s.kind === 'group').podium.map((r) => r.name), ['Ana', 'Biel', 'Cris']);
  assert.equal(slides[0].label, 'septiembre de 2026');
});

test('a slide without its figures is left out', () => {
  const slides = buildSlides({ ...DATA, player: { ...PLAYER, playmate: null, genres: [], by_hour: undefined, best_streak: 1, longest_session: 0, top_games: [], games_started: 0, games_completed: 0, achievements: 0 } });
  assert.deepEqual(slides.map((s) => s.kind), ['intro', 'hours', 'star', 'bestday', 'weekday', 'group', 'outro']);
});

test('a season has no day grid', () => {
  const slides = buildSlides({ ...DATA, period: '2026' });
  assert.equal(slides.find((s) => s.kind === 'bestday').grid, null);
  assert.equal(slides[0].label, 'temporada 2026');
});

test('a player who did not play gets an empty slide, and the group still shows if somebody did', () => {
  const none = { ...PLAYER, seconds: 0 };
  assert.deepEqual(buildSlides({ ...DATA, player: none }).map((s) => s.kind), ['empty', 'group']);
  assert.deepEqual(buildSlides({ ...DATA, player: none, group: { ...GROUP, seconds: 0 } }).map((s) => s.kind), ['empty']);
});

test('the address goes there and back', () => {
  assert.equal(storyHref('2026-09'), '#/story/2026-09');
  assert.equal(storyHref('2026-09', 'a b'), '#/story/2026-09/a%20b');
  assert.deepEqual(parseStoryHash('#/story/2026-09/a%20b'), { period: '2026-09', username: 'a b' });
  assert.deepEqual(parseStoryHash('#/story'), { period: null, username: null });
  assert.deepEqual(parseStoryHash('#/story/2026-13'), { period: null, username: null });
});

test('a time is a big figure in hours, or in minutes under an hour, never zero', () => {
  assert.deepEqual(bigDuration(61 * HOUR), { value: 61, unit: 'horas' });
  assert.deepEqual(bigDuration(HOUR), { value: 1, unit: 'hora' });
  assert.deepEqual(bigDuration(40 * 60), { value: 40, unit: 'minutos' });
  assert.deepEqual(bigDuration(20), { value: 1, unit: 'minuto' });
});

test('a recap still running is marked on the introduction', () => {
  assert.equal(buildSlides({ ...DATA, complete: false })[0].partial, true);
  assert.equal(buildSlides({ ...DATA, complete: true })[0].partial, false);
  assert.equal(buildSlides(DATA)[0].partial, false);
});
