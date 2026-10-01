// A season is a calendar year (the API derives it from each row's date).

/** The running season. */
export const current = (now = new Date()) => now.getFullYear();

/** Does this date fall in the running season? */
export const isCurrent = (date, now = new Date()) => date.getFullYear() === current(now);

/** What the profile asks the API for to see every season at once. */
export const ALL = 'all';

/** The choices of the season selector: the seasons newest first, then the total. */
export const choices = (years) => [...years.map((year) => ({ value: year, label: String(year) })), { value: ALL, label: 'Total' }];
