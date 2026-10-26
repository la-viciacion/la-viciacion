import assert from 'node:assert/strict';
import { test } from 'node:test';
import { installApi as install, installDom, installStorage, json, settle, text } from './dom.js';

installStorage();
const window = installDom('<main id="main"></main>', 'http://localhost/');
globalThis.location = window.location;
globalThis.history = window.history;
const recap = await import('../js/pages/recap/index.js');

// the page asks first whether the period can be chosen; the tests look at the recap requests
const installApi = (routes, selectable = true) => install({ 'GET /statistics/recap-access': { selectable }, ...routes });
const first = (calls) => calls.find((call) => call.path.startsWith('/statistics/recap/'));
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
  assert.equal(first(calls).path, '/statistics/recap/2026-09?username=ana');
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
  assert.equal(first(calls).path, '/statistics/recap/2026-09?username=ana');
  window.location.hash = '#/recap/2026-09/biel';
  await recap.render({ user: { ...ME, is_admin: true }, main: main() });
  await settle();
  assert.equal(calls.at(-1).path, '/statistics/recap/2026-09?username=biel&unrestricted=true');
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

test('annual opens the season of a finished year, without a month, and monthly goes back to the last month of it', async () => {
  const pastYear = new Date().getFullYear() - 1; // never the running year, whatever day this runs on
  window.location.hash = `#/recap/${pastYear}-09`;
  const calls = installApi({
    [`GET /statistics/recap/${pastYear}-09?`]: DATA,
    [`GET /statistics/recap/${pastYear}?`]: { ...DATA, period: String(pastYear), kind: 'year' },
  });
  await recap.render({ user: ME, main: main() });
  await settle();
  const kind = document.getElementById('rcKind');
  kind.value = 'year';
  kind.dispatchEvent(new window.Event('change', { bubbles: true }));
  await settle();
  assert.equal(calls.at(-1).path, `/statistics/recap/${pastYear}?username=ana`);
  assert.equal(window.location.hash, `#/recap/${pastYear}`);
  assert.equal(document.getElementById('rcMonth'), null);
  assert.match(main().textContent, new RegExp(`frente a temporada ${pastYear - 1}`));
});

test('an address naming the running season still opens it as annual (the December group notice links to it)', async () => {
  const year = new Date().getFullYear();
  window.location.hash = `#/recap/${year}`;
  const calls = installApi({ [`GET /statistics/recap/${year}?`]: { ...DATA, period: String(year), kind: 'year', complete: false } });
  await recap.render({ user: ME, main: main() });
  await settle();
  assert.equal(first(calls).path, `/statistics/recap/${year}?username=ana`);
  assert.equal(document.getElementById('rcKind').value, 'year');
  assert.equal(document.getElementById('rcMonth'), null);
  assert.match(main().textContent, /todavía no ha terminado/);
});

test('the running season is not among the years the Anual select offers', async () => {
  const pastYear = new Date().getFullYear() - 1;
  window.location.hash = `#/recap/${pastYear}-09`;
  installApi({
    [`GET /statistics/recap/${pastYear}-09?`]: DATA,
    [`GET /statistics/recap/${pastYear}?`]: { ...DATA, period: String(pastYear), kind: 'year' },
  });
  await recap.render({ user: ME, main: main() });
  await settle();
  document.getElementById('rcKind').value = 'year';
  document.getElementById('rcKind').dispatchEvent(new window.Event('change', { bubbles: true }));
  await settle();
  const years = [...document.querySelectorAll('#rcYear option')].map((o) => o.value);
  assert.equal(years.includes(String(new Date().getFullYear())), false);
});

test('switching to Anual while on a month of the running year falls back to the season before, not the running one', async () => {
  const now = new Date();
  const runningYear = now.getFullYear();
  // the last finished month and the year it belongs to (December of the year before, if today is January)
  const monthYear = now.getMonth() === 0 ? runningYear - 1 : runningYear;
  const month = now.getMonth() === 0 ? 12 : now.getMonth();
  const expectedYear = monthYear === runningYear ? runningYear - 1 : monthYear; // Anual never lands on the running year
  window.location.hash = `#/recap/${monthYear}-${String(month).padStart(2, '0')}`;
  const calls = installApi({
    [`GET /statistics/recap/${monthYear}-${String(month).padStart(2, '0')}?`]: DATA,
    [`GET /statistics/recap/${expectedYear}?`]: { ...DATA, period: String(expectedYear), kind: 'year' },
  });
  await recap.render({ user: ME, main: main() });
  await settle();
  document.getElementById('rcKind').value = 'year';
  document.getElementById('rcKind').dispatchEvent(new window.Event('change', { bubbles: true }));
  await settle();
  assert.equal(calls.at(-1).path, `/statistics/recap/${expectedYear}?username=ana`);
  assert.equal(document.getElementById('rcYear').value, String(expectedYear));
});

