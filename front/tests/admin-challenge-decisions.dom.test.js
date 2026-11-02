import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';
import { installApi, installDom, installStorage, settle } from './dom.js';

installStorage();
installDom('<main id="main"></main>');
const { closeAllModals } = await import('../js/ui/modal.js');
const { approveProposal, rejectProposal } = await import('../js/pages/admin/challenge-decisions.js');
const { ENTITIES } = await import('../js/pages/admin/entities.js');
const { SECTIONS } = await import('../js/pages/admin/nav.js');

afterEach(() => closeAllModals());

const proposal = { id: 7, title: 'Temático: <b>Horror</b>', label: 'Temático', status: 'pending', proposer: { id: 2, name: 'Bea' } };

test('approving asks who takes part and whether to tell the group, and sends both', async () => {
  const calls = installApi({ 'POST /manage/challenge-proposals/7/approve': { id: 7, status: 'approved' } });
  let reloaded = 0;
  approveProposal(proposal, { reload: async () => { reloaded += 1; } });
  assert.match(document.querySelector('.modal-header').textContent, /Aprobar · Temático:/);
  assert.equal(document.querySelectorAll('.modal-content b').length, 0); // the title is text
  assert.match(document.querySelector('.modal-content').textContent, /Propuesto por Bea/);
  const form = document.querySelector('.modal-content form');
  assert.equal(form.elements.announce.checked, true);
  form.elements.participation.value = 'opt_in';
  form.elements.announce.checked = false;
  form.requestSubmit();
  await settle();
  assert.deepEqual(calls[0].body, { participation: 'opt_in', announce: false });
  assert.equal(reloaded, 1);
});

test('an error of the API stays in the window and nothing reloads', async () => {
  installApi({ 'POST /manage/challenge-proposals/7/approve': () => { throw new Error('Ese mes ya ha pasado'); } });
  let reloaded = 0;
  approveProposal(proposal, { reload: async () => { reloaded += 1; } });
  document.querySelector('.modal-content form').requestSubmit();
  await settle();
  assert.match(document.querySelector('.adm-error').textContent, /Ese mes ya ha pasado/);
  assert.equal(reloaded, 0);
});

test('rejecting sends the note, and none when it is left empty', async () => {
  const calls = installApi({ 'POST /manage/challenge-proposals/7/reject': { id: 7, status: 'rejected' } });
  rejectProposal(proposal, { reload: async () => {} });
  const form = document.querySelector('.modal-content form');
  form.elements.note.value = '  Mejor en noviembre ';
  form.requestSubmit();
  await settle();
  assert.deepEqual(calls[0].body, { note: 'Mejor en noviembre' });
  rejectProposal(proposal, { reload: async () => {} });
  document.querySelector('.modal-content form').requestSubmit();
  await settle();
  assert.deepEqual(calls.at(-1).body, { note: null });
});

test('the panel lists the proposals in their own tab, the schedules under the challenges, and only a waiting proposal can be decided', () => {
  assert.ok(SECTIONS.find((s) => s.label === 'Retos').tabs.includes('proposals'));
  assert.ok(!SECTIONS.find((s) => s.label === 'Retos').tabs.includes('schedules'));
  assert.equal(ENTITIES.challenges.companion, 'schedules');
  const { actions } = ENTITIES.proposals;
  assert.deepEqual(actions.map((a) => a.show({ status: 'pending' })), [true, true]);
  assert.deepEqual(actions.map((a) => a.show({ status: 'approved' })), [false, false]);
});

test('a themed challenge can repeat every month; a game could too (not offered for now), and a rotation needs its games', () => {
  const [game, , themed] = ENTITIES.challenges.creates;
  assert.deepEqual([game.repeat, themed.repeat], ['/manage/challenge-schedules', '/manage/challenge-schedules']);
  const games = game.fields.find((f) => f.key === 'games');
  assert.deepEqual([games.type, games.required, games.when], ['games', true, { key: 'period', is: 'repeat' }]);
  assert.deepEqual(game.fields.find((f) => f.key === 'game_id').when, { key: 'period', not: 'repeat' });
  assert.ok(!game.fields.find((f) => f.type === 'period').repeatable); // not offered for now
  assert.deepEqual(ENTITIES.schedules.fields.map((f) => f.key), ['label', 'active', 'announce', 'participation', 'games']);
});

test('the challenges have one button and the type is chosen in the form', () => {
  const { createLabel, creates } = ENTITIES.challenges;
  assert.equal(createLabel, 'Lanzar reto');
  assert.ok(creates.every((c) => c.choose && c.body.kind));
  assert.deepEqual(creates.map((c) => c.choose), ['Reto de juego', 'Horas entre todos', 'Reto temático']);
  assert.equal(ENTITIES.schedules.creates, undefined);
});
