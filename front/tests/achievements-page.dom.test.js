import assert from 'node:assert/strict';
import { beforeEach, test } from 'node:test';
import { installApi, installDom, installStorage, json, settle, text } from './dom.js';

installStorage();
installDom('<main id="main"></main>');
const page = await import('../js/pages/achievements/index.js');

const LIST = [
  { id: 1, key: 'first', title: 'Primero <b>', description: 'Alguien lo hizo.', has_image: true, unlocked_by: 2, unlocked_by_me: true,
    players: [{ user_id: 1, name: 'Ana', times: 2, last: '2026-02-01' }, { user_id: 2, name: 'Bea', times: 1, last: '2025-01-01' }] },
  { id: 2, hidden: true, unlocked_by_me: false },
];

const main = () => document.getElementById('main');
let calls;

beforeEach(async () => {
  calls = installApi({ 'GET /group/achievements': LIST });
  await page.render({ main: main() });
  await settle();
});

test('yours are cards, with names as text, and the rest are listed hidden with the count', () => {
  assert.equal(calls[0].path, '/group/achievements');
  assert.deepEqual(text('.ach-title strong'), ['Primero <b>', 'Logro oculto']);
  assert.equal(document.querySelectorAll('.ach-title b').length, 0);
  assert.equal(text('.ach-count')[0], 'Tienes 1 de 2');
  assert.equal(document.querySelectorAll('.ach-card').length, 2);
  assert.equal(document.querySelectorAll('.ach-card.mine').length, 1);
  assert.equal(document.querySelectorAll('.ach-card.hidden').length, 1);
  assert.doesNotMatch(text('.ach-card')[0], /Lo tienes/);
  assert.doesNotMatch(text('.ach-card')[1], /Segundo|Otro/);
});

test('it says who has the unlocked ones, with the repeats', () => {
  assert.match(text('.ach-card')[0], /Lo han conseguido 2: Ana \(×2\) y Bea/);
});

test('the picture comes from the achievement image route only when there is one', () => {
  assert.equal(document.querySelector('.ach-card img').getAttribute('src'), '/api/v1/utils/achievement-image/first');
  assert.equal(document.querySelectorAll('.ach-card img').length, 1);
  assert.equal(document.querySelectorAll('.ach-img-placeholder').length, 1);
});

test('what is not unlocked shows a lock, not a question mark', () => {
  assert.equal(text('.ach-card.hidden .ach-img-placeholder')[0], '🔒');
});

test('a special one shines in the colour of its level, an ordinary one does not, with no tag saying the level', async () => {
  installApi({ 'GET /group/achievements': [{ ...LIST[0], special: 1 }, { ...LIST[0], id: 3, title: 'Dorado', special: 2 }, { ...LIST[0], id: 4, title: 'Normal', special: 0 }, LIST[1]] });
  await page.render({ main: main() });
  await settle();
  const cards = document.querySelectorAll('.ach-card.mine');
  assert.ok(cards[0].classList.contains('special-1'));
  assert.ok(cards[1].classList.contains('special-2'));
  assert.ok(![...cards[2].classList].some((c) => c.startsWith('special-')));
  assert.doesNotMatch(text('.ach-card').join(' '), /Especial/);  // the aura is enough
});

test('a secret one says so, and being secret is not being special', async () => {
  installApi({ 'GET /group/achievements': [{ ...LIST[0], secret: true }, { ...LIST[0], id: 3, title: 'Normal' }, LIST[1]] });
  await page.render({ main: main() });
  await settle();
  assert.match(text('.ach-card')[0], /Secreto/);
  assert.doesNotMatch(text('.ach-card')[1], /Secreto/);
  assert.ok(![...document.querySelector('.ach-card').classList].some((c) => c.startsWith('special-')));  // no aura without a level
});

test('one the viewer has not unlocked, and is not secret, is shown dimmed with its name only', async () => {
  installApi({ 'GET /group/achievements': [{ ...LIST[0], unlocked_by_me: false, unlocked_by: 0, players: [], description: null }, LIST[1]] });
  await page.render({ main: main() });
  await settle();
  const [open] = document.querySelectorAll('.ach-card.locked');
  assert.match(open.textContent, /Primero <b>/);
  assert.doesNotMatch(open.textContent, /Alguien lo hizo|null/);  // nothing about what it is
  assert.match(open.textContent, /Nadie lo ha conseguido/);
  assert.equal(document.querySelectorAll('.ach-card.mine').length, 0);
  assert.equal(text('.ach-count')[0], 'Tienes 0 de 2');
});

test('a secret one that is not unlocked still has the aura of its level, and says nothing else about itself', async () => {
  installApi({ 'GET /group/achievements': [LIST[1], { id: 5, hidden: true, unlocked_by_me: false, secret: true, special: 3 }] });
  await page.render({ main: main() });
  await settle();
  const [plain, special] = document.querySelectorAll('.ach-card.hidden');
  assert.ok(![...plain.classList].some((c) => c.startsWith('special-')));
  assert.ok(special.classList.contains('special-3'));
  assert.deepEqual(text('.ach-title strong'), ['Logro oculto', 'Logro oculto']);  // the aura is what tells them apart
  assert.doesNotMatch(special.textContent, /Secreto|Especial/);
});

