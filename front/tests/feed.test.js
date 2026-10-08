import assert from 'node:assert/strict';
import { test } from 'node:test';
import { installApi, installDom, installStorage } from './dom.js';

installStorage();
installDom('<main id="main"></main>');
const { feedSince, resetFeed } = await import('../js/pages/stats/feed.js');

// a feed of `total` events, one per day going back from 2026-03-31, served 100 at a time like the API does
const day = (i) => new Date(Date.UTC(2026, 2, 31 - i)).toISOString().slice(0, 10);
const serve = (total) => ({ path }) => {
  const { searchParams } = new URL(path, 'http://x');
  const [limit, offset] = ['limit', 'offset'].map((k) => Number(searchParams.get(k)));
  const items = Array.from({ length: Math.min(limit, total - offset) }, (_, i) => ({ type: 'played', day: day(offset + i) }));
  return { items, has_more: offset + limit < total };
};

test('it reads back only as far as the day asked for, and keeps what it read', async () => {
  resetFeed();
  const calls = installApi({ 'GET /activity': serve(500) });
  const first = await feedSince('2026-03-01');
  assert.equal(calls.length, 1); // the first 100 days go back far enough
  assert.equal(first.items.length, 100);
  assert.equal(first.truncated, false);
  await feedSince('2026-03-01');
  assert.equal(calls.length, 1);
  const deeper = await feedSince('2025-12-01');
  assert.equal(deeper.items.length, 200);
  assert.equal(calls.at(-1).path, '/activity?limit=100&offset=100');
});

test('without a day it reads everything, and the cap says the history is longer', async () => {
  resetFeed();
  installApi({ 'GET /activity': serve(150) });
  const all = await feedSince(null);
  assert.deepEqual([all.items.length, all.truncated], [150, false]);
  resetFeed();
  installApi({ 'GET /activity': serve(5000) });
  const capped = await feedSince(null);
  assert.deepEqual([capped.items.length, capped.truncated], [4000, true]);
});

test('two reads started together do not ask for the same page twice', async () => {
  resetFeed();
  const calls = installApi({ 'GET /activity': serve(100) });
  const [a, b] = await Promise.all([feedSince(null), feedSince(null)]);
  assert.equal(calls.length, 1);
  assert.equal(a.items.length + b.items.length, 200);
});
