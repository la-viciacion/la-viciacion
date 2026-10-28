import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';
import { installApi, installDom, installStorage, json, settle, text } from './dom.js';

installStorage();
installDom('<main id="main"></main>');
const { closeAllModals } = await import('../js/ui/modal.js');
const page = await import('../js/pages/challenges/index.js');
const history = await import('../js/ui/challenges-history.js');

afterEach(() => closeAllModals());

const main = () => document.getElementById('main');
const ANA = { id: 1, username: 'ana', is_admin: false };
const ROOT = { id: 9, username: 'root', is_admin: true };
const DEBT = { seconds: 40 * 3600, games: 4, open_games: 5 };

const challenge = (extra = {}) => ({
  id: 5, kind: 'game_of_month', label: 'Juego del mes', scope: 'group', title: 'Juego del mes: Hades <b>', status: 'active',
  starts_on: '2026-10-01', ends_on: '2026-10-31', params: { min_hours_each: 5, min_hours_total: 12 },
  game: { id: 'hades', name: 'Hades', image_url: null }, owner: null, taking_part: true, can_opt_out: true,
  progress: {
    players: [
      { user_id: 1, name: 'Ana', seconds: 25200, target_seconds: 18000, done: true },
      { user_id: 2, name: 'Bea', seconds: 7200, target_seconds: 18000, done: false },
    ],
    total_seconds: 32400, total_target_seconds: 43200, total_done: false,
  },
  ...extra,
});

const personal = (extra = {}) => ({
  id: 7, kind: 'new_genre', label: 'Probar un género', scope: 'user', title: 'Probar un género: Metroidvania', status: 'active',
  starts_on: '2026-10-01', ends_on: '2026-10-30', params: { genre: 'Metroidvania', mode: 'play', duration: 'month', hours: 2 },
  game: null, owner: { id: 1, name: 'Ana' }, taking_part: true, can_opt_out: false,
  progress: { players: [{ user_id: 1, name: 'Ana', seconds: 3600, target_seconds: 7200, done: false }] },
  ...extra,
});

test('a challenge shows its players and the total, escaped, with a link to the game', async () => {
  installApi({ 'GET /challenges/proposals': [], 'GET /challenges': [challenge()] });
  await page.render({ main: main(), user: ANA });
  await settle();
  assert.equal(document.querySelectorAll('.ch-card').length, 1);
  assert.equal(document.querySelector('.ch-title a').getAttribute('href'), '#/game/hades');
  assert.equal(document.querySelectorAll('.ch-title b').length, 0);
  assert.deepEqual(text('.ch-players .ch-name'), ['Ana (tú)', 'Bea']);
  assert.equal(document.querySelectorAll('.ch-players .ch-bar.ok').length, 1); // only Ana reached her part
  assert.match(text('.ch-total')[0], /9 h \/ 12 h/);
  assert.match(main().textContent, /mínimo 5 h cada uno y 12 h entre todos/);
  assert.equal(document.querySelector('[data-delete]'), null); // a group challenge is deleted from the admin panel
});

test('the challenges are in blocks: the group\'s, the viewer\'s own and the other players\'', async () => {
  const bea = personal({ id: 8, owner: { id: 2, name: 'Bea' }, title: 'Probar un género: RPG' });
  installApi({ 'GET /challenges/proposals': [], 'GET /challenges': [challenge(), personal(), bea] });
  await page.render({ main: main(), user: ANA });
  await settle();
  assert.deepEqual(text('.section-title'), ['Del grupo', 'Tuyos', 'De otros jugadores']);
  assert.deepEqual(text('.ch-title').map((t) => t.split('\n')[0].trim().slice(0, 12)), ['Juego del me', 'Probar un gé', 'Probar un gé']);
  assert.match(text('.ch-card')[2], /Bea · /); // the owner of somebody else's
});