test('there are two blocks, the season ones and the lifetime ones, each with the cards that belong to it', async () => {
  installApi({ 'GET /group/achievements': [
    { ...LIST[0], lifetime: true, title: 'Para siempre' }, { ...LIST[0], id: 3, title: 'De año' },
    { id: 4, hidden: true, unlocked_by_me: false, lifetime: true }, LIST[1],
  ] });
  await page.render({ main: main() });
  await settle();
  assert.deepEqual(text('.ach-block .section-title'), ['De temporada', 'Lifetime']);
  const [season, lifetime] = document.querySelectorAll('.ach-block');
  assert.deepEqual([...season.querySelectorAll('.ach-title strong')].map((e) => e.textContent), ['De año', 'Logro oculto']);
  assert.deepEqual([...lifetime.querySelectorAll('.ach-title strong')].map((e) => e.textContent), ['Para siempre', 'Logro oculto']);
  assert.match(season.querySelector('.ach-note').textContent, /Tienes 1 de 2/);
  assert.match(lifetime.querySelector('.ach-note').textContent, /Tienes 1 de 2/);
  assert.equal(text('.ach-count')[0], 'Tienes 2 de 4');
});

test('a block with nothing in it is not shown', () => {
  assert.deepEqual(text('.ach-block .section-title'), ['De temporada']);
});

test('an achievement that adds something up shows how far the player is, and the others show no bar', async () => {
  installApi({ 'GET /group/achievements': [
    { id: 5, key: 'PLAYED_100_HOURS', title: '100 horas', unlocked_by: 0, unlocked_by_me: false, players: [], progress: { percent: 35 } },
    { id: 6, key: 'EARLY', title: 'Sin barra', unlocked_by: 0, unlocked_by_me: false, players: [], progress: null },
    { id: 7, key: 'DONE', title: 'Hecho', unlocked_by: 1, unlocked_by_me: true, players: [{ user_id: 1, name: 'Ana', times: 1, last: '2026-02-01' }], progress: null },
  ] });
  await page.render({ main: main() });
  await settle();
  assert.equal(document.querySelectorAll('.ach-bar').length, 1);
  const bar = document.querySelector('.ach-bar');
  assert.equal(bar.getAttribute('role'), 'progressbar');
  assert.equal(bar.getAttribute('aria-valuenow'), '35');
  assert.match(document.querySelector('.ach-bar-fill').getAttribute('style'), /width: 35%/);
  assert.equal(document.querySelector('.ach-progress').textContent.trim(), ''); // no count, goal or unit
});

test('the season block has a pill per season, newest first, and the running one is pressed', () => {
  const year = new Date().getFullYear();
  const pills = [...document.querySelectorAll('.ach-seasons [data-season]')];
  assert.deepEqual(pills.map((p) => p.dataset.season), Array.from({ length: year - 2022 }, (_, i) => String(year - i)));
  assert.deepEqual(pills.filter((p) => p.getAttribute('aria-pressed') === 'true').map((p) => p.dataset.season), [String(year)]);
  assert.equal(document.querySelectorAll('.ach-seasons').length, 1);
  assert.equal(document.querySelector('.ach-seasons').closest('.ach-block').querySelector('.section-title').textContent, 'De temporada');
});

test('choosing a season asks for it and shows what that season had, keeping the lifetime block', async () => {
  const year = new Date().getFullYear();
  const calls = installApi({ 'GET /group/achievements': ({ path }) => (path.includes(`season=${year - 1}`)
    ? [{ ...LIST[0], title: 'Del año pasado' }, { ...LIST[0], id: 9, lifetime: true, title: 'Para siempre' }]
    : LIST) });
  await page.render({ main: main() });
  await settle();
  document.querySelector(`.ach-seasons [data-season="${year - 1}"]`).click();
  await settle();
  assert.equal(calls.at(-1).path, `/group/achievements?season=${year - 1}`);
  assert.deepEqual(text('.ach-block:first-of-type .ach-title strong'), ['Del año pasado']);
  assert.deepEqual(text('.ach-block .section-title'), ['De temporada', 'Lifetime']);
  assert.equal(document.querySelector(`.ach-seasons [aria-pressed="true"]`).dataset.season, String(year - 1));
  document.querySelector(`.ach-seasons [data-season="${year}"]`).click();
  await settle();
  assert.equal(calls.at(-1).path, '/group/achievements'); // the running season is the default one
});

test('every block starts open and can be folded, and stays as left when a season is chosen', async () => {
  const year = new Date().getFullYear();
  installApi({ 'GET /group/achievements': [{ ...LIST[0], title: 'De año' }, { ...LIST[0], id: 9, lifetime: true, title: 'Para siempre' }] });
  await page.render({ main: main() });
  await settle();
  const folds = () => [...document.querySelectorAll('.ach-fold')];
  assert.deepEqual(folds().map((f) => f.getAttribute('aria-expanded')), ['true', 'true']);
  assert.equal(document.querySelectorAll('.ach-block.folded').length, 0);
  folds()[1].click();
  assert.deepEqual(folds().map((f) => f.getAttribute('aria-expanded')), ['true', 'false']);
  assert.ok(document.querySelectorAll('.ach-block')[1].classList.contains('folded'));
  document.querySelector(`.ach-seasons [data-season="${year - 1}"]`).click();
  await settle();
  assert.deepEqual(folds().map((f) => f.getAttribute('aria-expanded')), ['true', 'false']);
  folds()[1].click();
  assert.equal(document.querySelectorAll('.ach-block.folded').length, 0);
});

test('a season with no achievements still shows its pills so another can be chosen', async () => {
  installApi({ 'GET /group/achievements': [] });
  await page.render({ main: main() });
  await settle();
  assert.equal(document.querySelectorAll('.ach-seasons [data-season]').length > 0, true);
});

test('an error says so', async () => {
  installApi({ 'GET /group/achievements': json({ detail: 'boom' }, 500) });
  await page.render({ main: main() });
  await settle();
  assert.match(main().textContent, /Error cargando los logros: boom/);
});
