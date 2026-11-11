// Colour of the aura around the running-timer card: it drifts linearly from green to red
// over 4 hours (yellow lands at exactly 2:00) and stays red from then on. Pure ambience.

const FULL_SECONDS = 4 * 3600;

// [hue, saturation %, lightness %] at 0:00 and at 4:00.
const FROM = [120, 72, 46];
const TO = [0, 85, 56];

/** The aura colour after `seconds` of play, as a CSS `h s% l%` triple. */
export function auraColor(seconds) {
  const fraction = Math.min(Math.max(seconds, 0) / FULL_SECONDS, 1);
  const [h, s, l] = FROM.map((from, i) => from + (TO[i] - from) * fraction);
  return `${Math.round(h)} ${Math.round(s)}% ${Math.round(l)}%`;
}
