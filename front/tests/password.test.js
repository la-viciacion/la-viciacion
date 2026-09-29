import assert from 'node:assert/strict';
import { test } from 'node:test';
import { generatePassword, isValidPassword } from '../js/lib/password.js';

test('isValidPassword enforces the API rules', () => {
  assert.equal(isValidPassword('Abcdefghij1!'), true);
  assert.equal(isValidPassword('Abcdefghij1'), false); // no special character
  assert.equal(isValidPassword('abcdefghij1!'), false); // no uppercase
  assert.equal(isValidPassword('ABCDEFGHIJ1!'), false); // no lowercase
  assert.equal(isValidPassword('Abcdefghijk!'), false); // no digit
  assert.equal(isValidPassword('Abc1!'), false); // too short
  assert.equal(isValidPassword('Abcdefghijklmnopqrstuvw1!'), false); // too long (25)
});

test('generatePassword always satisfies the rules', () => {
  for (let i = 0; i < 500; i++) assert.equal(isValidPassword(generatePassword()), true);
});
