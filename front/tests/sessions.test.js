import assert from 'node:assert/strict';
import { test } from 'node:test';
import { fromInputValue, toInputValue } from '../js/lib/format.js';
import { current, isCurrent } from '../js/lib/seasons.js';
import { confirmQuestion, sessionProblem } from '../js/pages/home/sessions.js';

const NOW = new Date(2026, 8, 29, 20, 0); // Tue 29 Sep 2026 20:00 local

test('datetime-local helpers round trip', () => {
  assert.equal(toInputValue(new Date(2026, 8, 9, 3, 4, 5)), '2026-09-09T03:04');
  assert.equal(toInputValue('2026-09-29T13:05:07'), '2026-09-29T13:05');
  assert.equal(fromInputValue('2026-09-29T13:05'), '2026-09-29T13:05:00');
  assert.equal(fromInputValue('2026-09-29T13:05:30'), '2026-09-29T13:05:30');
});

test('seasons', () => {
  assert.equal(current(NOW), 2026);
  assert.equal(isCurrent(new Date(2026, 0, 1), NOW), true);
  assert.equal(isCurrent(new Date(2025, 11, 31, 23, 59), NOW), false);
});

test('a valid session has no problem', () => {
  assert.equal(sessionProblem('2026-09-29T10:00', '2026-09-29T11:30', NOW), null);
});

test('a new session asks how much time it adds', () => {
  assert.equal(confirmQuestion('Doom', '2026-09-29T10:00', '2026-09-29T11:30'), 'Vas a añadir 1 h 30 min a «Doom». ¿Es correcto?');
  assert.equal(confirmQuestion('Doom', '2026-09-29T10:00', '2026-09-29T10:45'), 'Vas a añadir 45 min a «Doom». ¿Es correcto?');
});

test('sessionProblem explains what is wrong', () => {
  assert.match(sessionProblem('', '2026-09-29T11:30', NOW), /inicio y el fin/);
  assert.match(sessionProblem('2026-09-29T11:30', '2026-09-29T11:30', NOW), /posterior/);
  assert.match(sessionProblem('2026-09-29T12:00', '2026-09-29T11:00', NOW), /posterior/);
  assert.match(sessionProblem('2026-09-29T19:00', '2026-09-29T21:00', NOW), /futuro/);
  assert.match(sessionProblem('2026-09-27T10:00', '2026-09-28T11:00', NOW), /24 horas/);
  assert.match(sessionProblem('2025-12-30T22:00', '2025-12-30T23:00', NOW), /temporada actual \(2026\)/);
});

test('exactly 24 hours is allowed, one minute more is not', () => {
  assert.equal(sessionProblem('2026-09-28T10:00', '2026-09-29T10:00', NOW), null);
  assert.match(sessionProblem('2026-09-28T09:59', '2026-09-29T10:00', NOW), /24 horas/);
});
