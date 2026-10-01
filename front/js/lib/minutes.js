// Whole-minute input of the profile settings (how often the running-timer notification is
// refreshed), mirroring the API bounds (utils/user_settings.py): never below 10, on purpose.

export const MIN_MINUTES = 10;
export const MAX_MINUTES = 120;

export const MINUTES_HINT = `Un número entero de minutos entre ${MIN_MINUTES} y ${MAX_MINUTES}.`;

/**
 * Value of the minutes field: `null` when empty (use the default), the number when it
 * is a whole number in range, `undefined` when it is not valid (decimals, below the minimum...).
 */
export function parseMinutes(text) {
  const value = String(text).trim();
  if (value === '') return null;
  if (!/^\d+$/.test(value)) return undefined;
  const minutes = Number(value);
  return minutes >= MIN_MINUTES && minutes <= MAX_MINUTES ? minutes : undefined;
}
