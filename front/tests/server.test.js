import assert from 'node:assert/strict';
import { test } from 'node:test';
import { bytes, last, load, monthName, monthYear, uptime, linePoints, peak, percent, rate, sharedMax, statusInfo, trafficShare } from '../js/lib/server.js';

test('bytes use decimal units and keep decimals only where they matter', () => {
  assert.equal(bytes(0), '0 B');
  assert.equal(bytes(999), '999 B');
  assert.equal(bytes(1536), '1,5 KB');
  assert.equal(bytes(250_000_000), '250 MB');
  assert.equal(bytes(5 * 10 ** 12), '5 TB');
  assert.equal(bytes(-5), '0 B');
  assert.equal(rate(2_000_000), '2 MB/s');
});

test('a percentage has at most one decimal', () => {
  assert.equal(percent(12.34), '12,3 %');
  assert.equal(percent(0), '0 %');
});

test('the states of a server get a label and a colour, and an unknown one is a warning', () => {
  assert.deepEqual(statusInfo('running'), { label: 'En marcha', tone: 'ok' });
  assert.deepEqual(statusInfo('off'), { label: 'Apagado', tone: 'bad' });
  assert.deepEqual(statusInfo('starting'), { label: 'Arrancando', tone: 'warn' });
  assert.deepEqual(statusInfo('something-new'), { label: 'Desconocido', tone: 'warn' });
});

test('the traffic share is out over what the plan includes, never past the whole', () => {
  assert.equal(trafficShare({ out: 5, included: 20, in: 0 }), 0.25);
  assert.equal(trafficShare({ out: 30, included: 20, in: 0 }), 1);
  assert.equal(trafficShare({ out: 5, included: 0, in: 0 }), 0);
});

test('a line goes from the first to the last instant with the max at the top', () => {
  const points = [[0, 0], [50, 50], [100, 100]];
  assert.equal(linePoints(points, { width: 200, height: 100, max: 100 }), '0.0,100.0 100.0,50.0 200.0,0.0');
  assert.equal(linePoints(points, { width: 200, height: 100, max: 100, from: -100, to: 100 }), '100.0,100.0 150.0,50.0 200.0,0.0');
});

test('a value over the max is clipped, a flat zero stays at the bottom and one point draws nothing', () => {
  assert.equal(linePoints([[0, 500], [10, 0]], { width: 10, height: 10, max: 100 }), '0.0,0.0 10.0,10.0');
  assert.equal(linePoints([[0, 0], [10, 0]], { width: 10, height: 10 }), '0.0,10.0 10.0,10.0');
  assert.equal(linePoints([[0, 1]], { max: 1 }), '');
  assert.equal(linePoints([], { max: 1 }), '');
});

test('the latest value, the peak and the shared top of several series', () => {
  assert.equal(last([[1, 5], [2, 7]]), 7);
  assert.equal(last([]), 0);
  assert.equal(peak([[1, 5], [2, 9], [3, 2]]), 9);
  assert.equal(sharedMax([[1, 5]], [[1, 20]]), 20);
  assert.equal(sharedMax([], []), 1);
});

test('a month is named in Spanish', () => {
  assert.equal(monthName('2026-03'), 'marzo');
  assert.equal(monthName('2026-12'), 'diciembre');
});

test('a day becomes its month and year', () => {
  assert.equal(monthYear('2023-12-05'), 'diciembre de 2023');
});

test('the time on is days and hours, hours, or minutes', () => {
  assert.equal(uptime(90061), '1 d 1 h');
  assert.equal(uptime(7200), '2 h');
  assert.equal(uptime(1800), '30 min');
});

test('a load has two decimals', () => {
  assert.equal(load(0.5), '0,50');
  assert.equal(load(12), '12,00');
});
