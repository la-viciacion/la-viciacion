import assert from 'node:assert/strict';
import { test } from 'node:test';
import { SHARE_FILENAME, THEMES, canShare, shareCard } from '../js/lib/story-share.js';
import { buildSlides } from '../js/lib/story.js';

const HOUR = 3600;
const PLAYER = {
  name: 'Ana', seconds: 61 * HOUR, previous_seconds: 40 * HOUR, sessions: 24, days: 19, games: 5, best_day: '2026-09-19', best_day_seconds: 9 * HOUR,
  best_streak: 8, longest_session: 5 * HOUR, position: 1, star_game: { id: 'a', name: 'Hades II', image_url: 'https://img/a.png', seconds: 30 * HOUR },
  top_games: [{ id: 'a', name: 'Hades II', image_url: 'https://img/a.png', seconds: 30 * HOUR }, { id: 'b', name: 'Balatro', image_url: null, seconds: 10 * HOUR }],
  by_weekday: [0, 0, 0, 0, 0, 0, 5 * HOUR], by_hour: Array.from({ length: 24 }, (_, h) => (h === 22 ? HOUR : 0)),
  by_day: { '2026-09-19': 9 * HOUR }, genres: [{ genre: 'RPG', seconds: 40 * HOUR }], games_started: 2, games_completed: 1, achievements: 3,
  rarest_achievement: { title: 'Noctámbulo', holders: 1 }, playmate: { name: 'Marta', seconds: 11 * HOUR },
};
const GROUP = { seconds: 142 * HOUR, previous_seconds: 118 * HOUR, players: 3, ranking: [{ name: 'Ana', seconds: 61 * HOUR }, { name: 'Marta', seconds: 44 * HOUR }], top_games: [{ name: 'Hades II', seconds: 48 * HOUR }] };
const slides = buildSlides({ period: '2026-09', player: PLAYER, group: GROUP });
const slide = (kind) => slides.find((s) => s.kind === kind);

test('every slide that says something has a card with a kicker, and the goodbye does not', () => {
  for (const s of slides) {
    if (s.kind === 'outro') {
      assert.equal(canShare(s), false);
      continue;
    }
    assert.equal(canShare(s), true, s.kind);
    const card = shareCard(s, 'septiembre de 2026 · La Viciación');
    assert.ok(card.kicker, s.kind);
    assert.ok(card.title || card.lines.length, s.kind);
    assert.ok(THEMES[card.theme], s.kind);
    assert.equal(card.footer, 'septiembre de 2026 · La Viciación');
  }
});

test('the card talks in the first person', () => {
  assert.equal(shareCard(slide('hours'), 'f').kicker, 'He jugado');
  assert.equal(shareCard(slide('hours'), 'f').title, '61 horas');
  assert.match(shareCard(slide('star'), 'f').kicker, /^Mi juego estrella/);
  assert.deepEqual(shareCard(slide('intro'), 'f').lines, ['Así fue mi mes en La Viciación']);
});

test('the covers go with the slides that show games', () => {
  assert.deepEqual(shareCard(slide('star'), 'f').covers, ['https://img/a.png']);
  assert.deepEqual(shareCard(slide('topgames'), 'f').covers, ['https://img/a.png', null]);
  assert.deepEqual(shareCard(slide('topgames'), 'f').lines, ['1. Hades II · 30 h', '2. Balatro · 10 h']);
  assert.deepEqual(shareCard(slide('hours'), 'f').covers, []);
});

test('the group and the hours say how they moved', () => {
  assert.match(shareCard(slide('hours'), 'f').lines[0], /^\+21 h frente a agosto de 2026/);
  assert.deepEqual(shareCard(slide('group'), 'f').lines.slice(1), ['🥇 Ana · 61 h', '🥈 Marta · 44 h']);
});

test('the file has the period and the slide in its name', () => {
  assert.equal(SHARE_FILENAME({ id: 'topgames' }, '2026-09'), 'laviciacion-2026-09-topgames.png');
});
