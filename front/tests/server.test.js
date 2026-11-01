import assert from 'node:assert/strict';
import { test } from 'node:test';
import { barLayout, bytes, last, load, money, monthName, monthShort, monthTotal, monthYear, uptime, yearTotals, linePoints, peak, percent, rate, sharedMax, trafficShare } from '../js/lib/server.js';

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

test('an amount always shows its cents', () => {
  assert.equal(money(2).replace(/\s/g, ' '), '2,00 €');
  assert.equal(money(120.25).replace(/\s/g, ' '), '120,25 €');
  assert.equal(money(1234.5).replace(/\s/g, ' '), '1234,50 €');
});

const m = (month, kinds, forecast = 0, state = 'closed') => ({ month, state, kinds, forecast });

test('a month is short in three letters and counts its forecast in the whole', () => {
  assert.equal(monthShort('2026-09'), 'sep');
  assert.equal(monthTotal(m('2026-10', { server: 2, domain: 0.5 }, 3)), 5.5);
});

test('a year adds what was spent and, with the forecast, what it will have cost', () => {
  const months = [m('2026-01', { server: 4 }), m('2026-02', { server: 1 }, 3, 'running'), m('2026-03', { server: 0 }, 4, 'future')];
  assert.deepEqual(yearTotals(months), { so_far: 5, projected: 12 });
});

test('the bars are shares of the tallest month, the kinds stacked in order and the forecast on top', () => {
  const months = [m('2026-01', { domain: 1, server: 3 }), m('2026-02', { server: 1 }, 1, 'running'), m('2026-03', { server: 0 }, 0, 'future')];
  const bars = barLayout(months);
  assert.equal(bars.length, 3);
  assert.deepEqual(bars[0].segments, [{ kind: 'server', share: 0.75 }, { kind: 'domain', share: 0.25 }]); // the server first, whatever the order of the keys
  assert.equal(bars[0].forecast, null);
  assert.deepEqual(bars[1].segments, [{ kind: 'server', share: 0.25 }]);
  assert.equal(bars[1].forecast, 0.25);
  assert.deepEqual(bars[1].state, 'running');
  assert.deepEqual(bars[2].segments, []); // a month with nothing is no bar
});

test('with nothing at all the layout does not divide by zero', () => {
  const [bar] = barLayout([m('2026-01', { server: 0 })]);
  assert.deepEqual(bar.segments, []);
  assert.equal(bar.forecast, null);
});
