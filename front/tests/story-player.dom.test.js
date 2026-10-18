import assert from 'node:assert/strict';
import { mock, test } from 'node:test';
import { installDom } from './dom.js';
import { html } from '../js/lib/html.js';

const window = installDom('<div id="root"></div>', 'http://localhost/');
globalThis.document = window.document;
const { createStoryPlayer } = await import('../js/ui/story-player.js');

const SLIDES = [
  { id: 'one', theme: 'teal' },
  { id: 'two', theme: 'gold' },
  { id: 'three', theme: 'pink' },
];

function start(overrides = {}) {
  const calls = { closed: 0, changes: [] };
  const container = document.getElementById('root');
  const player = createStoryPlayer({
    container, slides: SLIDES, render: (slide) => html`<p>${slide.id}</p><button type="button" id="inside">hi</button>`,
    onClose: () => { calls.closed += 1; }, onChange: (i) => calls.changes.push(i), ...overrides,
  });
  const stage = container.querySelector('.st-stage');
  stage.getBoundingClientRect = () => ({ left: 0, width: 300 });
  return { player, stage, calls, container };
}

const event = (type, props = {}) => Object.assign(new window.Event(type, { bubbles: true }), props);
const press = (target, x) => target.dispatchEvent(event('pointerdown', { clientX: x }));
const release = (target, x) => target.dispatchEvent(event('pointerup', { clientX: x }));
const slideId = (container) => container.querySelector('.st-slide p').textContent;
const barClasses = (container) => [...container.querySelectorAll('.st-bar')].map((b) => b.className);

test('it starts on the first slide with its bar running and the others waiting', () => {
  const { player, stage, container } = start();
  assert.equal(slideId(container), 'one');
  assert.equal(stage.dataset.theme, 'teal');
  assert.deepEqual(barClasses(container), ['st-bar active', 'st-bar', 'st-bar']);
  player.destroy();
});

test('when the bar of a slide ends the next one comes up, and the last one stays', () => {
  const { player, stage, container } = start();
  const fill = (i) => container.querySelectorAll('.st-bar i')[i];
  fill(0).dispatchEvent(event('animationend'));
  assert.equal(slideId(container), 'two');
  assert.deepEqual(barClasses(container), ['st-bar done', 'st-bar active', 'st-bar']);
  fill(1).dispatchEvent(event('animationend'));
  assert.equal(slideId(container), 'three');
  assert.deepEqual(barClasses(container), ['st-bar done', 'st-bar done', 'st-bar done']);
  fill(2).dispatchEvent(event('animationend'));
  assert.equal(slideId(container), 'three');
  assert.equal(stage.dataset.slide, 'three');
  player.destroy();
});

test('a tap on the right goes on, on the left goes back, and on the first slide the left starts over', () => {
  const { player, stage, container, calls } = start();
  press(stage, 250);
  release(stage, 250);
  assert.equal(slideId(container), 'two');
  press(stage, 20);
  release(stage, 20);
  assert.equal(slideId(container), 'one');
  press(stage, 20);
  release(stage, 20);
  assert.equal(slideId(container), 'one');
  assert.deepEqual(calls.changes, [0, 1, 0, 0]);
  player.destroy();
});

test('a swipe changes slide and a long press only pauses', () => {
  mock.timers.enable({ apis: ['setTimeout'] });
  const { player, stage, container } = start();
  press(stage, 200);
  release(stage, 120); // 80 px to the left
  assert.equal(slideId(container), 'two');
  press(stage, 100);
  release(stage, 190); // to the right
  assert.equal(slideId(container), 'one');
  press(stage, 250);
  mock.timers.tick(200);
  assert.equal(stage.classList.contains('paused'), true);
  assert.equal(container.querySelector('.st-bar i').style.animationPlayState, 'paused');
  release(stage, 250);
  assert.equal(slideId(container), 'one', 'letting go after holding does not change slide');
  assert.equal(stage.classList.contains('paused'), false);
  mock.timers.reset();
  player.destroy();
});

test('a button inside a slide is not a tap', () => {
  const { player, stage, container } = start();
  const button = container.querySelector('#inside');
  button.dispatchEvent(event('pointerdown', { clientX: 250 }));
  button.dispatchEvent(event('pointerup', { clientX: 250 }));
  assert.equal(slideId(container), 'one');
  assert.equal(stage.classList.contains('paused'), false);
  player.destroy();
});

test('the mouse over the story pauses it and a finger does not', () => {
  const { player, stage } = start();
  stage.dispatchEvent(event('pointerenter', { pointerType: 'touch' }));
  assert.equal(stage.classList.contains('paused'), false);
  stage.dispatchEvent(event('pointerenter', { pointerType: 'mouse' }));
  assert.equal(stage.classList.contains('paused'), true);
  stage.dispatchEvent(event('pointerleave', { pointerType: 'mouse' }));
  assert.equal(stage.classList.contains('paused'), false);
  player.destroy();
});

test('the arrows, space and Escape work, and stop working once it is destroyed', () => {
  const { player, container, calls } = start();
  const key = (k) => document.dispatchEvent(event('keydown', { key: k }));
  key('ArrowRight');
  assert.equal(slideId(container), 'two');
  key(' ');
  assert.equal(slideId(container), 'three');
  key('ArrowLeft');
  assert.equal(slideId(container), 'two');
  key('Escape');
  assert.equal(calls.closed, 1);
  player.destroy();
  key('ArrowRight');
  assert.equal(slideId(container), 'two');
  key('Escape');
  assert.equal(calls.closed, 1);
});

test('the close button leaves', () => {
  const { player, container, calls } = start();
  container.querySelector('.st-close').click();
  assert.equal(calls.closed, 1);
  player.destroy();
});

test('go() jumps to a slide and ignores one that does not exist', () => {
  const { player, container } = start();
  player.go(2);
  assert.equal(player.index, 2);
  player.go(7);
  player.go(-1);
  assert.equal(slideId(container), 'three');
  player.destroy();
});
