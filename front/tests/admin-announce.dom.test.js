import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';
import { installApi, installDom, installStorage, json, settle } from './dom.js';

installStorage();
installDom('<main id="main"></main>');
const { closeAllModals } = await import('../js/ui/modal.js');
const { store } = await import('../js/pages/admin/components.js');
const announce = await import('../js/pages/admin/announce.js');

afterEach(() => closeAllModals());

const AUDIENCE = { ready: true, all: { devices: 2, users: 2 }, group: { devices: 1, users: 1 }, users: { 1: 1 }, telegram: { ready: true, group: true } };

async function open(extra = {}) {
  store.users = [{ id: 1, username: 'ana', telegram_id: 111 }];
  store.me = 1;
  const calls = installApi({ 'GET /manage/push/audience': AUDIENCE, ...extra });
  await announce.render(document.getElementById('main'));
  await settle();
  return { calls, form: document.getElementById('annForm') };
}

const type = (form, name, value) => {
  form.elements[name].value = value;
  form.dispatchEvent(new window.Event('input', { bubbles: true }));
};

test('Telegram is the channel it opens on, and the app one comes second', async () => {
  const { form } = await open();
  assert.equal(form.elements.channel.value, 'telegram');
  assert.deepEqual([...form.elements.channel.options].map((o) => o.value), ['telegram', 'push']);
});

test('a Telegram message is previewed with its Markdown drawn, and what is typed stays text', async () => {
  const { form } = await open();
  type(form, 'title', 'Novedades');
  type(form, 'body', '# Hola\n- **uno**\n- <b>dos</b> [guía](https://example.com)');
  const preview = document.getElementById('annPreviewBody');
  assert.equal(preview.querySelectorAll('strong').length, 2);
  assert.equal(preview.querySelectorAll('.adm-md-item').length, 2);
  assert.equal(preview.querySelector('a').getAttribute('href'), 'https://example.com');
  assert.equal(preview.querySelectorAll('b').length, 0);
  assert.match(preview.textContent, /<b>dos<\/b>/);
  assert.match(document.getElementById('annCount').textContent, /Telegram: \d+\/4000/);
});

test('the app channel is plain text with the short limit', async () => {
  const { form } = await open();
  form.elements.channel.value = 'push';
  form.elements.channel.dispatchEvent(new window.Event('change', { bubbles: true }));
  type(form, 'body', '**no** formato');
  assert.equal(form.elements.body.maxLength, 240);
  assert.equal(document.getElementById('annPreviewBody').textContent, '**no** formato');
  assert.match(document.getElementById('annSyntax').textContent, /texto plano/);
});

test('it sends the Markdown as typed to Telegram', async () => {
  const { calls, form } = await open({ 'POST /manage/telegram/announce': json({ message: 'Enviado a ana' }) });
  form.querySelector('#annAudience').value = 'me';
  type(form, 'title', 'Novedades');
  type(form, 'body', '- **uno**');
  form.dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }));
  await settle();
  const sent = calls.find((c) => c.method === 'POST');
  assert.equal(sent.path, '/manage/telegram/announce');
  assert.deepEqual(sent.body, { title: 'Novedades', body: '- **uno**', audience: 'me', user_id: null });
});

test('a message that drawn would not fit in a Telegram message is not sent', async () => {
  const { calls, form } = await open();
  form.querySelector('#annAudience').value = 'me';
  type(form, 'title', 'x');
  type(form, 'body', '---\n'.repeat(700));
  form.dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }));
  await settle();
  assert.equal(calls.filter((c) => c.method === 'POST').length, 0);
  assert.match(form.querySelector('.adm-error').textContent, /no cabe/);
});
