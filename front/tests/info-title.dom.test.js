import assert from 'node:assert/strict';
import { test } from 'node:test';
import { installDom } from './dom.js';

installDom('<div id="root"></div>');
const { html, mount } = await import('../js/lib/html.js');
const { cardTitle, infoTip } = await import('../js/ui/info-tip.js');
const { sectionTitle, titleView } = await import('../js/ui/profile-summary.js');

const root = () => document.getElementById('root');
const draw = (template) => {
  mount(root(), template);
  return root();
};

test('a card title with an "i" opens its explanation on a tap and has it ready for who reads it, without showing it', () => {
  const el = draw(cardTitle('Chat', html`Una frase con <code>código</code>.`));
  const head = el.querySelector('.pf-info-head.pf-info-title');
  assert.equal(head.querySelector('h3').textContent, 'Chat');
  const details = head.querySelector('details.pf-info');
  assert.equal(details.open, false, 'folded until it is wanted');
  assert.equal(details.querySelector('summary').getAttribute('aria-label'), 'Más información: Chat');
  assert.equal(details.querySelector('.pf-info-text code').textContent, 'código');
});

test('a section title has the "i" beside the title and keeps its line, and without information it is as it was', () => {
  const withInfo = draw(sectionTitle('Tu gasto', 'x', 'Lo que has usado.'));
  assert.equal(withInfo.querySelector('.section-header').id, 'x');
  assert.equal(withInfo.querySelector('.pf-info-title h2.section-title').textContent, 'Tu gasto');
  assert.ok(withInfo.querySelector('.section-header > .section-line'), 'the line goes on after the title and its "i"');
  const plain = draw(sectionTitle('Modelo'));
  assert.equal(plain.querySelector('.pf-info'), null);
  assert.equal(plain.querySelector('.section-header').children.length, 2);
  assert.equal(draw(titleView('Algo')).children.length, 2);
});

test('what is written in the explanation is escaped, so a name in it cannot add markup', () => {
  const el = draw(cardTitle('Aviso', '<img src=x onerror=alert(1)>'));
  assert.equal(el.querySelector('img'), null);
  assert.match(el.querySelector('.pf-info-text').textContent, /<img src=x/);
  assert.equal(draw(infoTip('Texto')).querySelector('summary').getAttribute('aria-label'), 'Más información');
});