test('a personal challenge shows its single bar and only its owner can delete it, with a second press', async () => {
  const calls = installApi({ 'GET /challenges/proposals': [], 'GET /challenges': [personal(), personal({ id: 8, owner: { id: 2, name: 'Bea' } })], 'DELETE /challenges/7': { message: 'ok' } });
  await page.render({ main: main(), user: ANA });
  await settle();
  assert.equal(document.querySelectorAll('[data-delete]').length, 1);
  assert.match(main().textContent, /jugar 2 h a un juego de Metroidvania que no tuvieras antes/);
  assert.equal(document.querySelector('.ch-total'), null);
  assert.equal(document.querySelector('[data-part]'), null); // nobody leaves a personal one
  const button = document.querySelector('[data-delete]');
  button.click();
  assert.equal(calls.filter((c) => c.method === 'DELETE').length, 0);
  assert.match(button.textContent, /¿Seguro\?/);
  button.click();
  await settle();
  assert.deepEqual(calls.filter((c) => c.method === 'DELETE').map((c) => c.path), ['/challenges/7']);
});

test('a completion is counted in games', async () => {
  const done = personal({ params: { genre: 'RPG', mode: 'complete', duration: 'week' }, progress: { players: [{ user_id: 1, name: 'Ana', count: 1, target_count: 1, done: true }] } });
  installApi({ 'GET /challenges/proposals': [], 'GET /challenges': [done] });
  await page.render({ main: main(), user: ANA });
  await settle();
  assert.match(text('.ch-row')[0], /1 \/ 1 juego ✓/);
  assert.match(main().textContent, /completar un juego de RPG/);
  assert.equal(document.querySelectorAll('.ch-bar.ok').length, 1);
});

test('leaving and coming back asks the API about the caller only', async () => {
  const calls = installApi({ 'GET /challenges/proposals': [], 'GET /challenges': [challenge()], 'PUT /challenges/5/participation': challenge({ taking_part: false }) });
  await page.render({ main: main(), user: ANA });
  await settle();
  document.querySelector('[data-part="leave"]').click();
  await settle();
  assert.deepEqual(calls.filter((c) => c.method === 'PUT').map((c) => c.path), ['/challenges/5/participation?joined=false']);
});

test('a group challenge you left says so and offers to join again', async () => {
  installApi({ 'GET /challenges/proposals': [], 'GET /challenges': [challenge({ taking_part: false })] });
  await page.render({ main: main(), user: ANA });
  await settle();
  assert.match(main().textContent, /No participas en este reto/);
  assert.equal(document.querySelector('[data-part]').dataset.part, 'join');
  assert.equal(document.querySelector('.ch-players'), null);
});

test('not even an admin launches or deletes a group challenge from this page: that is the admin panel', async () => {
  installApi({ 'GET /challenges/proposals': [], 'GET /challenges': [challenge()] });
  await page.render({ main: main(), user: ROOT });
  await settle();
  assert.equal(document.querySelector('[data-delete]'), null);
  assert.ok(document.querySelector('[data-part]')); // but an admin takes part like anybody
});

test('the new challenge form asks for a genre, the goal and the duration, and sends them', async () => {
  const GENRES = [{ genre: 'Action', games: 3, played: true }, { genre: 'Metroidvania', games: 2, played: false }];
  const calls = installApi({ 'GET /challenges/proposals': [], 'GET /challenges/debt': DEBT, 'GET /challenges/genres': GENRES, 'GET /challenges': [], 'POST /challenges': personal() });
  await page.render({ main: main(), user: ANA });
  await settle();
  document.querySelector('#chNew').click();
  await settle();
  assert.deepEqual(text('select[name="genre"] option'), ['Action (3)', 'Metroidvania (2) · nuevo para ti']);
  const form = document.querySelector('.modal-content form');
  assert.equal(form.elements.hours.value, '2'); // the default
  assert.equal(form.elements.duration.value, 'month');
  form.elements.genre.value = 'Metroidvania';
  form.elements.mode.value = 'complete';
  form.elements.mode.dispatchEvent(new window.Event('change', { bubbles: true }));
  assert.equal(document.querySelector('[data-for="play"]').hidden, true);
  form.requestSubmit();
  await settle();
  const post = calls.find((c) => c.method === 'POST');
  assert.deepEqual(post.body, { kind: 'new_genre', options: { genre: 'Metroidvania', mode: 'complete', duration: 'month' } });
});

