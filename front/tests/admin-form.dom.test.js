import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';
import { installDom, installStorage } from './dom.js';

installStorage();
installDom('<main id="main"></main>');
const { closeAllModals } = await import('../js/ui/modal.js');
const { openForm } = await import('../js/pages/admin/form.js');

afterEach(() => closeAllModals());

const entity = {
  createLabel: 'Nuevo',
  name: (r) => r.title,
  fields: [
    { key: 'title', label: 'Título', type: 'text' },
    { key: 'message', label: 'Mensaje', type: 'textarea', rows: 8 },
  ],
};

test('a textarea field is a multi-line box with the saved text and the rows its definition asks for', () => {
  openForm(entity, { title: 'T', message: 'Línea 1 <b>\nLínea 2' }, null);
  const box = document.getElementById('f_message');
  assert.equal(box.tagName, 'TEXTAREA');
  assert.equal(box.getAttribute('rows'), '8');
  assert.equal(box.value, 'Línea 1 <b>\nLínea 2');
  assert.equal(box.querySelector('b'), null); // text, never markup
  assert.equal(document.getElementById('f_title').tagName, 'INPUT');
});

test('with no rows given it still has a few', () => {
  openForm({ ...entity, fields: [{ key: 'message', label: 'Mensaje', type: 'textarea' }] }, { title: 'T', message: '' }, null);
  assert.equal(document.getElementById('f_message').getAttribute('rows'), '4');
});
