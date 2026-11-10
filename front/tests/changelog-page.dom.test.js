import assert from 'node:assert/strict';
import { test } from 'node:test';
import { installDom, installStorage, text } from './dom.js';
import { CHANGELOG, DOCS_URL, groups } from '../js/lib/changelog.js';

installStorage();
installDom('<main id="main"></main>');
const page = await import('../js/pages/changelog/index.js');

test('it lists every entry, the newest first, with its items grouped by kind', () => {
  page.render({ main: document.getElementById('main') });
  assert.equal(text('h1')[0], 'Novedades');
  assert.equal(document.querySelectorAll('.cl-entry').length, CHANGELOG.length);
  assert.equal(text('.cl-version')[0], CHANGELOG[0].title);
  assert.ok(text('.cl-meta')[0].startsWith(`v${CHANGELOG[0].version} · `)); // the newest entry's versions, whichever it is
  const total = CHANGELOG.reduce((n, e) => n + e.items.length, 0);
  assert.equal(document.querySelectorAll('.cl-items li').length, total);
  assert.deepEqual(text('.cl-kind').slice(0, groups(CHANGELOG[0]).length), groups(CHANGELOG[0]).map((g) => g.label));
});

test('it links to the full user guide, in a new tab', () => {
  page.render({ main: document.getElementById('main') });
  const link = document.querySelector('.cl-docs');
  assert.equal(link.getAttribute('href'), DOCS_URL);
  assert.equal(link.getAttribute('target'), '_blank');
  assert.match(link.getAttribute('rel'), /noopener/);
  assert.match(link.textContent, /Documentación completa/);
});