test('playing sends the hours', async () => {
  const calls = installApi({ 'GET /challenges/proposals': [], 'GET /challenges/debt': DEBT, 'GET /challenges/genres': [{ genre: 'RPG', games: 1, played: false }], 'GET /challenges': [], 'POST /challenges': personal() });
  await page.render({ main: main(), user: ANA });
  await settle();
  document.querySelector('#chNew').click();
  await settle();
  const form = document.querySelector('.modal-content form');
  form.elements.hours.value = '3.5';
  form.elements.duration.value = 'week';
  form.requestSubmit();
  await settle();
  assert.deepEqual(calls.find((c) => c.method === 'POST').body.options, { genre: 'RPG', mode: 'play', duration: 'week', hours: 3.5 });
});

test('an error from the API stays in the form', async () => {
  installApi({ 'GET /challenges/proposals': [], 'GET /challenges/debt': DEBT, 'GET /challenges/genres': [{ genre: 'RPG', games: 1, played: false }], 'GET /challenges': [], 'POST /challenges': json({ detail: 'Ya existe un reto igual' }, 409) });
  await page.render({ main: main(), user: ANA });
  await settle();
  document.querySelector('#chNew').click();
  await settle();
  document.querySelector('.modal-content form').requestSubmit();
  await settle();
  assert.match(document.querySelector('.adm-error').textContent, /Ya existe un reto igual/);
});

test('without challenges each block says how to get one', async () => {
  installApi({ 'GET /challenges/proposals': [], 'GET /challenges': [] });
  await page.render({ main: main(), user: ANA });
  await settle();
  assert.match(main().textContent, /No hay ningún reto del grupo/);
  assert.match(main().textContent, /No tienes ningún reto/);
});

test('an error loading is shown', async () => {
  installApi({ 'GET /challenges/proposals': [], 'GET /challenges': json({ detail: 'boom' }, 500) });
  await page.render({ main: main(), user: ANA });
  await settle();
  assert.match(main().textContent, /Error cargando los retos/);
});

test('the history of a player lists the finished challenges with how they did', async () => {
  document.body.innerHTML = '<div id="h"></div>';
  installApi({ 'GET /challenges/proposals': [], 'GET /challenges/player/1': [
    { id: 5, title: 'Juego del mes: Hades', scope: 'group', ends_on: '2026-09-30', done: true, group_done: false },
    { id: 6, title: 'Otro', scope: 'group', ends_on: '2026-08-31', done: false, group_done: false },
    { id: 7, title: 'Probar un género: RPG', scope: 'user', ends_on: '2026-08-01', done: true, group_done: null },
  ] });
  await history.showChallengesHistory(document.getElementById('h'), 1, true);
  assert.deepEqual(text('.ch-history-item strong'), ['Juego del mes: Hades', 'Otro', 'Probar un género: RPG']);
  assert.deepEqual(text('.ch-history-item .pf-tag'), ['Cumpliste tu parte', 'No se cumplió', 'Lo conseguiste']);
});

test('the empty history is worded for whose it is', async () => {
  document.body.innerHTML = '<div id="h"></div>';
  installApi({ 'GET /challenges/proposals': [], 'GET /challenges/player/1': [] });
  await history.showChallengesHistory(document.getElementById('h'), 1, true);
  assert.match(document.getElementById('h').textContent, /Todavía no has terminado ningún reto/);
  installApi({ 'GET /challenges/proposals': [], 'GET /challenges/player/2': [] });
  await history.showChallengesHistory(document.getElementById('h'), 2, false);
  assert.match(document.getElementById('h').textContent, /Todavía no ha terminado ningún reto/);
});

test('the kind of challenge decides which options show and the form starts on trying a genre', async () => {
  document.body.innerHTML = '<main id="main"></main>'; // the tests of the history above replaced it
  installApi({ 'GET /challenges/proposals': [], 'GET /challenges/debt': DEBT, 'GET /challenges/genres': [{ genre: 'RPG', games: 1, played: false }], 'GET /challenges': [] });
  await page.render({ main: main(), user: ANA });
  await settle();
  document.querySelector('#chNew').click();
  await settle();
  const form = document.querySelector('.modal-content form');
  assert.equal(form.querySelector('[data-kind="new_genre"]').hidden, false);
  assert.equal(form.querySelector('[data-kind="debt_reduction"]').hidden, true);
  form.elements.kind.value = 'debt_reduction';
  form.elements.kind.dispatchEvent(new window.Event('change', { bubbles: true }));
  assert.equal(form.querySelector('[data-kind="new_genre"]').hidden, true);
  assert.equal(form.querySelector('[data-kind="debt_reduction"]').hidden, false);
});

