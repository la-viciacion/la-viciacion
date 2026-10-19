import assert from 'node:assert/strict';
import { test } from 'node:test';
import { installApi, installDom, installStorage, json, settle } from './dom.js';

installStorage();
const window = installDom('<main id="main"></main>', 'http://localhost/');
globalThis.location = window.location;
globalThis.history = window.history;
const story = await import('../js/pages/story/index.js');
const { buildSlides } = await import('../js/lib/story.js');
const { animateCounts, renderSlide } = await import('../js/ui/story-slides.js');
const { html, mount } = await import('../js/lib/html.js');

const main = () => document.getElementById('main');
const HOUR = 3600;
const ME = { id: 1, username: 'ana', is_admin: false };
const PLAYER = {
  name: 'Ana <b>', seconds: 61 * HOUR, previous_seconds: 40 * HOUR, sessions: 24, days: 19, games: 5, best_day: '2026-09-19', best_day_seconds: 9 * HOUR,
  best_streak: 8, longest_session: 5 * HOUR, position: 1, star_game: { id: 'a', name: 'Hades II', image_url: 'https://img/a.png', seconds: 34 * HOUR },
  top_games: [{ id: 'a', name: 'Hades II', image_url: 'https://img/a.png', seconds: 34 * HOUR }, { id: 'b', name: 'Balatro', image_url: null, seconds: 10 * HOUR }],
  by_weekday: [HOUR, 0, 0, 20 * HOUR, 5 * HOUR, 0, 35 * HOUR], by_hour: Array.from({ length: 24 }, (_, h) => (h === 22 ? 40 * HOUR : h === 15 ? 21 * HOUR : 0)),
  by_day: { '2026-09-19': 9 * HOUR, '2026-09-20': 3 * HOUR }, genres: [{ genre: 'RPG', seconds: 40 * HOUR }, { genre: 'Action', seconds: 20 * HOUR }],
  games_started: 2, games_completed: 1, achievements: 3, rarest_achievement: { title: 'Noctámbulo', holders: 1 }, playmate: { name: 'Marta', seconds: 11 * HOUR },
};
const GROUP = {
  seconds: 142 * HOUR, previous_seconds: 118 * HOUR, players: 4, ranking: [{ name: 'Ana', seconds: 61 * HOUR }, { name: 'Marta', seconds: 44 * HOUR }, { name: 'Biel', seconds: 27 * HOUR }],
  top_games: [{ name: 'Hades II', seconds: 48 * HOUR }],
};
const DATA = { period: '2026-09', player: PLAYER, group: GROUP };

const text = () => main().querySelector('.st-slide').textContent;
const key = (k) => document.dispatchEvent(Object.assign(new window.Event('keydown', { bubbles: true }), { key: k }));

async function open(hash = '#/story/2026-09', user = ME, data = DATA) {
  window.location.hash = hash;
  const calls = installApi({ 'GET /statistics/recap/': data });
  await story.render({ user, main: main() });
  await settle();
  return calls;
}

test('it asks for the recap of the period and opens on the introduction, with the name escaped', async () => {
  const calls = await open();
  assert.equal(calls[0].path, '/statistics/recap/2026-09?username=ana');
  assert.match(text(), /septiembre de 2026/);
  assert.match(text(), /Ana <b>, así fue tu mes en La Viciación/);
  assert.equal(main().querySelectorAll('.st-slide b').length, 0);
  assert.equal(main().querySelectorAll('.st-bar').length, buildSlides(DATA).length);
  story.dispose();
});

test('the arrows go through the slides: hours, star game, top games, and back', async () => {
  await open();
  key('ArrowRight');
  assert.match(text(), /Has jugado/);
  assert.match(text(), /61/);
  assert.match(text(), /\+21 h/);
  assert.match(text(), /Puesto 1º/);
  key('ArrowRight');
  assert.match(text(), /Tu juego estrella/);
  assert.match(text(), /Hades II/);
  assert.match(text(), /56 %/);
  key('ArrowRight');
  assert.deepEqual([...main().querySelectorAll('.st-rank strong')].map((e) => e.textContent), ['Hades II', 'Balatro']);
  key('ArrowLeft');
  assert.match(text(), /Tu juego estrella/);
  story.dispose();
});

test('every kind of slide draws something and has its own colour theme', () => {
  const slides = buildSlides(DATA);
  for (const slide of slides) {
    mount(main(), html`<div>${renderSlide(slide)}</div>`);
    assert.ok(main().textContent.trim().length > 0, slide.kind);
    assert.ok(['teal', 'gold', 'purple', 'pink', 'night'].includes(slide.theme), slide.kind);
  }
  const names = slides.map((s) => s.kind);
  assert.deepEqual(names.slice(-3), ['milestones', 'group', 'outro']);
});

