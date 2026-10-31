// Colour of the aura around the running-timer card: it drifts from teal to red as the
// session grows, one stop every 30 minutes and flat red from 4 hours on. Pure ambience.

const STEP_SECONDS = 30 * 60;

// [hue, saturation %, lightness %] at 0:00, 0:30 ... 4:00. Green is kept short on purpose
// so that yellow shows up early (from about 1:30).
const STOPS = [
  [168, 70, 45],
  [145, 66, 45],
  [78, 72, 48],
  [50, 95, 52],
  [40, 95, 52],
  [28, 92, 52],
  [16, 90, 54],
  [6, 87, 55],
  [0, 85, 56],
];

/** The aura colour after `seconds` of play, as a CSS `h s% l%` triple, blended between neighbouring stops. */
export function auraColor(seconds) {
  const last = STOPS.length - 1;
  const position = Math.min(Math.max(seconds, 0) / STEP_SECONDS, last);
  const index = Math.min(Math.floor(position), last - 1);
  const fraction = position - index;
  const [h, s, l] = STOPS[index].map((from, i) => from + (STOPS[index + 1][i] - from) * fraction);
  return `${Math.round(h)} ${Math.round(s)}% ${Math.round(l)}%`;
}