test('before accepting a percentage of the debt the form says how many hours it is', async () => {
  document.body.innerHTML = '<main id="main"></main>'; // the tests of the history above replaced it
  installApi({ 'GET /challenges/proposals': [], 'GET /challenges/debt': DEBT, 'GET /challenges/genres': [], 'GET /challenges': [] });
  await page.render({ main: main(), user: ANA });
  await settle();
  document.querySelector('#chNew').click();
  await settle();
  const form = document.querySelector('.modal-content form');
  form.elements.kind.value = 'debt_reduction';
  form.elements.kind.dispatchEvent(new window.Event('change', { bubbles: true }));
  assert.match(document.querySelector('#chDebtPreview').textContent, /El 25 % de tu deuda son unas 10 h \(tu deuda ahora: 40 h en 4 juegos\)/);
  form.elements.debtValue.value = '12.5';
  form.elements.debtValue.dispatchEvent(new window.Event('input', { bubbles: true }));
  assert.match(document.querySelector('#chDebtPreview').textContent, /El 12,5 % de tu deuda son unas 5 h/);
});

test('launching a debt challenge sends the percentage or the games', async () => {
  document.body.innerHTML = '<main id="main"></main>'; // the tests of the history above replaced it
  const calls = installApi({ 'GET /challenges/proposals': [], 'GET /challenges/debt': DEBT, 'GET /challenges/genres': [], 'GET /challenges': [], 'POST /challenges': personal() });
  await page.render({ main: main(), user: ANA });
  await settle();
  document.querySelector('#chNew').click();
  await settle();
  const form = document.querySelector('.modal-content form');
  form.elements.kind.value = 'debt_reduction';
  form.elements.kind.dispatchEvent(new window.Event('change', { bubbles: true }));
  form.elements.debtValue.value = '30';
  form.requestSubmit();
  await settle();
  assert.deepEqual(calls.find((c) => c.method === 'POST').body, { kind: 'debt_reduction', options: { mode: 'percent', duration: 'month', percent: 30 } });
  document.querySelector('#chNew').click();
  await settle();
  const second = document.querySelector('.modal-content form');
  second.elements.kind.value = 'debt_reduction';
  second.elements.debtMode.value = 'games';
  second.elements.debtMode.dispatchEvent(new window.Event('change', { bubbles: true }));
  assert.equal(second.elements.debtValue.max, '5'); // as many as are open
  second.elements.debtValue.value = '2';
  second.requestSubmit();
  await settle();
  assert.deepEqual(calls.filter((c) => c.method === 'POST').at(-1).body.options, { mode: 'games', duration: 'month', games: 2 });
});

test('a debt challenge shows its share of the debt paid', async () => {
  document.body.innerHTML = '<main id="main"></main>'; // the tests of the history above replaced it
  const progress = { players: [{ user_id: 1, name: 'Ana', percent: 12.5, target_percent: 25, paid_seconds: 18000, initial_seconds: 144000, done: false }] };
  installApi({ 'GET /challenges/proposals': [], 'GET /challenges': [personal({ kind: 'debt_reduction', label: 'Bajar la deuda', title: 'Bajar la deuda un 25 %', params: { mode: 'percent', percent: 25, duration: 'month' }, progress })] });
  await page.render({ main: main(), user: ANA });
  await settle();
  assert.match(text('.ch-row')[0], /12,5 % \/ 25 %/);
  assert.match(main().textContent, /saldar el 25 % de lo que te quedaba por jugar al empezar/);
});

