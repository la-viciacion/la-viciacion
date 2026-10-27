import assert from 'node:assert/strict';
import { beforeEach, test } from 'node:test';
import { installDom, installStorage } from './dom.js';

import { createFolds, toggleFold } from '../js/lib/fold.js';

beforeEach(() => installStorage());

test('a fold is remembered under its storage key and read back', () => {
  const folds = createFolds('k');
  assert.equal(folds.set('a', true), true);
  assert.equal(folds.set('a', true), false); // nothing changed
  assert.deepEqual(JSON.parse(localStorage.getItem('k')), ['a']);
  assert.equal(createFolds('k').has('a'), true);
});

test('without a storage key nothing is saved', () => {
  const folds = createFolds();
  folds.set('a', true);
  assert.equal(localStorage.getItem('null'), null);
  assert.equal(folds.has('a'), true);
  folds.clear();
  assert.equal(folds.has('a'), false);
});

test('unreadable or refused storage leaves everything open and does not throw', () => {
  localStorage.setItem('k', '1'); // an old format
  assert.equal(createFolds('k').has('a'), false);
  localStorage.setItem('k', 'not json');
  const folds = createFolds('k');
  localStorage.setItem = () => { throw new Error('blocked'); };
  assert.doesNotThrow(() => folds.set('a', true));
  assert.equal(folds.has('a'), true); // it still folds for this page
});

test('toggleFold flips the key, the class and aria-expanded', () => {
  installDom('<section><button aria-expanded="true"></button></section>');
  const section = document.querySelector('section');
  const button = section.querySelector('button');
  const folds = createFolds();
  toggleFold(folds, 'a', section, button);
  assert.equal(section.classList.contains('folded'), true);
  assert.equal(button.getAttribute('aria-expanded'), 'false');
  toggleFold(folds, 'a', section, button);
  assert.equal(section.classList.contains('folded'), false);
  assert.equal(button.getAttribute('aria-expanded'), 'true');
});
