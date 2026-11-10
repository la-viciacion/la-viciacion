import assert from 'node:assert/strict';
import { test } from 'node:test';
import { installDom, installStorage, text } from './dom.js';
import { CHANGELOG } from '../js/lib/changelog.js';

installStorage();
installDom('<main id="main"></main>');
const page = await import('../js/pages/changelog/index.js');

test('it lists every entry, the newest first, with its items grouped by kind', () => {
  page.render({ main: document.getElementById('main') });
  assert.equal(text('h1')[0], 'Novedades');
  assert.equal(document.querySelectorAll('.cl-entry').length, CHANGELOG.length);
  assert.equal(text('.cl-version')[0], CHANGELOG[0].title);
  assert.match(text('.cl-meta')[0], /^v2\.35 – 2\.39 · /);
  const total = CHANGELOG.reduce((n, e) => n + e.items.length, 0);
  assert.equal(document.querySelectorAll('.cl-items li').length, total);
  assert.deepEqual(text('.cl-kind').slice(0, 2), ['Nuevo', 'Mejora']);
});
