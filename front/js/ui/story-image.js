// A story slide as a PNG (1080x1920, the size of a phone story), made with a canvas: no library, nothing leaves the browser.
// lib/story-share.js says what the picture holds; this paints it and hands it over: the share sheet where the device has
// one (a phone), a download everywhere else.
import { saveFile } from '../lib/download.js';
import { THEMES } from '../lib/story-share.js';

export const WIDTH = 1080;
export const HEIGHT = 1920;
const MARGIN = 100;
const FONT = '"Outfit", system-ui, -apple-system, "Segoe UI", sans-serif';
const COVER_ONE = 520;
const COVER_ROW = 170;
const IMAGE_TIMEOUT_MS = 4000;

/** Break `text` into lines that fit `maxWidth`, by words; `measure(text)` gives a width. A word wider than the line stays whole. */
export function wrapText(measure, text, maxWidth) {
  const lines = [];
  let line = '';
  for (const word of String(text).split(/\s+/).filter(Boolean)) {
    const tried = line ? `${line} ${word}` : word;
    if (line && measure(tried) > maxWidth) {
      lines.push(line);
      line = word;
    } else {
      line = tried;
    }
  }
  if (line) lines.push(line);
  return lines;
}

/** A cover as an image, or null when it cannot be had (no address, blocked, slow): the picture is made without it. */
export function loadImage(url) {
  if (!url) return Promise.resolve(null);
  return new Promise((resolve) => {
    const image = new Image();
    const timer = setTimeout(() => resolve(null), IMAGE_TIMEOUT_MS);
    image.crossOrigin = 'anonymous'; // without it the canvas is tainted and cannot be saved
    image.onload = () => { clearTimeout(timer); resolve(image); };
    image.onerror = () => { clearTimeout(timer); resolve(null); };
    image.src = url;
  });
}

function roundedRect(ctx, x, y, size, radius) {
  ctx.beginPath();
  ctx.roundRect(x, y, size, size, radius);
}

function drawCover(ctx, image, x, y, size) {
  ctx.save();
  roundedRect(ctx, x, y, size, size * 0.08);
  ctx.clip();
  if (image) {
    const side = Math.min(image.width, image.height);
    ctx.drawImage(image, (image.width - side) / 2, (image.height - side) / 2, side, side, x, y, size, size);
  } else {
    ctx.fillStyle = 'rgba(255,255,255,0.14)';
    ctx.fillRect(x, y, size, size);
    ctx.fillStyle = '#fff';
    ctx.font = `${size * 0.4}px ${FONT}`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText('🎮', x + size / 2, y + size / 2);
  }
  ctx.restore();
}

/** Paint the card on a canvas of WIDTH x HEIGHT. `images` are the covers, in order (null for the ones that could not load). */
export function paintCard(ctx, card, images) {
  const theme = THEMES[card.theme] || THEMES.teal;
  const gradient = ctx.createLinearGradient(0, 0, WIDTH * 0.4, HEIGHT);
  gradient.addColorStop(0, theme.from);
  gradient.addColorStop(0.55, theme.mid);
  gradient.addColorStop(1, '#0a0a14');
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, WIDTH, HEIGHT);

  const inner = WIDTH - MARGIN * 2;
  const measure = (font) => { ctx.font = font; return (text) => ctx.measureText(text).width; };
  const titleFont = `800 118px ${FONT}`;
  const lineFont = `500 54px ${FONT}`;
  const titleLines = card.title ? wrapText(measure(titleFont), card.title, inner).slice(0, 3) : [];
  const textLines = card.lines.flatMap((line) => wrapText(measure(lineFont), line, inner));
  const many = card.covers.length > 1;
  const coverBlock = card.covers.length ? (many ? COVER_ROW : COVER_ONE) : 0;

  const KICKER_H = 60;
  const GAP = 56;
  const titleH = titleLines.length * 128;
  const linesH = textLines.length * 74;
  const blocks = [KICKER_H, coverBlock, titleH, linesH].filter(Boolean);
  const total = blocks.reduce((a, b) => a + b, 0) + GAP * (blocks.length - 1);
  let y = Math.max(260, (HEIGHT - total) / 2);

  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  ctx.fillStyle = theme.accent;
  ctx.font = `700 46px ${FONT}`;
  ctx.fillText('LA VICIACIÓN', WIDTH / 2, 150);

  ctx.font = `700 50px ${FONT}`;
  ctx.fillText(card.kicker.toUpperCase(), WIDTH / 2, y);
  y += KICKER_H + GAP;

  if (coverBlock) {
    const count = Math.min(card.covers.length, 5);
    const gap = 28;
    const rowWidth = count * coverBlock + (count - 1) * gap;
    for (let i = 0; i < count; i += 1) drawCover(ctx, images[i], (WIDTH - rowWidth) / 2 + i * (coverBlock + gap), y, coverBlock);
    y += coverBlock + GAP;
  }

  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  ctx.fillStyle = '#fff';
  ctx.font = titleFont;
  for (const line of titleLines) {
    ctx.fillText(line, WIDTH / 2, y);
    y += 128;
  }
  if (titleLines.length) y += GAP - 10;

  ctx.fillStyle = 'rgba(255,255,255,0.88)';
  ctx.font = lineFont;
  for (const line of textLines) {
    ctx.fillText(line, WIDTH / 2, y);
    y += 74;
  }

  ctx.fillStyle = 'rgba(255,255,255,0.6)';
  ctx.font = `500 40px ${FONT}`;
  ctx.fillText(card.footer, WIDTH / 2, HEIGHT - 150);
}

const toBlob = (canvas) => new Promise((resolve, reject) => {
  try {
    canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error('No se ha podido crear la imagen'))), 'image/png');
  } catch (err) {
    reject(err); // a canvas tainted by a cover that does not allow it
  }
});

/** The PNG of a card. If a cover taints the canvas the picture is made again without covers. */
export async function cardBlob(card, { load = loadImage, makeCanvas = () => Object.assign(document.createElement('canvas'), { width: WIDTH, height: HEIGHT }) } = {}) {
  const images = await Promise.all(card.covers.map(load));
  for (const withCovers of [true, false]) {
    const canvas = makeCanvas();
    paintCard(canvas.getContext('2d'), card, withCovers ? images : card.covers.map(() => null));
    try {
      return await toBlob(canvas);
    } catch (err) {
      if (!withCovers) throw err;
    }
  }
  return null;
}

/** Share the picture of a card: the share sheet when the device has one, a download otherwise.
 * Resolves to "shared", "cancelled" (the person closed the sheet) or "saved". */
export async function shareImage(card, { filename, title }, { blob = cardBlob, nav = globalThis.navigator, save = saveFile } = {}) {
  const image = await blob(card);
  const file = new File([image], filename, { type: 'image/png' });
  if (nav?.canShare?.({ files: [file] })) {
    try {
      await nav.share({ files: [file], title });
      return 'shared';
    } catch (err) {
      if (err.name === 'AbortError') return 'cancelled';
      // any other failure of the sheet: the download still gets the picture to them
    }
  }
  save(filename, image, 'image/png');
  return 'saved';
}
