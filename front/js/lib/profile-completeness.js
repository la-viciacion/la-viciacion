// How much of the profile a player has filled in, and when this device may remind them about it. Pure apart from the
// storage of what the player answered. Nothing is stored about the profile itself: the percentage is worked out from the
// photo and the settings every time (the name and the email are always there, and the Telegram id is set by the bot).

// what a profile can lack, in the order it is said; `where` is the page that fills it in
const STEPS = [
  { id: 'photo', text: 'la foto', where: '#/profile/resumen' },
  { id: 'place', text: 'la ciudad', where: '#/profile/ajustes/perfil' },
  { id: 'birth', text: 'la fecha de nacimiento', where: '#/profile/ajustes/perfil' },
];

/** The ids of what is missing: `hasAvatar` is whether there is a photo, `settings` is GET /users/{username}/settings. */
export function missingSteps({ hasAvatar, settings }) {
  const lacks = { photo: !hasAvatar, place: !settings?.place_name, birth: !settings?.birth_date };
  return STEPS.filter(({ id }) => lacks[id]).map(({ id }) => id);
}

export const percent = (missing) => Math.round(((STEPS.length - missing.length) / STEPS.length) * 100);

const stepsOf = (missing) => STEPS.filter(({ id }) => missing.includes(id));

/** "Te falta la foto" / "Te faltan la ciudad y la fecha de nacimiento". */
export function missingText(missing) {
  const texts = stepsOf(missing).map(({ text }) => text);
  const list = texts.length > 1 ? `${texts.slice(0, -1).join(', ')} y ${texts.at(-1)}` : texts[0];
  return `${texts.length > 1 ? 'Te faltan' : 'Te falta'} ${list}`;
}

/** The page to fill in the first thing that is missing. */
export const fillHref = (missing) => stepsOf(missing)[0]?.where ?? '#/profile';

/** Whether any of what is missing is filled in the Ajustes tab (the photo is changed from the header of the summary). */
export const needsSettings = (missing) => missing.some((id) => id !== 'photo');

// After an "Ahora no" the bar waits a week ("Completar" is not an answer: it comes back on the next visit); it stops for good a month after it was first shown.
export const WAIT_DAYS = 7;
export const GIVE_UP_DAYS = 30;
const DAY = 24 * 60 * 60 * 1000;

const key = (username) => `lv-profile-invite-${username}`;

function read(username) {
  try {
    return { since: 0, until: 0, done: false, ...JSON.parse(localStorage.getItem(key(username))) };
  } catch {
    return { since: 0, until: 0, done: false };
  }
}

function write(username, state) {
  try { localStorage.setItem(key(username), JSON.stringify(state)); } catch { /* private mode: it will ask again on the next visit */ }
}

/** May the bar be shown now? Not while a wait is running, not a month after the first time, and not once the profile was seen complete. */
export function mayAsk(username, now = new Date()) {
  const { since, until, done } = read(username);
  return !done && now.getTime() >= until && (!since || now.getTime() < since + GIVE_UP_DAYS * DAY);
}

/** The bar is on screen: the month it may keep coming back for starts with the first time. */
export function markShown(username, now = new Date()) {
  const state = read(username);
  if (!state.since) write(username, { ...state, since: now.getTime() });
}

/** "Ahora no": the bar comes back after a week. */
export function snooze(username, now = new Date()) {
  const state = read(username);
  write(username, { ...state, since: state.since || now.getTime(), until: now.getTime() + WAIT_DAYS * DAY });
}

/** The profile is complete: there is nothing to ask about, now or on this device's next visits. */
export function markComplete(username) {
  write(username, { ...read(username), done: true });
}