test('a period that does not exist yet is moved to one that does', async () => {
  const future = `${new Date().getFullYear() + 1}-03`;
  window.location.hash = `#/recap/${future}`;
  const calls = installApi({ 'GET /statistics/recap/': DATA });
  await recap.render({ user: ME, main: main() });
  await settle();
  assert.equal(first(calls).path.includes(String(new Date().getFullYear() + 1)), false);
  // the running year, unless today is in January: March has not happened yet there either, so it falls back further
  const year = new Date().getMonth() === 0 ? new Date().getFullYear() - 1 : new Date().getFullYear();
  assert.equal(document.getElementById('rcYear').value, String(year));
});

test('without an address the recap is the one of the month that has just ended, and with one it is that one', async () => {
  const month = new Date().getMonth();
  const last = `${month === 0 ? new Date().getFullYear() - 1 : new Date().getFullYear()}-${String(month === 0 ? 12 : month).padStart(2, '0')}`;
  window.location.hash = '#/recap';
  let calls = installApi({ 'GET /statistics/recap/': DATA });
  await recap.render({ user: ME, main: main() });
  await settle();
  assert.equal(first(calls).path, `/statistics/recap/${last}?username=ana`);
  assert.equal(window.location.hash, '#/recap', 'the address stays as it was: the month is the default, not a choice');
  window.location.hash = '#/recap/2025-03';
  calls = installApi({ 'GET /statistics/recap/': DATA });
  await recap.render({ user: ME, main: main() });
  await settle();
  assert.equal(first(calls).path, '/statistics/recap/2025-03?username=ana');
  assert.equal(window.location.hash, '#/recap/2025-03');
});

test('the running month cannot be seen: an address naming it falls back to the one before, in the address too', async () => {
  const month = new Date().getMonth();
  const running = `${new Date().getFullYear()}-${String(month + 1).padStart(2, '0')}`;
  const last = `${month === 0 ? new Date().getFullYear() - 1 : new Date().getFullYear()}-${String(month === 0 ? 12 : month).padStart(2, '0')}`;
  window.location.hash = `#/recap/${running}`;
  const calls = installApi({ 'GET /statistics/recap/': DATA });
  await recap.render({ user: ME, main: main() });
  await settle();
  assert.equal(first(calls).path, `/statistics/recap/${last}?username=ana`);
  assert.equal(window.location.hash, `#/recap/${last}`);
});

test('choosing a period on the page is what puts it in the address', async () => {
  window.location.hash = '#/recap';
  installApi({ 'GET /statistics/recap/': DATA });
  await recap.render({ user: ME, main: main() });
  await settle();
  assert.equal(window.location.hash, '#/recap');
  const kind = document.getElementById('rcKind');
  kind.value = 'year';
  kind.dispatchEvent(new window.Event('change', { bubbles: true }));
  await settle();
  assert.equal(window.location.hash, `#/recap/${document.getElementById('rcYear').value}`);
});

test('a player without the recaps open sees the one on offer and no way to change it', async () => {
  window.location.hash = '#/recap/2026-09';
  installApi({ 'GET /statistics/recap/2026-09?': DATA }, false);
  await recap.render({ user: ME, main: main() });
  await settle();
  assert.equal(document.querySelector('.rc-picker'), null);
  assert.match(main().querySelector('#rcBody').textContent, /Has jugado/);
});

test('an admin who names themselves keeps the address and the unrestricted request across the page and the story', async () => {
  window.location.hash = '#/recap/2026-09/ana';
  const calls = installApi({ 'GET /statistics/recap/2026-09?': DATA }, false);
  await recap.render({ user: { ...ME, is_admin: true }, main: main() });
  await settle();
  assert.equal(first(calls).path, '/statistics/recap/2026-09?username=ana&unrestricted=true');
  assert.ok(document.querySelector('.rc-picker'), 'the pickers of the panel links are there');
  assert.equal(document.getElementById('rcStory').getAttribute('href'), '#/story/2026-09/ana');
  assert.equal(window.location.hash, '#/recap/2026-09/ana');
});
