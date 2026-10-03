import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';
import { installDom } from './dom.js';

const window = installDom('<button id="menuBtn" aria-expanded="false">menu</button>');
globalThis.location = window.location;
const { closeMenu, mountMenu } = await import('../js/ui/menu.js');

let logouts = 0;
mountMenu(document.getElementById('menuBtn'), { user: { is_admin: true }, onLogout: () => logouts++ });

afterEach(() => { closeMenu(); window.location.hash = ''; });

const button = () => document.getElementById('menuBtn');
const panel = () => document.querySelector('.menu-panel');

test('the button opens the panel with the sections and tells the state', () => {
  button().click();
  assert.ok(panel());
  assert.equal(button().getAttribute('aria-expanded'), 'true');
  assert.deepEqual([...document.querySelectorAll('.menu-section')].map((e) => e.textContent), ['Principal', 'Explorar', 'Tú', 'Administración']);
  assert.equal(document.querySelectorAll('a.menu-item').length, 9);
  assert.equal(document.querySelector('.menu-wip').textContent, 'WIP');
});

test('it highlights the page it is on and puts the focus there', () => {
  window.location.hash = '#/group';
  button().click();
  assert.equal(document.querySelector('a.menu-item.active').textContent.trim(), 'Grupo');
  assert.equal(document.querySelector('a.menu-item.active').getAttribute('aria-current'), 'page');
  assert.equal(document.activeElement, document.querySelector('a.menu-item.active'));
});

test('Escape, the close button, a press outside and choosing a page close it', () => {
  for (const close of [
    () => document.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Escape' })),
    () => document.querySelector('.menu-close').click(),
    () => document.querySelector('.menu-overlay').dispatchEvent(new window.MouseEvent('click', { bubbles: true })),
    () => document.querySelector('a.menu-item').click(),
  ]) {
    button().click();
    assert.ok(panel());
    close();
    assert.equal(panel(), null);
    assert.equal(button().getAttribute('aria-expanded'), 'false');
  }
});

test('pressing the button again closes it, and a press inside the panel does not', () => {
  button().click();
  panel().click();
  assert.ok(panel());
  button().click();
  assert.equal(panel(), null);
});

test('"Cerrar sesión" closes the menu and ends the session', () => {
  button().click();
  document.getElementById('menuLogout').click();
  assert.equal(panel(), null);
  assert.equal(logouts, 1);
});