test('each challenge tells the viewer how they stand and the top of the page counts the running ones', async () => {
  installApi({ 'GET /challenges/proposals': [], 'GET /challenges': [challenge(), personal({ owner: { id: 2, name: 'Bea' }, taking_part: false })] });
  await page.render({ main: main(), user: ANA });
  await settle();
  assert.deepEqual([...document.querySelectorAll('[data-standing]')].map((el) => el.dataset.standing), ['done']); // Ana's part is reached; Bea's challenge is not Ana's
  assert.match(document.querySelector('.ch-standing').textContent, /Ya has cumplido tu parte/);
  assert.equal(document.querySelector('[data-digest]').textContent, '1 reto en marcha · 1 cumplido');
});

test('a viewer with nothing running gets no summary line', async () => {
  installApi({ 'GET /challenges/proposals': [], 'GET /challenges': [] });
  await page.render({ main: main(), user: ANA });
  await settle();
  assert.equal(document.querySelector('[data-digest]'), null);
});

test('each new personal kind sends its own options', async () => {
  document.body.innerHTML = '<main id="main"></main>';
  const calls = installApi({ 'GET /challenges/proposals': [], 'GET /challenges/debt': DEBT, 'GET /challenges/genres': [], 'GET /challenges': [], 'POST /challenges': personal() });
  await page.render({ main: main(), user: ANA });
  await settle();
  const launch = async (kind, values) => {
    document.querySelector('#chNew').click();
    await settle();
    const form = document.querySelector('.modal-content form');
    form.elements.kind.value = kind;
    form.elements.kind.dispatchEvent(new window.Event('change', { bubbles: true }));
    assert.equal(form.querySelector(`[data-kind="${kind}"]`).hidden, false);
    for (const [name, value] of Object.entries(values)) form.elements[name].value = value;
    form.elements.duration.value = 'week';
    form.requestSubmit();
    await settle();
    return calls.filter((c) => c.method === 'POST').at(-1).body;
  };
  assert.deepEqual(await launch('streak', { streakMode: 'days', streakDays: '4' }), { kind: 'streak', options: { mode: 'days', days: 4, duration: 'week' } });
  assert.deepEqual(await launch('long_sessions', { longSessions: '2', longMinutes: '90' }), { kind: 'long_sessions', options: { sessions: 2, minutes: 90, duration: 'week' } });
  assert.deepEqual(await launch('variety', { varietyGenres: '4', varietyHours: '1.5' }), { kind: 'variety', options: { genres: 4, hours: 1.5, duration: 'week' } });
  assert.deepEqual(await launch('wishlist', { wishMode: 'complete', wishGames: '2' }), { kind: 'wishlist', options: { mode: 'complete', games: 2, duration: 'week' } });
});

test('a challenge counted in days says so on its bar and its notice', async () => {
  document.body.innerHTML = '<main id="main"></main>';
  const progress = { players: [{ user_id: 1, name: 'Ana', count: 3, target_count: 7, unit: 'days', done: false }] };
  installApi({ 'GET /challenges/proposals': [], 'GET /challenges': [personal({ kind: 'streak', label: 'Racha', title: 'Racha de 7 días', params: { mode: 'consecutive', days: 7, duration: 'month' }, progress })] });
  await page.render({ main: main(), user: ANA });
  await settle();
  assert.match(document.querySelector('.ch-players').textContent, /3 \/ 7 días/);
  assert.match(main().textContent, /jugar 7 días seguidos/);
});

const duelCard = (extra = {}) => ({
  id: 21, kind: 'duel_hours', label: 'Duelo de horas', scope: 'duel', title: 'Duelo de horas', status: 'active', declined: false,
  starts_on: '2026-10-01', ends_on: '2026-10-30', params: { opponent_id: 2, duration: 'month' }, game: null,
  owner: { id: 2, name: 'Bea' }, opponent: { id: 1, name: 'Ana' }, taking_part: true, can_opt_out: true,
  progress: { players: [
    { user_id: 2, name: 'Bea', seconds: 7200, target_seconds: 7200, versus: true, position: 1, winner: true, done: true },
    { user_id: 1, name: 'Ana', seconds: 3600, target_seconds: 7200, versus: true, position: 2, winner: false, done: false },
  ] },
  ...extra,
});

