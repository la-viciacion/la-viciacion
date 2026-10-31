// The logic of the hidden surprises, apart from the page so it can be tested: no DOM, no clock of its own.

export const KONAMI_KEYS = ['up', 'up', 'down', 'down', 'left', 'right', 'left', 'right', 'b', 'a'];
// on a phone the same code is swiped, and B A become two taps
export const KONAMI_SWIPES = ['up', 'up', 'down', 'down', 'left', 'right', 'left', 'right', 'tap', 'tap'];

const ARROWS = { ArrowUp: 'up', ArrowDown: 'down', ArrowLeft: 'left', ArrowRight: 'right' };
const MODIFIERS = new Set(['Shift', 'Control', 'Alt', 'Meta', 'CapsLock']);
const SWIPE_MIN_PX = 40;

/** The step a key press means for the Konami code (null for a modifier, which must not break the sequence). */
export function keyStep(key) {
  if (MODIFIERS.has(key)) return null;
  return ARROWS[key] ?? key.toLowerCase();
}

/** The step a finger gesture means: the direction of a swipe, or 'tap' when it barely moved. */
export function swipeStep(dx, dy) {
  if (Math.max(Math.abs(dx), Math.abs(dy)) < SWIPE_MIN_PX) return 'tap';
  if (Math.abs(dx) > Math.abs(dy)) return dx > 0 ? 'right' : 'left';
  return dy > 0 ? 'down' : 'up';
}

/** Feed it one step at a time; it answers true when the last steps are `sequence`. A pause longer than `maxGapMs`
 * starts over. It looks at a sliding window, so an extra step before the code (↑↑↑↓↓…) does not hide it. */
export function sequenceMatcher(sequence, { maxGapMs = 5000, now = Date.now } = {}) {
  const recent = [];
  let last = 0;
  return (step) => {
    const t = now();
    if (t - last > maxGapMs) recent.length = 0;
    last = t;
    recent.push(step);
    if (recent.length > sequence.length) recent.shift();
    const hit = recent.length === sequence.length && recent.every((s, i) => s === sequence[i]);
    if (hit) recent.length = 0;
    return hit;
  };
}

/** Counts quick repeated taps: true when `taps` of them fall within `windowMs`, then it starts over. */
export function tapCounter({ taps = 7, windowMs = 3000, now = Date.now } = {}) {
  const times = [];
  return () => {
    const t = now();
    times.push(t);
    while (t - times[0] > windowMs) times.shift();
    if (times.length < taps) return false;
    times.length = 0;
    return true;
  };
}

// Month and day (as month * 100 + day), both ends included.
const SKINS = [
  { name: 'halloween', from: 1025, to: 1031 },
  { name: 'christmas', from: 1224, to: 1231 },
];

/** Is `date` the birthday of someone born on `born` ('YYYY-MM-DD', the year does not matter)? Born on 29 February
 * celebrates on the 28th in the years with no 29th, as the API does for the achievement. */
export function isBirthday(born, date = new Date()) {
  const match = /^\d{4}-(\d{2})-(\d{2})$/.exec(born ?? '');
  if (!match) return false;
  const month = Number(match[1]);
  const leapDay = month === 2 && match[2] === '29' && new Date(date.getFullYear(), 1, 29).getMonth() !== 1;
  return date.getMonth() + 1 === month && date.getDate() === (leapDay ? 28 : Number(match[2]));
}

/** The costume the logo wears on `date` (local time), or '' on any other day. The birthday of the player (`born`)
 * wins over the season: it is only theirs. */
export function skinFor(date = new Date(), born = null) {
  if (isBirthday(born, date)) return 'birthday';
  const day = (date.getMonth() + 1) * 100 + date.getDate();
  return SKINS.find((s) => day >= s.from && day <= s.to)?.name ?? '';
}

const greetedKey = (username) => `birthday-greeted:${username}`;
const dayOf = (date) => date.toLocaleDateString('sv-SE');

/** Has this device already greeted `username` today? */
export function hasGreeted(username, date = new Date()) {
  try { return localStorage.getItem(greetedKey(username)) === dayOf(date); } catch { return false; }
}

export function markGreeted(username, date = new Date()) {
  try { localStorage.setItem(greetedKey(username), dayOf(date)); } catch { /* private mode: it greets again on the next visit */ }
}
