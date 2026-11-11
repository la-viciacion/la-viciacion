import assert from 'node:assert/strict';
import { test } from 'node:test';
import { menuPages } from '../js/lib/menu.js';
import { fold, matchBy, matchPages, matchPlayers } from '../js/lib/search.js';

test('folding ignores case and accents', () => {
  assert.equal(fold('  José TÚ '), 'jose tu');
  assert.equal(fold(null), '');
});

test('a page is found by the start of its name or of one of its words, the start of the name first', () => {
  const pages = menuPages({ is_admin: false });
  assert.deepEqual(matchPages('ju', pages).map((p) => p.id), ['players', 'games', 'settings']); // "Ajustes" only contains it: last
  assert.deepEqual(matchPages('perfil', pages).map((p) => p.id), ['profile']); // "Mi perfil": a word of the name
  assert.deepEqual(matchPages('RECOMEN', pages).map((p) => p.id), ['recommendations']);
});

test('the administration is only found by an admin', () => {
  assert.deepEqual(matchPages('admin', menuPages({ is_admin: false })), []);
  assert.deepEqual(matchPages('admin', menuPages({ is_admin: true })).map((p) => p.id), ['admin']);
});

test('players are found by name or username, accents ignored', () => {
  const players = [{ name: 'Álvaro', username: 'alv' }, { name: 'Marta', username: 'jmar' }, { name: 'Jaime', username: 'jai' }];
  assert.deepEqual(matchPlayers('alva', players).map((p) => p.name), ['Álvaro']);
  assert.deepEqual(matchPlayers('j', players).map((p) => p.name), ['Marta', 'Jaime']); // a username that starts with it ties with a name that does: the order of the list
  assert.deepEqual(matchPlayers('zzz', players), []);
});

test('nothing is found for an empty query, and the list is cut at the limit', () => {
  const items = Array.from({ length: 9 }, (_, i) => ({ label: `Juego ${i}` }));
  assert.deepEqual(matchBy('  ', items, ['label']), []);
  assert.equal(matchBy('juego', items, ['label']).length, 5);
  assert.equal(matchBy('juego', items, ['label'], 3).length, 3);
});
