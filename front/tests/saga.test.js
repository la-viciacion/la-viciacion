import assert from 'node:assert/strict';
import { test } from 'node:test';
import { newestFirst, releaseYear, sagaSummary, standing } from '../js/lib/saga.js';

const game = (over) => ({ rawg_id: 1, name: 'Hades', released: '2020-09-17', game_id: 'hades', mine: null, next: false, current: false, ...over });

test('the year of a release, or nothing', () => {
  assert.equal(releaseYear('2020-09-17'), '2020');
  assert.equal(releaseYear(null), '');
});

test('where the viewer stands in a game: completed, in the library with its time, not had, or not in the group at all', () => {
  assert.deepEqual(standing(game({ mine: { has: true, completed: true, seconds: 3600 } })), { label: 'Completado', tone: 'done' });
  assert.deepEqual(standing(game({ mine: { has: true, completed: false, seconds: 5400 } })), { label: 'En tu biblioteca · 1 h 30 min', tone: 'live' });
  assert.deepEqual(standing(game({ mine: { has: true, completed: false, seconds: 0 } })), { label: 'En tu biblioteca', tone: 'live' });
  assert.deepEqual(standing(game({})), { label: 'No lo tienes', tone: 'muted' });
  assert.deepEqual(standing(game({ game_id: null })), { label: 'No está en la biblioteca del grupo', tone: 'muted' });
});

test('the summary counts what is completed and names the next game', () => {
  const list = [game({ mine: { has: true, completed: true, seconds: 1 } }), game({ rawg_id: 2, name: 'Hades II', next: true }), game({ rawg_id: 3, name: 'Remix' })];
  assert.equal(sagaSummary(list), 'Has completado 1 de 3. Siguiente: Hades II.');
  assert.equal(sagaSummary([game({})]), 'Has completado 0 de 1.');
  assert.equal(sagaSummary([]), '');
});

test('the saga is shown from the newest to the oldest, the undated last, without changing what it was given', () => {
  const list = [
    game({ rawg_id: 1, name: 'B', released: '2010-01-01' }),
    game({ rawg_id: 2, name: 'A', released: null }),
    game({ rawg_id: 3, name: 'C', released: '2020-05-05' }),
    game({ rawg_id: 4, name: 'D', released: '2010-01-01' }),
  ];
  assert.deepEqual(newestFirst(list).map((g) => g.rawg_id), [3, 1, 4, 2]); // a tie goes by name
  assert.deepEqual(list.map((g) => g.rawg_id), [1, 2, 3, 4]);
});
