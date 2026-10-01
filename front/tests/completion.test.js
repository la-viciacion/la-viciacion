import assert from 'node:assert/strict';
import { test } from 'node:test';
import { blockedReason } from '../js/lib/completion.js';

test('a closed season names both seasons', () => {
  const text = blockedReason({ complete_blocked: 'closed_season', season: 2025 }, 2026);
  assert.match(text, /2025/);
  assert.match(text, /2026/);
});

test('a game already completed this season says so', () => {
  assert.match(blockedReason({ complete_blocked: 'completed_in_season', season: 2026 }, 2026), /otra plataforma/);
});

test('nothing blocks an entry that can be completed', () => {
  assert.equal(blockedReason({ complete_blocked: null, season: 2026 }, 2026), '');
});
