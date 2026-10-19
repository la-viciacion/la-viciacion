import assert from 'node:assert/strict';
import { test } from 'node:test';
import { installApi, installDom, installStorage, settle } from './dom.js';

installStorage();
const window = installDom('<div id="panel"></div>', 'http://localhost/');
globalThis.location = window.location;
const { render } = await import('../js/pages/admin/recap.js');
const { store } = await import('../js/pages/admin/components.js');
const { ANNUAL_DAYS, syncAnnualDay } = await import('../js/pages/admin/settings.js');

store.me = 1;
store.users = [{ id: 1, username: 'ana' }, { id: 2, username: 'biel' }];

const VALUES = {
  'notifications.enabled': true, 'notifications.admin_alerts': true, 'weekly.enabled': true, 'weekly.weekday': 0, 'weekly.time': '09:00',
  'monthly.enabled': false, 'monthly.day': 1, 'monthly.time': '10:00',
  'annual.enabled': false, 'annual.month': 1, 'annual.day': 1, 'annual.time': '10:00',
  'telegram.token': { is_set: false }, 'telegram.group_id': { is_set: false }, 'telegram.admin_chat_id': { is_set: false },
  'push.enabled': true, 'push.contact': '', 'push.vapid_private': { is_set: true }, 'ai.enabled': true, 'ai.provider': 'google', 'ai.api_key': { is_set: false }, 'ai.model': '',
};

function routes(extra = {}) {
  return {
    'GET /manage/recap/preview': { period: '2026-09', label: 'septiembre de 2026', nobody_played: false, telegram: 'TELEGRAM', push: { title: 'TITULO', body: 'CUERPO', url: '#/story/2026-09' } },
    'GET /manage/settings': { values: VALUES, jobs: { annual_recap: { last_run_at: '2027-01-01T10:00:00', last_status: 'ok: 2026: group and 3 users' } }, push_devices: { devices: 0, users: 0 }, mail: { configured: false, missing: [] }, ai_uses: [] },
    ...extra,
  };
}

