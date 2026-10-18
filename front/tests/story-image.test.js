import assert from 'node:assert/strict';
import { test } from 'node:test';
import { installDom } from './dom.js';

installDom('<main></main>', 'http://localhost/');
const { HEIGHT, WIDTH, cardBlob, paintCard, shareImage, wrapText } = await import('../js/ui/story-image.js');

const CARD = { theme: 'gold', kicker: 'He jugado', title: '61 horas', lines: ['+21 h frente a agosto', '24 sesiones'], covers: [], footer: 'septiembre de 2026' };

// A canvas context that only remembers what was drawn
function fakeContext() {
  const drawn = [];
  return {
    drawn, font: '', measureText: (text) => ({ width: String(text).length * 10 }), createLinearGradient: () => ({ addColorStop() {} }),
    fillText: (text) => drawn.push(text), fillRect() {}, save() {}, restore() {}, clip() {}, beginPath() {}, roundRect() {}, drawImage: (...args) => drawn.push(['image', args.length]),
  };
}

test('text is wrapped by words to the width, and a word too long stays whole', () => {
  const measure = (text) => text.length * 10;
  assert.deepEqual(wrapText(measure, 'uno dos tres cuatro', 80), ['uno dos', 'tres', 'cuatro']);
  assert.deepEqual(wrapText(measure, 'extraordinariamente largo', 50), ['extraordinariamente', 'largo']);
  assert.deepEqual(wrapText(measure, '', 50), []);
});

test('the card paints the brand, the kicker in capitals, the title, the lines and the footer', () => {
  const ctx = fakeContext();
  paintCard(ctx, CARD, []);
  assert.deepEqual(ctx.drawn, ['LA VICIACIÓN', 'HE JUGADO', '61 horas', '+21 h frente a agosto', '24 sesiones', 'septiembre de 2026']);
});

test('the covers are drawn, and a missing one leaves its place with the placeholder', () => {
  const ctx = fakeContext();
  paintCard(ctx, { ...CARD, covers: ['a', null] }, [{ width: 300, height: 200 }, null]);
  assert.equal(ctx.drawn.filter((d) => Array.isArray(d)).length, 1);
  assert.ok(ctx.drawn.includes('🎮'));
});

const fakeCanvas = (failFirst) => {
  let attempts = 0;
  return {
    width: WIDTH, height: HEIGHT, getContext: () => fakeContext(),
    toBlob(callback) {
      attempts += 1;
      if (failFirst && attempts === 1) throw new Error('tainted');
      callback(new Blob(['png'], { type: 'image/png' }));
    },
  };
};

test('the blob is the PNG of the canvas', async () => {
  const blob = await cardBlob(CARD, { load: async () => null, makeCanvas: () => fakeCanvas(false) });
  assert.equal(blob.type, 'image/png');
});

test('a cover that taints the canvas is left out and the picture is made again', async () => {
  let made = 0;
  const makeCanvas = () => { made += 1; return fakeCanvas(made === 1); };
  const blob = await cardBlob({ ...CARD, covers: ['a'] }, { load: async () => ({ width: 1, height: 1 }), makeCanvas });
  assert.equal(blob.type, 'image/png');
  assert.equal(made, 2);
});

const blob = async () => new Blob(['png'], { type: 'image/png' });

test('a phone shares through its sheet', async () => {
  const shared = [];
  const nav = { canShare: () => true, share: async (data) => shared.push(data) };
  const saved = [];
  const result = await shareImage(CARD, { filename: 'a.png', title: 'Mi resumen' }, { blob, nav, save: (...args) => saved.push(args) });
  assert.equal(result, 'shared');
  assert.equal(shared[0].files[0].name, 'a.png');
  assert.equal(shared[0].title, 'Mi resumen');
  assert.equal(saved.length, 0);
});

test('closing the sheet is not an error and saves nothing', async () => {
  const nav = { canShare: () => true, share: async () => { throw Object.assign(new Error('x'), { name: 'AbortError' }); } };
  const saved = [];
  assert.equal(await shareImage(CARD, { filename: 'a.png', title: 't' }, { blob, nav, save: (...a) => saved.push(a) }), 'cancelled');
  assert.equal(saved.length, 0);
});

test('without a share sheet, or if it fails, the picture is downloaded', async () => {
  const saved = [];
  const save = (...args) => saved.push(args);
  assert.equal(await shareImage(CARD, { filename: 'a.png', title: 't' }, { blob, nav: {}, save }), 'saved');
  const broken = { canShare: () => true, share: async () => { throw new Error('nope'); } };
  assert.equal(await shareImage(CARD, { filename: 'b.png', title: 't' }, { blob, nav: broken, save }), 'saved');
  assert.deepEqual(saved.map((s) => [s[0], s[2]]), [['a.png', 'image/png'], ['b.png', 'image/png']]);
});
