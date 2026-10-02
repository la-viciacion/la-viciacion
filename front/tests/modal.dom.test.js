import assert from 'node:assert/strict';
import { afterEach, beforeEach, mock, test } from 'node:test';
import { installDom } from './dom.js';

const window = installDom();
const { closeAllModals, modalHeader, openModal } = await import('../js/ui/modal.js');
const { toast } = await import('../js/ui/toast.js');
const { html } = await import('../js/lib/html.js');

beforeEach(() => mock.timers.enable({ apis: ['setTimeout'] }));
afterEach(() => {
  closeAllModals();
  mock.timers.reset();
});

const overlays = () => document.querySelectorAll('.modal-overlay').length;

test('the close button, a press outside, Escape and close() dismiss it, and onClose runs once each time', () => {
  let closed = 0;
  const open = () => openModal(html`${modalHeader('Título')}<p id="inside">dentro</p>`, { onClose: () => closed++ });

  open();
  assert.equal(document.querySelector('.modal-header h3').textContent, 'Título');
  document.querySelector('.modal-close').click();
  assert.equal(overlays(), 0);

  const modal = open();
  document.querySelector('#inside').dispatchEvent(new window.MouseEvent('mousedown', { bubbles: true }));
  assert.equal(overlays(), 1); // a press inside does not close it
  modal.el.dispatchEvent(new window.MouseEvent('mousedown', { bubbles: true }));
  assert.equal(overlays(), 0);

  open();
  document.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Escape' }));
  assert.equal(overlays(), 0);

  open().close();
  assert.equal(overlays(), 0);
  assert.equal(closed, 4);
});

test('closing twice does not run onClose twice, and Escape stops listening once closed', () => {
  let closed = 0;
  const modal = openModal(html`<p>x</p>`, { onClose: () => closed++ });
  modal.close();
  modal.close();
  document.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Escape' }));
  assert.equal(closed, 1);
});

test('closeAllModals dismisses every open one', () => {
  openModal(html`<p>a</p>`);
  openModal(html`<p>b</p>`, { wide: true });
  assert.equal(overlays(), 2);
  assert.equal(document.querySelectorAll('.modal-wide').length, 1);
  closeAllModals();
  assert.equal(overlays(), 0);
});

test('the content is escaped', () => {
  openModal(html`<p>${'<img src=x onerror=alert(1)>'}</p>`);
  assert.equal(document.querySelectorAll('.modal-content img').length, 0);
});

test('a toast shows its message with its type and disappears after a few seconds', () => {
  toast('Guardado');
  toast('Mal', 'err');
  const [ok, err] = document.querySelectorAll('.toast');
  assert.equal(ok.textContent, 'Guardado');
  assert.ok(ok.classList.contains('ok'));
  assert.ok(err.classList.contains('err'));
  assert.equal(ok.getAttribute('role'), 'status');
  mock.timers.tick(3499);
  assert.equal(document.querySelectorAll('.toast').length, 2);
  mock.timers.tick(1);
  assert.equal(document.querySelectorAll('.toast').length, 0);
});