test('a duel shows both players with their hours and medals, and the challenged one can decline it', async () => {
  document.body.innerHTML = '<main id="main"></main>';
  const calls = installApi({ 'GET /challenges/proposals': [], 'GET /challenges': [duelCard()], 'PUT /challenges/21/participation': duelCard({ taking_part: false, declined: true }) });
  await page.render({ main: main(), user: ANA });
  await settle();
  assert.deepEqual(text('.section-title'), ['Del grupo', 'Tuyos', 'Duelos']);
  assert.match(document.querySelector('.ch-card .pf-sub').textContent, /Bea contra Ana/);
  assert.deepEqual(text('.ch-players .ch-name'), ['🥇 Bea', '🥈 Ana (tú)']);
  assert.deepEqual(text('.ch-players .pf-sub'), ['2 h ✓', '1 h']); // the leader is the one who is winning
  assert.match(main().textContent, /Vas perdiendo contra Bea por 1 h/);
  assert.match(main().textContent, /Puedes rechazarlo durante las 48 horas/);
  assert.equal(document.querySelector('[data-delete]'), null); // only the challenger deletes it
  const button = document.querySelector('[data-part]');
  assert.equal(button.textContent.trim(), 'Rechazar duelo');
  button.click();
  await settle();
  assert.ok(calls.some((c) => c.method === 'PUT' && c.path.includes('/21/participation?joined=false')));
});

test('a declined duel says so and the challenger can delete it', async () => {
  document.body.innerHTML = '<main id="main"></main>';
  const declined = duelCard({
    owner: { id: 1, name: 'Ana' }, opponent: { id: 2, name: 'Bea' }, declined: true, can_opt_out: false,
    progress: { players: [{ user_id: 1, name: 'Ana', seconds: 0, target_seconds: 0, versus: true, position: 1, winner: false, done: false }] },
  });
  installApi({ 'GET /challenges/proposals': [], 'GET /challenges': [declined] });
  await page.render({ main: main(), user: ANA });
  await settle();
  assert.match(document.querySelector('.pf-tag').textContent, /Rechazado/);
  assert.match(main().textContent, /Bea ha rechazado el duelo/);
  assert.notEqual(document.querySelector('[data-delete]'), null);
});

test('a duel is launched against a player of the list, with a game for a duel in a game', async () => {
  document.body.innerHTML = '<main id="main"></main>';
  const players = [
    { user_id: 1, name: 'Ana', is_active: true, is_me: true }, { user_id: 2, name: 'Bea', is_active: true, is_me: false },
    { user_id: 3, name: 'Cris', is_active: false, is_me: false },
  ];
  const calls = installApi({
    'GET /challenges/debt': DEBT, 'GET /challenges/genres': [], 'GET /challenges': [], 'GET /group/players': players,
    'GET /games/catalog?q=hades&limit=8': { items: [{ id: 'hades', name: 'Hades' }] }, 'POST /challenges': duelCard(),
  });
  await page.render({ main: main(), user: ANA });
  await settle();
  document.querySelector('#chNew').click();
  await settle();
  const form = document.querySelector('.modal-content form');
  assert.deepEqual(text('select[name="duelOpponent"] option'), ['Bea']); // neither oneself nor a player who is not active
  form.elements.kind.value = 'duel_hours';
  form.elements.kind.dispatchEvent(new window.Event('change', { bubbles: true }));
  assert.equal(form.querySelector('[data-kind="duel_hours duel_game"]').hidden, false);
  assert.equal(form.querySelector('[data-kind="duel_game"]').hidden, true);
  form.requestSubmit();
  await settle();
  assert.deepEqual(calls.find((c) => c.method === 'POST').body, { kind: 'duel_hours', options: { opponent_id: 2, duration: 'month' } });

  document.querySelector('#chNew').click();
  await settle();
  const second = document.querySelector('.modal-content form');
  second.elements.kind.value = 'duel_game';
  second.elements.kind.dispatchEvent(new window.Event('change', { bubbles: true }));
  assert.equal(second.querySelector('[data-kind="duel_game"]').hidden, false);
  second.elements.gameQuery.value = 'hades';
  second.elements.gameQuery.dispatchEvent(new window.Event('input', { bubbles: true }));
  await new Promise((resolve) => setTimeout(resolve, 300));
  await settle();
  second.querySelector('[data-game-id="hades"]').click();
  assert.match(second.querySelector('[data-game-chosen]').textContent, /Juego elegido: Hades/);
  second.requestSubmit();
  await settle();
  assert.deepEqual(calls.filter((c) => c.method === 'POST').at(-1).body, { kind: 'duel_game', options: { opponent_id: 2, game_id: 'hades', duration: 'month' } });
});

