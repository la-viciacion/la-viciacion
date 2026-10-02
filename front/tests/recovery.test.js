import assert from 'node:assert/strict';
import { test } from 'node:test';
import { RESET_ROUTE, isResetRoute, resetTokenFromHash } from '../js/lib/recovery.js';

test('the recovery route is recognised with or without a token', () => {
  assert.equal(isResetRoute('#/reset-password?token=abc'), true);
  assert.equal(isResetRoute(RESET_ROUTE), true);
  assert.equal(isResetRoute('#/profile'), false);
  assert.equal(isResetRoute('#/reset-passwords'), false);
  assert.equal(isResetRoute(''), false);
});

test('the token is read from the fragment', () => {
  assert.equal(resetTokenFromHash('#/reset-password?token=abc-DEF_123'), 'abc-DEF_123');
});

test('no token, an empty token or no query give null', () => {
  assert.equal(resetTokenFromHash('#/reset-password'), null);
  assert.equal(resetTokenFromHash('#/reset-password?token='), null);
  assert.equal(resetTokenFromHash('#/reset-password?other=1'), null);
});

test('the token is taken as is, not decoded twice', () => {
  assert.equal(resetTokenFromHash('#/reset-password?token=a%2Bb'), 'a+b');
});
