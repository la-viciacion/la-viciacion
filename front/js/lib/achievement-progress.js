// The bar of an achievement that adds something up (hours, days, games...). Pure, so it can be tested.
// `progress` is what the API gives: { current, target }. It has no unit on purpose: the bar says how far, not what it counts.

/** 0-100, whole number; a bar never shows more than full nor empty by rounding when something is done. */
export function progressPercent({ current, target }) {
  if (!target || current <= 0) return 0;
  const percent = Math.floor((Math.min(current, target) / target) * 100);
  return Math.max(1, Math.min(100, percent));
}

const number = (n) => (Number.isInteger(n) ? String(n) : n.toFixed(1).replace('.', ','));

/** "35 / 100" (a number with a decimal uses a comma). */
export const progressText = ({ current, target }) => `${number(current)} / ${number(target)}`;
