// Whole-hour input of the profile settings, mirroring the API bounds
// (utils/user_settings.py) so the form can reject a bad value before sending it.

export const MIN_HOURS = 1;
export const MAX_HOURS = 24;

export const HOURS_HINT = `Un número entero de horas entre ${MIN_HOURS} y ${MAX_HOURS}.`;

/**
 * Value of the hours field: `null` when empty (use the default), the number when it
 * is a whole number in range, `undefined` when it is not valid (minutes, decimals...).
 */
export function parseHours(text) {
  const value = String(text).trim();
  if (value === '') return null;
  if (!/^\d+$/.test(value)) return undefined;
  const hours = Number(value);
  return hours >= MIN_HOURS && hours <= MAX_HOURS ? hours : undefined;
}
