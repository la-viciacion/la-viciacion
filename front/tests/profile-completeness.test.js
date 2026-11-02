import assert from 'node:assert/strict';
import { test } from 'node:test';
import { installStorage } from './dom.js';

installStorage();
const { GIVE_UP_DAYS, WAIT_DAYS, fillHref, markComplete, markShown, mayAsk, missingSteps, missingText, needsSettings, percent, snooze } = await import('../js/lib/profile-completeness.js');

const DAY = 24 * 60 * 60 * 1000;
const START = new Date(2026, 10, 2);
const later = (days) => new Date(START.getTime() + days * DAY);

test('the photo, the city and the birth date are what a profile lacks, and the percentage follows', () => {
  const full = { place_name: 'Valencia', birth_date: '1990-05-01' };
  assert.deepEqual(missingSteps({ hasAvatar: true, settings: full }), []);
  assert.deepEqual(missingSteps({ hasAvatar: false, settings: { place_name: null, birth_date: null } }), ['photo', 'place', 'birth']);
  assert.deepEqual(missingSteps({ hasAvatar: true, settings: { ...full, place_name: null } }), ['place']);
  assert.deepEqual([[], ['photo'], ['photo', 'place'], ['photo', 'place', 'birth']].map(percent), [100, 67, 33, 0]);
});

test('it says what is missing in the singular and the plural, and where to fill it', () => {
  assert.equal(missingText(['photo']), 'Te falta la foto');
  assert.equal(missingText(['place', 'birth']), 'Te faltan la ciudad y la fecha de nacimiento');
  assert.equal(missingText(['photo', 'place', 'birth']), 'Te faltan la foto, la ciudad y la fecha de nacimiento');
  assert.equal(fillHref(['photo', 'birth']), '#/profile/resumen');
  assert.equal(fillHref(['birth']), '#/profile/ajustes/perfil');
  assert.equal(needsSettings(['photo']), false);
  assert.equal(needsSettings(['photo', 'place']), true);
});

test('every answer waits a week, and a month after the first time it stops for good', () => {
  localStorage.removeItem('lv-profile-invite-ana');
  assert.deepEqual([WAIT_DAYS, GIVE_UP_DAYS], [7, 30]);
  assert.equal(mayAsk('ana', START), true);
  markShown('ana', START);
  assert.equal(mayAsk('ana', START), true, 'being on screen is not an answer');
  snooze('ana', later(1)); // answered a day after it came up: the wait runs from the answer
  assert.equal(mayAsk('ana', later(7)), false);
  assert.equal(mayAsk('ana', later(8)), true);
  snooze('ana', later(8));
  assert.equal(mayAsk('ana', later(14)), false);
  assert.equal(mayAsk('ana', later(15)), true);
  snooze('ana', later(15));
  snooze('ana', later(22));
  assert.equal(mayAsk('ana', later(29)), true, 'still inside the month');
  snooze('ana', later(29));
  assert.equal(mayAsk('ana', later(36)), false, 'the month is over');
  assert.equal(mayAsk('ana', later(3650)), false);
});

test('the month counts from the first time even if the bar is never answered', () => {
  localStorage.removeItem('lv-profile-invite-ana');
  markShown('ana', START);
  markShown('ana', later(20)); // a second showing does not move the start
  assert.equal(mayAsk('ana', later(29)), true);
  assert.equal(mayAsk('ana', later(31)), false);
});

test('a complete profile is never asked about again, and each player has their own wait', () => {
  localStorage.removeItem('lv-profile-invite-ana');
  localStorage.removeItem('lv-profile-invite-ben');
  snooze('ben', START);
  assert.equal(mayAsk('ana', START), true);
  markComplete('ana');
  assert.equal(mayAsk('ana', later(1000)), false);
});

test('a storage that holds rubbish asks as if nothing was answered', () => {
  localStorage.setItem('lv-profile-invite-cy', '{not json');
  assert.equal(mayAsk('cy', START), true);
});
