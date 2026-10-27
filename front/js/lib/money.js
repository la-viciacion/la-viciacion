// Euros, for the prices of the games. Pure, so it can be tested.

/** 2999 -> "29,99 €", 1000 -> "10 €", 5 -> "0,05 €" (whole euros without decimals). */
export function euros(cents) {
  const value = cents / 100;
  return value.toLocaleString('es-ES', { style: 'currency', currency: 'EUR', minimumFractionDigits: Number.isInteger(value) ? 0 : 2 });
}

/** What a player typed in a price box: null for an empty box (no price), NaN for something that is not a price, else
 * the euros as a number ("29,99" and "29.99" both work). */
export function parseEuros(text) {
  const clean = String(text ?? '').trim().replace(',', '.');
  if (clean === '') return null;
  return /^\d+(\.\d{1,2})?$/.test(clean) ? Number(clean) : NaN;
}

/** The price a game row shows: what was paid for it on every platform that has one, "59,98 €", or '' if none has. */
export function paidText(platforms) {
  const prices = (platforms || []).map((p) => p.price_cents).filter((cents) => cents != null);
  return prices.length ? euros(prices.reduce((sum, cents) => sum + cents, 0)) : '';
}

/** What goes in a price box for a price in cents: 2999 -> "29,99", 1000 -> "10", none -> "". */
export const inputValue = (cents) => (cents == null ? '' : String(cents / 100).replace('.', ','));

/** A cost per hour: 250 -> "2,50 €/h". */
export const perHour = (cents) => `${(cents / 100).toLocaleString('es-ES', { style: 'currency', currency: 'EUR' })}/h`;