test('a voluntary group challenge says so and offers to join, and joining asks the API for the caller only', async () => {
  document.body.innerHTML = '<main id="main"></main>';
  const voluntary = challenge({ participation: 'opt_in', taking_part: false, progress: { players: [], total_seconds: 0, total_target_seconds: 43200, total_done: false } });
  const calls = installApi({ 'GET /challenges/proposals': [], 'GET /challenges': [voluntary], 'PUT /challenges/5/participation': challenge({ participation: 'opt_in' }) });
  await page.render({ main: main(), user: ANA });
  await settle();
  assert.match(document.querySelector('.ch-title').textContent, /Voluntario/);
  assert.match(main().textContent, /Es un reto voluntario: apúntate si quieres jugarlo/);
  const button = document.querySelector('[data-part]');
  assert.equal(button.textContent.trim(), 'Apuntarme');
  assert.equal(button.dataset.part, 'join');
  button.click();
  await settle();
  assert.ok(calls.some((c) => c.method === 'PUT' && c.path.includes('/5/participation?joined=true')));
});

test('the proposals of the player show how each one stands and a pending one can be withdrawn with a second press', async () => {
  document.body.innerHTML = '<main id="main"></main>';
  const proposals = [
    { id: 1, kind: 'themed', label: 'Temático', title: 'Temático: Horror', status: 'pending', decision_note: null },
    { id: 2, kind: 'game_of_month', label: 'Juego del mes', title: 'Juego del mes: Hades', status: 'rejected', decision_note: 'Mejor en noviembre' },
    { id: 3, kind: 'game_of_month', label: 'Juego del mes', title: 'Juego del mes: Celeste', status: 'approved', decision_note: null },
  ];
  const calls = installApi({ 'GET /challenges/proposals': proposals, 'DELETE /challenges/proposals/1': { message: 'ok' }, 'GET /challenges': [] });
  await page.render({ main: main(), user: ANA });
  await settle();
  assert.deepEqual([...document.querySelectorAll('#chProposals [data-status]')].map((el) => el.textContent), ['Esperando respuesta', 'Rechazada', 'Aprobada']);
  assert.match(document.querySelector('#chProposals').textContent, /Nota: Mejor en noviembre/);
  assert.equal(document.querySelectorAll('#chProposals [data-withdraw]').length, 1); // only the pending one
  const withdraw = document.querySelector('[data-withdraw]');
  withdraw.click();
  assert.equal(calls.some((c) => c.method === 'DELETE'), false);
  assert.match(withdraw.textContent, /Seguro/);
  withdraw.click();
  await settle();
  assert.ok(calls.some((c) => c.method === 'DELETE' && c.path === '/challenges/proposals/1'));
});

test('a player with no proposals sees no block of them', async () => {
  document.body.innerHTML = '<main id="main"></main>';
  installApi({ 'GET /challenges/proposals': [], 'GET /challenges': [] });
  await page.render({ main: main(), user: ANA });
  await settle();
  assert.equal(document.querySelector('#chProposals').children.length, 0);
});