test('the favourite day, the part of the day and the genres are told', async () => {
  await open();
  const texts = [];
  for (let i = 0; i < buildSlides(DATA).length - 1; i += 1) {
    texts.push(text());
    key('ArrowRight');
  }
  const all = texts.join('\n');
  assert.match(all, /19 de septiembre/);
  assert.match(all, /domingo/);
  assert.match(all, /Ave nocturna/);
  assert.match(all, /RPG/);
  assert.match(all, /11 h/); // the playmate
  assert.match(all, /Marta/);
  story.dispose();
});

test('every slide but the goodbye can be shared as a picture', async () => {
  await open();
  const button = main().querySelector('.st-share');
  assert.equal(button.hidden, false);
  const total = buildSlides(DATA).length;
  for (let i = 0; i < total - 1; i += 1) key('ArrowRight');
  assert.equal(button.hidden, true);
  assert.notEqual(main().querySelector('[data-act="share"]'), null);
  story.dispose();
});

test('the last slide can start over or close, back to the recap page', async () => {
  await open();
  const total = buildSlides(DATA).length;
  for (let i = 0; i < total - 1; i += 1) key('ArrowRight');
  assert.match(text(), /Eso fue septiembre de 2026/);
  main().querySelector('[data-act="replay"]').click();
  assert.match(text(), /así fue tu mes/);
  key('Escape');
  assert.equal(window.location.hash, '#/recap/2026-09');
  story.dispose();
});

test('a player who did not play still gets a slide, and an error is shown', async () => {
  await open('#/story/2026-09', ME, { ...DATA, player: { ...PLAYER, seconds: 0 } });
  assert.match(text(), /no hay nada que contar/);
  story.dispose();
  window.location.hash = '#/story/2026-09';
  installApi({ 'GET /statistics/recap/': json({ detail: 'boom' }, 500) });
  await story.render({ user: ME, main: main() });
  await settle();
  assert.match(main().textContent, /No se ha podido cargar/);
  assert.match(main().textContent, /boom/);
  main().querySelector('[data-act="close"]').click();
  assert.equal(window.location.hash, '#/recap/2026-09');
});

test('only an admin can ask for another player', async () => {
  let calls = await open('#/story/2026-09/biel');
  assert.equal(calls[0].path, '/statistics/recap/2026-09?username=ana');
  story.dispose();
  calls = await open('#/story/2026-09/biel', { ...ME, is_admin: true });
  assert.equal(calls[0].path, '/statistics/recap/2026-09?username=biel');
  key('Escape');
  assert.equal(window.location.hash, '#/recap/2026-09/biel');
  story.dispose();
});

test('the figures count up from zero and end on their value', () => {
  mount(main(), html`<span class="st-count" data-count="61">61</span>`);
  const frames = [];
  globalThis.requestAnimationFrame = (fn) => frames.push(fn);
  let clock = 0;
  animateCounts(main(), { duration: 1000, now: () => clock });
  const el = main().querySelector('.st-count');
  assert.equal(el.textContent, '0');
  clock = 500;
  frames.shift()();
  assert.ok(Number(el.textContent) > 30 && Number(el.textContent) < 61);
  clock = 1000;
  frames.shift()();
  assert.equal(el.textContent, '61');
  delete globalThis.requestAnimationFrame;
});

test('opening your own story clears the notice of the first days of the month; looking at another player does not', async () => {
  localStorage.removeItem('lv-recap-seen-2026-09');
  await open('#/story/2026-09/biel', { ...ME, is_admin: true });
  assert.equal(localStorage.getItem('lv-recap-seen-2026-09'), null);
  story.dispose();
  await open();
  assert.equal(localStorage.getItem('lv-recap-seen-2026-09'), '1');
  story.dispose();
});

// the month that has just ended, worked out here on its own (not with the code under test)
const lastMonthKey = () => {
  const now = new Date();
  const month = now.getMonth() === 0 ? 12 : now.getMonth();
  return `${now.getMonth() === 0 ? now.getFullYear() - 1 : now.getFullYear()}-${String(month).padStart(2, '0')}`;
};

test('without an address it tells the story of the month that has just ended, and with one it tells that one', async () => {
  const last = lastMonthKey();
  for (const hash of ['#/story', '#/story/']) {
    const calls = await open(hash);
    assert.equal(calls[0].path, `/statistics/recap/${last}?username=ana`, hash);
    story.dispose();
  }
  const asked = await open('#/story/2025-03');
  assert.equal(asked[0].path, '/statistics/recap/2025-03?username=ana');
  story.dispose();
  const season = await open('#/story/2025');
  assert.equal(season[0].path, '/statistics/recap/2025?username=ana');
  story.dispose();
});

test('a story address that is not a period falls back to the last month instead of asking for nonsense', async () => {
  const calls = await open('#/story/2026-13');
  assert.equal(calls[0].path, `/statistics/recap/${lastMonthKey()}?username=ana`);
  story.dispose();
});

test('the running month cannot be told as a story: the address falls back to the one before', async () => {
  const now = new Date();
  const running = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
  const calls = await open(`#/story/${running}`);
  assert.equal(calls[0].path, `/statistics/recap/${lastMonthKey()}?username=ana`);
  story.dispose();
});
