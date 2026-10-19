import assert from 'node:assert/strict';
import { test } from 'node:test';
import { installApi, installDom, installStorage, json, settle, text } from './dom.js';

installStorage();
const window = installDom('<main id="main"></main>', 'http://localhost/');
globalThis.location = window.location;
globalThis.history = window.history;
const recap = await import('../js/pages/recap/index.js');

const main = () => document.getElementById('main');
const HOUR = 3600;
const ME = { id: 1, username: 'ana', is_admin: false };
const DATA = {
  period: '2026-09',
  kind: 'month',
  start: '2026-09-01',
  end: '2026-09-30',
  complete: true,
  group: {
    seconds: 5 * HOUR, previous_seconds: 3 * HOUR, sessions: 3, players: 2, busiest_day: '2026-09-10', busiest_day_seconds: 4 * HOUR,
    top_games: [{ game_id: 'doom', id: 'doom', name: 'Doom <b>', image_url: null, seconds: 4 * HOUR, players: 2 }],
    ranking: [{ user_id: 1, name: 'Ana', seconds: 4 * HOUR, previous_seconds: 5 * HOUR }, { user_id: 2, name: 'Biel', seconds: HOUR, previous_seconds: 0 }],
    achievements: 2, rarest_achievement: { title: 'Común', holders: 2, date: '2026-09-12' },
  },
  player: {
    user_id: 1, name: 'Ana', seconds: 4 * HOUR, previous_seconds: 5 * HOUR, sessions: 2, days: 2, games: 2, best_day: '2026-09-10', best_day_seconds: 3 * HOUR,
    best_streak: 2, longest_session: 3 * HOUR, position: 1, star_game: { id: 'doom', name: 'Doom', image_url: null, seconds: 3 * HOUR },
    games_started: 1, games_completed: 1, achievements: 2, rarest_achievement: { title: 'Oculto', holders: 1, date: '2026-09-13' },
    playmate: { user_id: 2, name: 'Biel', seconds: HOUR },
  },
};

test('it opens on the asked month and tells the player their figures against the month before', async () => {
  window.location.hash = '#/recap/2026-09';
  const calls = installApi({ 'GET /statistics/recap/2026-09?username=ana': DATA });
  await recap.render({ user: ME, main: main() });
  await settle();
  assert.equal(calls[0].path, '/statistics/recap/2026-09?username=ana');
  const body = main().querySelector('#rcBody').textContent;
  assert.match(body, /Has jugado/);
  assert.match(body, /4 h/);
  assert.match(body, /frente a agosto de 2026/);
  assert.match(body, /Puesto 1º/);
  assert.match(body, /Juego estrella/);
  assert.match(body, /Biel/);
  assert.match(body, /solo lo tienes tú/);
  assert.notEqual(main().querySelector('.rc-trend.down'), null);
});

test('the group tab has the ranking and the games, escaped', async () => {
  window.location.hash = '#/recap/2026-09';
  installApi({ 'GET /statistics/recap/2026-09?username=ana': DATA });
  await recap.render({ user: ME, main: main() });
  await settle();
  document.querySelector('[data-view="group"]').click();
  assert.deepEqual(text('#rcRanking .pf-bar-label > span:first-child'), ['🥇 Ana', '🥈 Biel']);
  assert.deepEqual(text('#rcGames .rc-name'), ['Doom <b>']);
  assert.equal(document.querySelectorAll('#rcGames b').length, 0);
});

test('choosing another period asks for it and keeps the address', async () => {
  window.location.hash = '#/recap/2026-09';
  const calls = installApi({
    'GET /statistics/recap/2026-09?': DATA,
    'GET /statistics/recap/2026-08?': { ...DATA, period: '2026-08', player: { ...DATA.player, seconds: 0 } },
  });
  await recap.render({ user: ME, main: main() });
  await settle();
  const select = document.getElementById('rcMonth');
  select.value = '8';
  select.dispatchEvent(new window.Event('change', { bubbles: true }));
  await settle();
  assert.equal(calls.at(-1).path, '/statistics/recap/2026-08?username=ana');
  assert.equal(window.location.hash, '#/recap/2026-08');
  assert.match(main().querySelector('#rcBody').textContent, /No se jugó nada en agosto de 2026/);
});

test('a period still running says so', async () => {
  window.location.hash = '#/recap/2026-09';
  installApi({ 'GET /statistics/recap/2026-09?': { ...DATA, complete: false } });
  await recap.render({ user: ME, main: main() });
  await settle();
  assert.match(main().textContent, /todavía no ha terminado/);
});

