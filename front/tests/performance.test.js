import assert from 'node:assert/strict';
import { test } from 'node:test';
import { count, duration, errorRate, memory, perMinute, shortRoute } from '../js/lib/performance.js';

test('a time of answer is in milliseconds below a second and in seconds above', () => {
  assert.equal(duration(null), '—');
  assert.equal(duration(0.004), '<10 ms');
  assert.equal(duration(0.0234), '23 ms');
  assert.equal(duration(1.5), '1,50 s');
  assert.equal(duration(12.34), '12,3 s');
});

test('counts and rates read in Spanish, with a dash when there is nothing recorded', () => {
  assert.equal(count(null), '—');
  assert.equal(count(12345), '12.345');
  assert.equal(perMinute(2.5), '2,5/min');
  assert.equal(perMinute(42), '42/min');
});

test('the error rate is a share of the requests, and a dash without requests', () => {
  assert.equal(errorRate(0, 0), '—');
  assert.equal(errorRate(null, 0), '—');
  assert.equal(errorRate(200, 0), '0,0 %');
  assert.equal(errorRate(1000, 3), '0,30 %');
  assert.equal(errorRate(100, 5), '5,0 %');
});

test('the memory is in bytes made readable, a dash when unknown', () => {
  assert.equal(memory(undefined), '—');
  assert.match(memory(300 * 1024 * 1024), /MB/);
});

test('a route is shown without the API prefix', () => {
  assert.equal(shortRoute('/api/v1/timers/active/{user_id}'), '/timers/active/{user_id}');
  assert.equal(shortRoute('/api/v1'), '/');
  assert.equal(shortRoute('unmatched'), 'unmatched');
});
