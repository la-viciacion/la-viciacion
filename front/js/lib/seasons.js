// A season is a calendar year (the API derives it from each row's date).

/** The running season. */
export const current = (now = new Date()) => now.getFullYear();

/** Does this date fall in the running season? */
export const isCurrent = (date, now = new Date()) => date.getFullYear() === current(now);
