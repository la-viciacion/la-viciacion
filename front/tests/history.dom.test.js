import assert from 'node:assert/strict';
import { before, beforeEach, test } from 'node:test';
import { installApi, installDom, installStorage, json, settle, text } from './dom.js';

installStorage();
const window = installDom('<div id="historyList"></div><div id="historyMore"></div>');
const { initHistory, loadHistory, onHistoryClick, onHistoryKey } = await import('../js/pages/home/history.js');

const GROUPS = [
  { game_id: 'celeste', game_name: 'Celeste', image_url: null, platform: 'pc', platforms: ['pc', 'switch'], last_played: '2026-03-01T20:00:00',
    total_seconds: 7200, session_count: 3, completed: true, score: 87,
    sessions: [{ id: 11, start_time: '2026-03-01T20:00:00', duration_seconds: 3600, platform: 'pc', is_active: false },
               { id: 10, start_time: '2026-02-28T20:00:00', duration_seconds: 3600, platform: 'switch', is_active: false }] },
  { game_id: 'hades', game_name: 'Hades <b>', image_url: 'https://img/h.jpg', platform: 'pc', platforms: ['pc'], last_played: '2026-02-20T20:00:00',
    total_seconds: 600, session_count: 1, completed: false, sessions: [{ id: 5, start_time: '2026-02-20T20:00:00', duration_seconds: 600, platform: 'pc', is_active: false }] },
];
const ALL_SESSIONS = [
  { id: 11, start_time: '2026-03-01T20:00:00', duration_seconds: 3600, platform: 'pc', is_active: false },
  { id: 10, start_time: '2026-02-28T20:00:00', duration_seconds: 3600, platform: 'switch', is_active: false },
  { id: 9, start_time: '2026-02-27T20:00:00', duration_seconds: 60, platform: 'pc', is_active: false },
  { id: 8, start_time: '2026-02-26T20:00:00', duration_seconds: 0, platform: 'pc', is_active: true },
];

const picked = {};
let calls;

before(() => {
  document.getElementById('historyList').addEventListener('click', onHistoryClick);
  document.getElementById('historyList').addEventListener('keydown', onHistoryKey);
  document.getElementById('historyMore').addEventListener('click', onHistoryClick);
});

beforeEach(async () => {
  for (const key of Object.keys(picked)) delete picked[key];
  calls = installApi({
    'GET /timers/history/7/grouped': { groups: GROUPS, total_games: 11 },
    'GET /timers/history/7?game_id=celeste': ALL_SESSIONS,
  });
  initHistory({ userId: 7, onContinue: (g) => (picked.continue = g), onComplete: (g) => (picked.complete = g), onEditSession: (g, s) => (picked.edit = [g, s]) });
  await loadHistory(true);
});

const click = (selector) => document.querySelector(selector).click();

test('one row per game, with the markup of a name shown as text and the "show more" counter', () => {
  assert.equal(calls[0].path, '/timers/history/7/grouped?limit=8&offset=0');
  assert.deepEqual(text('.history-name'), ['Celeste', 'Hades <b>']);
  assert.equal(document.querySelectorAll('.history-name b').length, 0);
  assert.equal(text('#historyMoreBtn')[0], 'Mostrar más (9)');
  assert.ok(document.querySelector('[data-game-id="celeste"] .btn-complete.done'));
  assert.equal(document.querySelector('[data-game-id="hades"] .btn-complete.done'), null);
  assert.match(text('[data-game-id="celeste"] .history-meta')[0], /3 sesiones/);
});

test('pressing a row unfolds its sessions and pressing it again folds them', () => {
  click('[data-game-id="celeste"] [data-action="toggle"]');
  assert.equal(document.querySelectorAll('[data-game-id="celeste"] .history-sessions li').length, 4); // two sessions, the line of the older one and the link to the game page
  assert.equal(document.querySelector('[data-game-id="celeste"] [data-action="toggle"]').getAttribute('aria-expanded'), 'true');
  click('[data-game-id="celeste"] [data-action="toggle"]');
  assert.equal(document.querySelectorAll('[data-game-id="celeste"] .history-sessions').length, 0);
});

test('Enter and Space on the focused row unfold it; other keys do not', () => {
  const press = (key) => document.querySelector('[data-game-id="hades"] [data-action="toggle"]')
    .dispatchEvent(new window.KeyboardEvent('keydown', { key, bubbles: true }));
  press('a');
  assert.equal(document.querySelectorAll('.history-group.open').length, 0);
  press('Enter');
  assert.equal(document.querySelectorAll('.history-group.open').length, 1);
  press(' ');
  assert.equal(document.querySelectorAll('.history-group.open').length, 0);
});

test('the buttons of a row call back with their game and do not unfold it', () => {
  click('[data-game-id="hades"] [data-action="continue"]');
  assert.equal(picked.continue.game_id, 'hades');
  click('[data-game-id="celeste"] [data-action="complete"]');
  assert.equal(picked.complete.game_id, 'celeste');
  assert.equal(document.querySelectorAll('.history-group.open').length, 0);
});

test('"Editar" hands over the game and the session of that row', () => {
  click('[data-game-id="celeste"] [data-action="toggle"]');
  click('[data-game-id="celeste"] [data-action="edit-session"][data-timer-id="10"]');
  assert.equal(picked.edit[0].game_id, 'celeste');
  assert.equal(picked.edit[1].id, 10);
});

test('"Ver todas" loads every session of the game and drops the one still running', async () => {
  click('[data-game-id="celeste"] [data-action="toggle"]');
  click('[data-game-id="celeste"] [data-action="all-sessions"]');
  await settle();
  assert.equal(calls.at(-1).path, '/timers/history/7?game_id=celeste&limit=500');
  assert.equal(document.querySelectorAll('[data-game-id="celeste"] .history-sessions li').length, 4); // the three finished ones and the link to the game page
  assert.equal(document.querySelector('[data-game-id="celeste"] [data-action="all-sessions"]'), null);
});

test('"show more" asks for the next page, after the games already shown', async () => {
  click('#historyMoreBtn');
  await settle();
  assert.equal(calls.at(-1).path, '/timers/history/7/grouped?limit=8&offset=2');
});

test('a user without sessions gets the invitation to start a timer', async () => {
  installApi({ 'GET /timers/history/7/grouped': { groups: [], total_games: 0 } });
  await loadHistory(true);
  assert.match(text('#historyList')[0], /Aún no tienes sesiones/);
  assert.equal(document.querySelector('#historyMoreBtn'), null);
});

test('an API failure is shown in the list instead of leaving it empty', async () => {
  installApi({ 'GET /timers/history/7/grouped': json({ detail: 'Se rompió' }, 500) });
  await loadHistory(true);
  assert.match(text('#historyList')[0], /Error cargando el historial: Se rompió/);
});

test('a rated game shows its rating next to the name, an unrated one shows none', () => {
  assert.deepEqual(text('[data-game-id="celeste"] .history-title .score-badge'), ['87']);
  assert.equal(document.querySelector('[data-game-id="celeste"] .score-badge').style.getPropertyValue('--h'), '109');
  assert.equal(document.querySelector('[data-game-id="hades"] .score-badge'), null);
});
