import assert from 'node:assert/strict';
import { test } from 'node:test';
import { addsSomething, describeFile, parseExport, summarize } from '../js/lib/data-import.js';

const counts = (imported = 0, existing = 0, skipped = 0) => ({ imported, existing, skipped });
const report = (over = {}) => ({
  dry_run: true, sessions: counts(), library: counts(), scores: counts(), wishlist: counts(), created: { games: 0, platforms: 0 }, problems: [], problems_total: 0, ...over,
});

test('a file is accepted only if it is an export of the app', () => {
  assert.equal(parseExport('{"format":"laviciacion-export","version":1}').version, 1);
  assert.throws(() => parseExport('not json'), /JSON válido/);
  assert.throws(() => parseExport('{"format":"other"}'), /no es una exportación/);
  assert.throws(() => parseExport('null'), /no es una exportación/);
});

test('a file the proxy would refuse is refused first', () => {
  assert.throws(() => parseExport('{}', 9 * 1024 * 1024), /demasiado grande/);
});

test('the file is described by what it holds', () => {
  assert.equal(describeFile({ sessions: [1, 2], library: [1], scores: [], wishlist: [1, 2, 3] }), '2 sesiones, 1 juegos en la biblioteca, 3 deseados');
  assert.equal(describeFile({}), 'nada que importar');
});

test('the summary has a line for each kind that did something', () => {
  const lines = summarize(report({ sessions: counts(8, 2, 1), scores: counts(0, 1, 0) }));
  assert.deepEqual(lines, ['Sesiones: 8 nuevas, 2 que ya tenías, 1 no se puede importar', 'Puntuaciones: 1 que ya tenías']);
  assert.deepEqual(summarize(report({ sessions: counts(1, 0, 2) })), ['Sesiones: 1 nueva, 2 no se pueden importar']);
});

test('what an admin would create is said, before and after', () => {
  const created = { games: 2, platforms: 1 };
  assert.match(summarize(report({ created })).at(-1), /Se añadirían al catálogo: 2 juegos y 1 plataforma/);
  assert.match(summarize(report({ created, dry_run: false })).at(-1), /Añadidos al catálogo/);
});

test('an import that finds nothing new adds nothing', () => {
  assert.equal(addsSomething(report({ sessions: counts(0, 5, 1) })), false);
  assert.equal(addsSomething(report({ wishlist: counts(1) })), true);
  assert.equal(addsSomething(report({ created: { games: 1, platforms: 0 } })), true);
});
