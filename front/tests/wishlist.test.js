import assert from 'node:assert/strict';
import { test } from 'node:test';
import { countdown, releaseLine, wantedBy } from '../js/lib/wishlist.js';

test('the countdown speaks of days, then of months, and of a missing date', () => {
  assert.equal(countdown({ release_date: null, days_until: null }), 'Sin fecha confirmada');
  assert.equal(countdown({ release_date: '2026-10-04', days_until: null }), 'Sale hoy');
  assert.equal(countdown({ release_date: '2026-10-05', days_until: 1 }), 'Mañana');
  assert.equal(countdown({ release_date: '2026-10-14', days_until: 10 }), 'En 10 días');
  assert.equal(countdown({ release_date: '2026-12-03', days_until: 60 }), 'En 60 días');
  assert.equal(countdown({ release_date: '2027-03-01', days_until: 148 }), 'En 5 meses');
});

test('the release line adds the date only when there is one', () => {
  assert.equal(releaseLine({ release_date: null, days_until: null }), 'Sin fecha confirmada');
  assert.match(releaseLine({ release_date: '2026-10-14', days_until: 10 }), /^En 10 días · /);
});

test('who else wants a game, in singular and plural', () => {
  assert.equal(wantedBy([]), '');
  assert.equal(wantedBy([{ name: 'Bea' }]), 'Lo quiere Bea');
  assert.equal(wantedBy([{ name: 'Bea' }, { name: 'Cai' }]), 'Lo quieren Bea y Cai');
});