test('only an admin can look at another player', async () => {
  window.location.hash = '#/recap/2026-09/biel';
  const calls = installApi({ 'GET /statistics/recap/2026-09?': DATA });
  await recap.render({ user: ME, main: main() });
  await settle();
  assert.equal(calls[0].path, '/statistics/recap/2026-09?username=ana');
  window.location.hash = '#/recap/2026-09/biel';
  await recap.render({ user: { ...ME, is_admin: true }, main: main() });
  await settle();
  assert.equal(calls.at(-1).path, '/statistics/recap/2026-09?username=biel');
  assert.match(main().querySelector('[data-view="player"]').textContent, /biel/);
  assert.match(main().textContent, /Ha jugado/);
});

test('an error is shown instead of the recap', async () => {
  window.location.hash = '#/recap/2026-09';
  installApi({ 'GET /statistics/recap/2026-09?': json({ detail: 'boom' }, 500) });
  await recap.render({ user: ME, main: main() });
  await settle();
  assert.match(main().textContent, /boom/);
});

test('the period is chosen as monthly or annual, a year and a month, not from one long list', async () => {
  window.location.hash = '#/recap/2026-09';
  installApi({ 'GET /statistics/recap/2026-09?': DATA });
  await recap.render({ user: ME, main: main() });
  await settle();
  assert.equal(document.getElementById('rcPeriod'), null);
  assert.equal(document.getElementById('rcKind').value, 'month');
  assert.equal(document.getElementById('rcYear').value, '2026');
  assert.equal(document.getElementById('rcMonth').value, '9');
  assert.equal(document.querySelectorAll('#rcYear option').length, new Date().getFullYear() - 2023 + 1);
});

test('annual opens the season of the year, without a month, and monthly goes back to the last month of it', async () => {
  window.location.hash = '#/recap/2026-09';
  const calls = installApi({
    'GET /statistics/recap/2026-09?': DATA,
    'GET /statistics/recap/2026?': { ...DATA, period: '2026', kind: 'year' },
  });
  await recap.render({ user: ME, main: main() });
  await settle();
  const kind = document.getElementById('rcKind');
  kind.value = 'year';
  kind.dispatchEvent(new window.Event('change', { bubbles: true }));
  await settle();
  assert.equal(calls.at(-1).path, '/statistics/recap/2026?username=ana');
  assert.equal(window.location.hash, '#/recap/2026');
  assert.equal(document.getElementById('rcMonth'), null);
  assert.match(main().textContent, /frente a temporada 2025/);
});

test('an address with a season opens it as annual', async () => {
  window.location.hash = '#/recap/2026';
  const calls = installApi({ 'GET /statistics/recap/2026?': { ...DATA, period: '2026', kind: 'year' } });
  await recap.render({ user: ME, main: main() });
  await settle();
  assert.equal(calls[0].path, '/statistics/recap/2026?username=ana');
  assert.equal(document.getElementById('rcKind').value, 'year');
  assert.equal(document.getElementById('rcMonth'), null);
});

test('a period that does not exist yet is moved to one that does', async () => {
  const future = `${new Date().getFullYear() + 1}-03`;
  window.location.hash = `#/recap/${future}`;
  const calls = installApi({ 'GET /statistics/recap/': DATA });
  await recap.render({ user: ME, main: main() });
  await settle();
  assert.equal(calls[0].path.includes(String(new Date().getFullYear() + 1)), false);
  assert.equal(document.getElementById('rcYear').value, String(new Date().getFullYear()));
});

test('without an address the recap is the one of the month that has just ended, and with one it is that one', async () => {
  const month = new Date().getMonth();
  const last = `${month === 0 ? new Date().getFullYear() - 1 : new Date().getFullYear()}-${String(month === 0 ? 12 : month).padStart(2, '0')}`;
  window.location.hash = '#/recap';
  let calls = installApi({ 'GET /statistics/recap/': DATA });
  await recap.render({ user: ME, main: main() });
  await settle();
  assert.equal(calls[0].path, `/statistics/recap/${last}?username=ana`);
  assert.equal(window.location.hash, `#/recap/${last}`, 'the address says which month it is');
  window.location.hash = '#/recap/2025-03';
  calls = installApi({ 'GET /statistics/recap/': DATA });
  await recap.render({ user: ME, main: main() });
  await settle();
  assert.equal(calls[0].path, '/statistics/recap/2025-03?username=ana');
});