const panel = () => document.getElementById('panel');
const field = (name) => panel().querySelector(`[name="${name}"]`);
const lastMonthKey = () => { const d = new Date(new Date().getFullYear(), new Date().getMonth() - 1, 1); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`; };
const previewPaths = (calls) => calls.filter((c) => c.path.startsWith('/manage/recap/preview')).map((c) => c.path);
const enabledDays = (select) => [...select.options].filter((o) => !o.disabled).map((o) => Number(o.value));
const change = (el, value) => {
  el.value = String(value);
  el.dispatchEvent(new window.Event('change', { bubbles: true }));
};

test('the Recap tab has the notice, the sending and the two schedules', async () => {
  const calls = installApi(routes());
  await render(panel());
  await settle();
  assert.equal(panel().querySelector('#rcaTelegram').textContent, 'TELEGRAM');
  assert.equal(panel().querySelector('#rcaPushTitle').textContent, 'TITULO');
  assert.equal(panel().querySelector('#rcaPushBody').textContent, 'CUERPO');
  assert.match(calls.find((c) => c.path.startsWith('/manage/recap/preview')).path, /^\/manage\/recap\/preview\?period=\d{4}-\d{2}$/);
  assert.doesNotMatch(panel().textContent, /Texto para el jugador/);
  assert.match(panel().textContent, /Envío automático/);
  assert.match(panel().textContent, /Resumen mensual/);
  assert.match(panel().textContent, /Resumen anual/);
  assert.match(panel().textContent, /Último envío/); // the annual job ran
  assert.deepEqual([...panel().querySelectorAll('[data-send]')].map((b) => b.dataset.send), ['me', 'group']);
});

test('the player only changes where the buttons open, not the notice', async () => {
  const calls = installApi(routes());
  await render(panel());
  await settle();
  const before = calls.filter((c) => c.path.startsWith('/manage/recap/preview')).length;
  change(panel().querySelector('#rcaUser'), 2);
  await settle();
  assert.equal(calls.filter((c) => c.path.startsWith('/manage/recap/preview')).length, before);
  assert.match(panel().querySelector('#rcaStory').getAttribute('href'), /^#\/story\/\d{4}-\d{2}\/biel$/);
  assert.match(panel().querySelector('#rcaOpen').getAttribute('href'), /^#\/recap\/\d{4}-\d{2}\/biel$/);
});

test('the monthly recap can go out from the 1st to the 5th', async () => {
  installApi(routes());
  await render(panel());
  await settle();
  assert.deepEqual([...field('monthly.day').options].map((o) => Number(o.value)), [1, 2, 3, 4, 5]);
});

test('the annual recap is in January by default, with January days, and December moves the days to 20-28', async () => {
  installApi(routes());
  await render(panel());
  await settle();
  assert.equal(field('annual.month').value, '1');
  assert.deepEqual(enabledDays(field('annual.day')), [1, 2, 3, 4, 5]);
  change(field('annual.month'), 12);
  assert.deepEqual(enabledDays(field('annual.day')), [20, 21, 22, 23, 24, 25, 26, 27, 28]);
  assert.equal(field('annual.day').value, '20', 'a day that no longer fits moves to the first one that does');
  change(field('annual.day'), 25);
  change(field('annual.month'), 1);
  assert.equal(field('annual.day').value, '1');
});

test('the months and days of the annual recap are the ones the API accepts', () => {
  assert.deepEqual(ANNUAL_DAYS, { 12: [20, 28], 1: [1, 5] });
  const form = document.createElement('form');
  form.innerHTML = '<select name="annual.month"><option value="12">D</option><option value="1">E</option></select><select name="annual.day"></select>';
  assert.doesNotThrow(() => syncAnnualDay(form)); // a day select without options does nothing harmful
});

test('saving sends the month and the day together', async () => {
  let saved;
  installApi(routes({ 'PUT /manage/settings': ({ body }) => { saved = body; return { changed: Object.keys(body.values), values: VALUES }; } }));
  await render(panel());
  await settle();
  const enable = field('annual.enabled');
  enable.checked = true;
  change(field('annual.month'), 12);
  change(field('annual.day'), 24);
  panel().querySelector('#admSettings').dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }));
  await settle();
  assert.deepEqual(saved.values, { 'annual.enabled': true, 'annual.month': 12, 'annual.day': 24 });
});

test('the monthly settings are no longer among the notification settings', async () => {
  const { ENTITIES } = await import('../js/pages/admin/entities.js');
  assert.deepEqual(ENTITIES.notifications.sections, ['notifications', 'weekly', 'telegram', 'push']);
  assert.equal(ENTITIES.recap.label, 'Recap');
  assert.equal(ENTITIES.recap.custom, 'recap');
});

test('it opens on the last month, monthly, with a year and a month to choose instead of one long list', async () => {
  const calls = installApi(routes());
  await render(panel());
  await settle();
  assert.equal(panel().querySelector('#rcaKind').value, 'month');
  assert.deepEqual([...panel().querySelectorAll('#rcaKind option')].map((o) => o.textContent), ['Mensual', 'Anual']);
  assert.equal(panel().querySelectorAll('#rcaYear option').length, new Date().getFullYear() - 2023 + 1);
  assert.ok(panel().querySelector('#rcaMonth'));
  assert.deepEqual(previewPaths(calls), [`/manage/recap/preview?period=${lastMonthKey()}`]);
  assert.equal(panel().querySelector('#rcaPeriod'), null, 'the mixed list is gone');
});

test('choosing annual hides the month and previews the season', async () => {
  const calls = installApi(routes());
  await render(panel());
  await settle();
  change(panel().querySelector('#rcaKind'), 'year');
  await settle();
  assert.equal(panel().querySelector('#rcaMonth'), null);
  const year = panel().querySelector('#rcaYear').value;
  assert.equal(previewPaths(calls).at(-1), `/manage/recap/preview?period=${year}`);
  assert.equal(panel().querySelector('#rcaStory').getAttribute('href'), `#/story/${year}`);
  change(panel().querySelector('#rcaKind'), 'month');
  await settle();
  assert.ok(panel().querySelector('#rcaMonth'));
});

test('another year or month previews that one, and the months of the running year stop before the running one', async () => {
  const calls = installApi(routes());
  await render(panel());
  await settle();
  const thisYear = new Date().getFullYear();
  change(panel().querySelector('#rcaYear'), thisYear - 1);
  await settle();
  assert.equal(panel().querySelectorAll('#rcaMonth option').length, 12);
  change(panel().querySelector('#rcaMonth'), 3);
  await settle();
  assert.equal(previewPaths(calls).at(-1), `/manage/recap/preview?period=${thisYear - 1}-03`);
  change(panel().querySelector('#rcaYear'), thisYear);
  await settle();
  // the running month itself is not offered; in January the running year has none, so the picker falls back to December of the year before
  if (new Date().getMonth() === 0) assert.equal(panel().querySelector('#rcaYear').value, String(thisYear - 1));
  else assert.equal(panel().querySelectorAll('#rcaMonth option').length, new Date().getMonth());
});

test('the notice and the sending are one card, and the first one is called Previsualizar', async () => {
  installApi(routes());
  await render(panel());
  await settle();
  const titles = [...panel().querySelectorAll('#rcAdmin h3')].map((h) => h.textContent);
  assert.deepEqual(titles, ['Previsualizar', 'El aviso']);
  const notice = [...panel().querySelectorAll('#rcAdmin section')].find((s) => s.querySelector('h3').textContent === 'El aviso');
  assert.ok(notice.querySelector('#rcaTelegram') && notice.querySelector('[data-send="me"]') && notice.querySelector('[data-send="group"]'));
});
