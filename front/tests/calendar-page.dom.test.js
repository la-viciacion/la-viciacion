import assert from 'node:assert/strict';
import { test } from 'node:test';
import { installApi, installDom, installStorage, json, settle, text } from './dom.js';
import { monthOf, shiftMonth } from '../js/lib/calendar.js';

installStorage();
installDom('<main id="main"></main>');
const calendar = await import('../js/pages/calendar/index.js');

const main = () => document.getElementById('main');
const THIS = monthOf(new Date());
const NEXT = shiftMonth(THIS, 1);
const game = (id, name, day, wanted_by) => ({ id, name, image_url: null, genres: ['RPG'], release_date: `${NEXT}-${day}`, days_until: 30, wanted_by });
const ANA = { user_id: 1, name: 'Ana', is_me: true };
const BEA = { user_id: 2, name: 'Bea <b>', is_me: false };

test('the running month opens first and the months before it can be reached', async () => {
  const BEFORE = shiftMonth(THIS, -1);
  const calls = installApi({
    [`GET /group/releases?month=${THIS}`]: { month: THIS, releases: [], undated: [] },
    [`GET /group/releases?month=${BEFORE}`]: { month: BEFORE, releases: [{ ...game('p', 'Past', '05', []), release_date: `${BEFORE}-05`, days_until: null }], undated: [] },
  });
  await calendar.render({ main: main() });
  await settle();
  assert.equal(calls[0].path, `/group/releases?month=${THIS}`);
  assert.match(main().textContent, /Ningún lanzamiento este mes/);
  assert.equal(document.querySelectorAll('.cal-weekday').length, 7);
  const back = document.querySelector('[data-step="-1"]');
  assert.equal(back.disabled, false);
  back.click();
  await settle();
  assert.deepEqual(text('#calMonth .gc-name'), ['Past']);
  document.querySelector('[data-today]').click();
  await settle();
  assert.match(main().textContent, /Ningún lanzamiento este mes/);
  assert.equal(document.querySelector('[data-today]'), null, 'no button once back on the running month');
});

test('a day with releases is marked and opens its games with everybody who waits for them', async () => {
  installApi({
    [`GET /group/releases?month=${THIS}`]: { month: THIS, releases: [], undated: [] },
    [`GET /group/releases?month=${NEXT}`]: {
      month: NEXT,
      releases: [game('a', 'Alpha', '05', [ANA, BEA]), game('b', 'Beta', '05', [BEA]), game('c', 'Gamma', '20', [ANA])],
      undated: [{ ...game('d', 'Delta', '01', [BEA]), release_date: null, days_until: null }],
    },
  });
  await calendar.render({ main: main() });
  await settle();
  document.querySelector('[data-step="1"]').click();
  await settle();
  assert.equal(document.querySelectorAll('.cal-cell.has').length, 2);
  assert.equal(document.querySelector('.modal-overlay'), null, 'no day is opened by default');
  assert.deepEqual(text('#calMonth .gc-name'), ['Alpha', 'Beta', 'Gamma']);
  assert.match(text('#calMonth .pf-sub')[0], /Lo quieren tú y Bea <b>/);
  assert.equal(document.querySelectorAll('#calMonth b').length, 0); // escaped
  // every day with releases is a button that opens its games, one or several
  assert.equal(document.querySelector('a.cal-cell'), null);
  document.querySelector(`[data-day="${NEXT}-20"]`).click();
  assert.deepEqual(text('.modal-overlay .gc-name'), ['Gamma']);
  document.querySelector('.modal-overlay [data-close]').click();
  assert.equal(document.querySelector('.modal-overlay'), null);
  document.querySelector(`[data-day="${NEXT}-05"]`).click();
  assert.deepEqual(text('.modal-overlay .gc-name'), ['Alpha', 'Beta']);
  assert.ok(document.querySelector('.modal-overlay a[href="#/game/a"][data-close]'));
  document.querySelector('.modal-overlay [data-close]').click();
  assert.deepEqual(text('#calUndated .gc-name'), ['Delta']);
  assert.match(text('#calUndated .gc-meta')[0], /Sin fecha confirmada/);
});

test('an error loading a month is shown', async () => {
  installApi({
    [`GET /group/releases?month=${THIS}`]: { month: THIS, releases: [], undated: [] },
    [`GET /group/releases?month=${NEXT}`]: json({ detail: 'boom' }, 500),
  });
  await calendar.render({ main: main() });
  await settle();
  document.querySelector('[data-step="1"]').click();
  await settle();
  assert.match(main().textContent, /Error cargando el calendario/);
});