test('a game of the month is proposed with a game from the search and a themed one with a tag', async () => {
  document.body.innerHTML = '<main id="main"></main>';
  const calls = installApi({
    'GET /challenges/proposals': [], 'GET /challenges/tags': [{ tag: 'Horror', games: 3 }, { tag: 'Puzzle', games: 1 }], 'GET /challenges': [],
    'GET /games/catalog?q=hades&limit=8': { items: [{ id: 'hades', name: 'Hades' }] },
    'POST /challenges/proposals': { id: 1, status: 'pending', kind: 'themed', label: 'Temático', title: 'x' },
  });
  await page.render({ main: main(), user: ANA });
  await settle();
  document.querySelector('#chPropose').click();
  await settle();
  const form = document.querySelector('.modal-content form');
  assert.deepEqual(text('select[name="tag"] option'), ['Horror (3)', 'Puzzle (1)']);
  assert.equal(form.querySelector('[data-kind="themed"]').hidden, true);
  form.elements.gameQuery.value = 'hades';
  form.elements.gameQuery.dispatchEvent(new window.Event('input', { bubbles: true }));
  await new Promise((resolve) => setTimeout(resolve, 300));
  await settle();
  form.querySelector('[data-game-id="hades"]').click();
  form.elements.gameEach.value = '3';
  form.elements.gameTotal.value = '12';
  form.elements.month.value = form.elements.month.options[1].value;
  form.requestSubmit();
  await settle();
  const first = calls.find((c) => c.method === 'POST' && c.path === '/challenges/proposals').body;
  assert.deepEqual(first, { kind: 'game_of_month', options: { game_id: 'hades', month: form.elements.month.options[1].value, min_hours_each: 3, min_hours_total: 12, versus: false } });

  document.querySelector('#chPropose').click();
  await settle();
  const second = document.querySelector('.modal-content form');
  second.elements.kind.value = 'themed';
  second.elements.kind.dispatchEvent(new window.Event('change', { bubbles: true }));
  second.elements.tag.value = 'Puzzle';
  second.elements.mode.value = 'complete';
  second.elements.mode.dispatchEvent(new window.Event('change', { bubbles: true }));
  assert.equal(second.querySelector('[data-for="play"]').hidden, true);
  second.elements.themedGames.value = '5';
  second.elements.versus.checked = true;
  second.requestSubmit();
  await settle();
  const body = calls.filter((c) => c.method === 'POST' && c.path === '/challenges/proposals').at(-1).body;
  assert.equal(body.kind, 'themed');
  assert.deepEqual({ ...body.options, month: 'x' }, { tag: 'Puzzle', month: 'x', mode: 'complete', versus: true, min_games_total: 5 });
});

test('an error of the API stays in the proposal form', async () => {
  document.body.innerHTML = '<main id="main"></main>';
  installApi({ 'GET /challenges/proposals': [], 'GET /challenges/tags': [], 'GET /challenges': [], 'POST /challenges/proposals': () => { throw new Error('Ya hay una propuesta igual esperando respuesta'); } });
  await page.render({ main: main(), user: ANA });
  await settle();
  document.querySelector('#chPropose').click();
  await settle();
  document.querySelector('.modal-content form').requestSubmit();
  await settle();
  assert.match(document.querySelector('.modal-content .adm-error').textContent, /Ya hay una propuesta igual/);
});

test('the page asks only for the latest finished challenges of each block and "Ver todos" asks for every one', async () => {
  document.body.innerHTML = '<main id="main"></main>';
  const finished = Array.from({ length: 5 }, (_, i) => personal({ id: 100 + i, title: `Terminado ${i}`, status: 'finished', starts_on: '2026-0' + (i + 1) + '-01' }));
  const calls = installApi({ 'GET /challenges/proposals': [], 'GET /challenges': [challenge(), ...finished] });
  await page.render({ main: main(), user: ANA });
  await settle();
  assert.equal(calls.find((c) => c.path.startsWith('/challenges?')).path, '/challenges?finished_per_block=5');
  const button = document.querySelector('[data-all]');
  assert.ok(button); // a block shows five finished ones: there may be more
  button.click();
  await settle();
  assert.equal(calls.filter((c) => c.method === 'GET' && c.path === '/challenges').length, 1); // and now it asks for all of them
  assert.equal(document.querySelector('[data-all]'), null);
});

test('with fewer finished challenges than the page shows there is nothing more to ask for', async () => {
  document.body.innerHTML = '<main id="main"></main>';
  installApi({ 'GET /challenges/proposals': [], 'GET /challenges': [challenge(), personal({ status: 'finished' })] });
  await page.render({ main: main(), user: ANA });
  await settle();
  assert.equal(document.querySelector('[data-all]'), null);
});
