import assert from 'node:assert/strict';
import { test } from 'node:test';
import { FAB_SIZE, parseFabPosition, snapFab } from '../js/lib/chat-fab.js';

const screen = { width: 400, height: 800, minBottom: 72 };

test('the button sticks to the nearest side', () => {
  assert.equal(snapFab({ ...screen, left: 50, top: 300 }).side, 'left');
  assert.equal(snapFab({ ...screen, left: 300, top: 300 }).side, 'right');
});

test('the height the player chose is kept as the distance from the bottom', () => {
  assert.equal(snapFab({ ...screen, left: 300, top: 300 }).bottom, 800 - (300 + FAB_SIZE));
});

test('it never rests below the bottom bar nor above the top of the screen', () => {
  assert.equal(snapFab({ ...screen, left: 300, top: 790 }).bottom, 72);
  assert.equal(snapFab({ ...screen, left: 300, top: -50 }).bottom, 800 - FAB_SIZE - 16);
});

test('a saved position is used only if it is valid', () => {
  assert.deepEqual(parseFabPosition('{"side":"left","bottom":240.4}'), { side: 'left', bottom: 240 });
  for (const bad of [null, '', 'x', '{"side":"top","bottom":10}', '{"side":"left","bottom":"10"}', '{"side":"left","bottom":-1}']) {
    assert.equal(parseFabPosition(bad), null);
  }
});
