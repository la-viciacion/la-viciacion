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

test('the running month opens first and the month before it cannot be reached', async () => {
  const calls = installApi({ [`GET /group/releases?month=${THIS}`]: { month: THIS, releases: [], undated: [] } });
  await calendar.render({ main: main() });
  await settle();
  assert.equal(calls[0].path, `/group/releases?month=${THIS}`);
  assert.equal(document.querySelector('[data-step="-1"]').disabled, true);
  assert.match(main().textContent, /Ningún lanzamiento deseado este mes/);
  assert.equal(document.querySelectorAll('.cal-weekday').length, 7);
});

test('a day with releases is marked and shows its games with everybody who waits for them', async () => {
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
  assert.equal(document.querySelector(`[data-day="${NEXT}-05"]`).getAttribute('aria-pressed'), 'true'); // the first day with several games is selected
  assert.deepEqual(text('#calDay .gc-name'), ['Alpha', 'Beta']);
  assert.match(text('#calDay .pf-sub')[0], /Lo quieren tú y Bea <b>/);
  assert.equal(document.querySelectorAll('#calDay b').length, 0); // escaped
  // a day with one game is a link to its page, not a button
  const single = document.querySelector(`a.cal-cell[href="#/game/c"]`);
  assert.ok(single);
  assert.equal(document.querySelector(`[data-day="${NEXT}-20"]`), null);
  assert.match(single.getAttribute('title'), /Gamma · Lo quiere tú/);
  assert.deepEqual(text('#calDay .gc-name'), ['Alpha', 'Beta']);
  assert.equal(document.querySelector('#calDay a[href="#/game/a"]') !== null, true);
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
