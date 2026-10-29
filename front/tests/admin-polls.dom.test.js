import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';
import { installApi, installDom, installStorage, settle } from './dom.js';

installStorage();
installDom('<main id="main"></main>');
const { closeAllModals } = await import('../js/ui/modal.js');
const { closePoll } = await import('../js/pages/admin/poll-actions.js');
const { ENTITIES } = await import('../js/pages/admin/entities.js');
const { SECTIONS } = await import('../js/pages/admin/nav.js');
const { describe } = await import('../js/pages/admin/audit-labels.js');

afterEach(() => closeAllModals());

const poll = (extra = {}) => ({
  id: 4, question: '¿A qué <b>jugamos</b>?', multiple: false, status: 'open', closes_at: null, closed_at: null, telegram_stopped: false, missed_votes: false,
  voters: 3, winners: [0],
  options: [
    { text: 'Hades', votes: 2, voters: [{ user_id: 1, name: 'Ana' }, { user_id: null, name: null }] },
    { text: 'Celeste', votes: 1, voters: [{ user_id: 2, name: 'Bea' }] },
  ],
  ...extra,
});

test('the polls are listed under the notifications and launched with a question, its options, a choice of several and a deadline', () => {
  assert.ok(SECTIONS.find((s) => s.label === 'Notificaciones').tabs.includes('polls'));
  assert.ok(!SECTIONS.find((s) => s.label === 'Jugadores').tabs.includes('polls'));
  const [create] = ENTITIES.polls.creates;
  assert.deepEqual(create.fields.map((f) => [f.key, f.type]), [['question', 'text'], ['options', 'options'], ['multiple', 'checkbox'], ['closes_at', 'datetime']]);
  assert.deepEqual(create.fields.filter((f) => f.required).map((f) => f.key), ['question', 'options']);
});

test('the options are rows of the launch form itself, added one by one, and are sent cleaned', async () => {
  const { openForm } = await import('../js/pages/admin/form.js');
  const calls = installApi({ 'POST /manage/polls': poll() });
  openForm(ENTITIES.polls, null, { reload: async () => {} }, ENTITIES.polls.creates[0]);
  assert.equal(document.querySelectorAll('.modal-overlay').length, 1); // no window over the window
  const rows = () => document.querySelectorAll('#f_options input');
  assert.equal(rows().length, 2);
  document.getElementById('f_question').value = '¿A qué jugamos?';
  rows()[0].value = ' Hades ';
  document.querySelector('form').requestSubmit(); // one is not enough
  assert.match(document.querySelector('.adm-error').textContent, /al menos 2/);
  document.querySelector('[data-optionadd]').click();
  assert.equal(rows().length, 3);
  rows()[1].value = 'Celeste';
  rows()[2].value = '  ';
  document.querySelector('[data-optionremove]').click(); // drops Hades
  assert.equal(rows().length, 2);
  rows()[1].value = 'Hollow Knight';
  document.querySelector('form').requestSubmit();
  await settle();
  assert.deepEqual(calls[0].body.options, ['Celeste', 'Hollow Knight']);
});

test('only an open poll can be closed, and a closed one Telegram did not stop can be stopped again', () => {
  const [close, retry] = ENTITIES.polls.actions;
  assert.deepEqual([close.show(poll()), retry.show(poll())], [true, false]);
  assert.deepEqual([close.show(poll({ status: 'closed', telegram_stopped: false })), retry.show(poll({ status: 'closed', telegram_stopped: false }))], [false, true]);
  assert.deepEqual([close.show(poll({ status: 'closed', telegram_stopped: true })), retry.show(poll({ status: 'closed', telegram_stopped: true }))], [false, false]);
});

test('closing asks whether to tell the group and sends the choice', async () => {
  const calls = installApi({ 'POST /manage/polls/4/close': poll({ status: 'closed', telegram_stopped: true }) });
  let reloaded = 0;
  closePoll(poll(), { reload: async () => { reloaded += 1; } });
  assert.match(document.querySelector('.modal-header').textContent, /Cerrar · ¿A qué <b>jugamos<\/b>\?/);
  assert.equal(document.querySelectorAll('.modal-content b').length, 0); // the question is text
  const form = document.querySelector('.modal-content form');
  assert.equal(form.elements.announce.checked, true);
  form.elements.announce.checked = false;
  form.requestSubmit();
  await settle();
  assert.deepEqual(calls[0].body, { announce: false });
  assert.equal(reloaded, 1);
});

test('trying again on a poll already closed announces nothing and does not ask', async () => {
  const calls = installApi({ 'POST /manage/polls/4/close': poll({ status: 'closed', telegram_stopped: true }) });
  closePoll(poll({ status: 'closed' }), { reload: async () => {} });
  const form = document.querySelector('.modal-content form');
  assert.equal(form.elements.announce, undefined);
  form.requestSubmit();
  await settle();
  assert.deepEqual(calls[0].body, { announce: false });
});

test('a failure stays in the window and nothing reloads', async () => {
  installApi({ 'POST /manage/polls/4/close': () => { throw new Error('Encuesta no encontrado'); } });
  let reloaded = 0;
  closePoll(poll(), { reload: async () => { reloaded += 1; } });
  document.querySelector('.modal-content form').requestSubmit();
  await settle();
  assert.match(document.querySelector('.adm-error').textContent, /Encuesta no encontrado/);
  assert.equal(reloaded, 0);
});

test('the table shows the votes with who gave them (escaped), the winner and what is wrong', () => {
  const [question, result, state, limit] = ENTITIES.polls.columns;
  assert.equal(question.label, 'Encuesta');
  const text = (column, row) => {
    const box = document.createElement('div');
    box.innerHTML = String(column.render(row)); // the markup the table would put in a cell
    return box;
  };
  const shown = text(result, poll());
  assert.match(shown.textContent, /🏆 Hades · 2 votos/);
  assert.match(shown.textContent, /Ana, sin cuenta/);
  assert.doesNotMatch(shown.textContent, /🏆 Celeste/);
  assert.equal(text(question, poll()).querySelectorAll('b').length, 0);
  assert.match(text(state, poll()).textContent, /Abierta/);
  assert.match(text(state, poll({ status: 'closed', telegram_stopped: false, missed_votes: true })).textContent, /Cerrada.*Sigue abierta en Telegram.*Faltan votos/);
  assert.equal(text(limit, poll()).textContent, 'A mano');
});

test('launching and closing a poll read as sentences in the audit log', () => {
  assert.equal(describe({ method: 'POST', path: '/api/v1/manage/polls', entity: 'polls', entity_id: '4' }), 'Lanzó una encuesta al grupo');
  assert.equal(describe({ method: 'POST', path: '/api/v1/manage/polls/4/close', entity: 'polls', entity_id: '4' }), 'Cerró una encuesta del grupo');
  assert.equal(describe({ method: 'DELETE', path: '/api/v1/manage/polls/4', entity: 'polls', entity_id: '4' }), 'Borró encuesta #4');
});
