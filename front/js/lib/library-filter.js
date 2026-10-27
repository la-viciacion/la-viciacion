// Pure logic of the "Mis juegos" list of the profile: the state of a library entry, the filters, the games still
// without a rating (what the random rating walks through) and "¿Qué juego sigo?", the games worth going back to.
// Nothing here is stored: the states and the suggestions come from what the library already says (sessions, completion,
// the abandoned mark and the average time to complete).

const DAY = 86400000;
export const PAUSED_DAYS = 30; // a pending game not played for this long is paused
export const FORGOTTEN_DAYS = 60; // ... and forgotten for this long
export const ALMOST_SHARE = 0.7; // from this share of the average time a game is almost finished...
export const ALMOST_CAP = 1.5; // ... until this one (well past the average, the average says nothing about it)
export const SHORT_SECONDS = 4 * 3600; // a game with this much left or less is short

/** Where an entry stands: "completed", "abandoned", "unfinished" (pending in a closed season), "backlog" (never
 * played), "paused" (not played for PAUSED_DAYS) or "playing". */
export function entryState(entry, now = new Date()) {
  if (entry.completed) return 'completed';
  if (entry.abandoned) return 'abandoned';
  if (entry.complete_blocked === 'closed_season') return 'unfinished';
  if (!entry.played_time && !entry.last_played) return 'backlog';
  if (entry.last_played && now - new Date(entry.last_played) > PAUSED_DAYS * DAY) return 'paused';
  return 'playing';
}

export const STATES = [
  ['playing', 'En curso'],
  ['paused', 'Pausados'],
  ['backlog', 'Pendientes'],
  ['completed', 'Completados'],
  ['abandoned', 'Abandonados'],
  ['unfinished', 'Sin completar'],
];

const OPEN = ['playing', 'paused', 'backlog'];

/** The games of the library that are still to be played, one item per game: { game_id, game_name, image_url, avg_time,
 * played_time, last_played, state }. The time is that of the runs not completed yet (a game completed in an earlier season and
 * played again counts from its new run), and the game is open when its entry of the running season is pending
 * and nothing blocks it. */
export function openGames(entries, now = new Date(), season = now.getFullYear()) {
  const games = new Map();
  for (const g of entries) {
    const game = games.get(g.game_id) || { game_id: g.game_id, game_name: g.game_name, image_url: g.image_url, avg_time: 0, played_time: 0, last_played: null, state: null };
    if (g.avg_time) game.avg_time = g.avg_time;
    if (!g.completed) game.played_time += g.played_time || 0;
    if (g.last_played && !g.completed && (!game.last_played || g.last_played > game.last_played)) game.last_played = g.last_played;
    if (g.season === season && !g.complete_blocked && OPEN.includes(entryState(g, now))) game.state = entryState(g, now);
    games.set(g.game_id, game);
  }
  return [...games.values()].filter((game) => game.state);
}

/** "¿Qué juego sigo?": { almost, forgotten, short }, each game in the first list that fits it.
 * almost: from 70 % of the average time (until 150 %), the nearest to the end first;
 * forgotten: played and not touched for 60 days, the one with most time put in first;
 * short: with 4 hours left or less by the average, the shortest first (a game never played counts). */
export function nextUp(entries, now = new Date(), season = now.getFullYear()) {
  const result = { almost: [], forgotten: [], short: [] };
  for (const game of openGames(entries, now, season)) {
    const left = game.avg_time ? game.avg_time - game.played_time : null;
    if (game.avg_time && game.played_time >= ALMOST_SHARE * game.avg_time && game.played_time <= ALMOST_CAP * game.avg_time) {
      result.almost.push({ ...game, left });
    } else if (game.played_time > 0 && game.last_played && now - new Date(game.last_played) > FORGOTTEN_DAYS * DAY) {
      result.forgotten.push({ ...game, left });
    } else if (left !== null && left > 0 && left <= SHORT_SECONDS) {
      result.short.push({ ...game, left });
    }
  }
  result.almost.sort((a, b) => Math.abs(a.left) - Math.abs(b.left));
  result.forgotten.sort((a, b) => b.played_time - a.played_time);
  result.short.sort((a, b) => a.left - b.left);
  return result;
}

/** Value of the platform filter for the entries without one. */
export const NO_PLATFORM = 'none';

export const NO_FILTERS = { q: '', season: '', state: '', rated: '', platform: '' };

const plain = (text) => String(text ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();

/** The platforms a row stands for: every one of its game and season, or its own platform for an item without the list. */
export const entryPlatforms = (entry) => entry.platforms
  || (entry.platform_id ? [{ id: entry.platform_id, name: entry.platform_name }] : []);

/** The entries that pass every filter that is set; `rated` is "yes" or "no". Keeps the order. */
export function filterEntries(entries, filters) {
  const { q, season, state, rated, platform } = { ...NO_FILTERS, ...filters };
  const needle = plain(q).trim();
  return entries.filter((g) => (
    (!needle || plain(g.game_name).includes(needle))
    && (!season || String(g.season) === String(season))
    && (!state || entryState(g) === state)
    && (!rated || (rated === 'yes') === (g.score != null))
    && (!platform || (entryPlatforms(g).length ? entryPlatforms(g) : [{ id: NO_PLATFORM }]).some((p) => String(p.id) === String(platform)))
  ));
}

/** One item per game that has no rating, with the time of all its entries (the rating is per game). */
export function unratedGames(entries) {
  const games = new Map();
  for (const g of entries) {
    if (g.score != null) continue;
    const game = games.get(g.game_id) || { game_id: g.game_id, game_name: g.game_name, image_url: g.image_url, played_time: 0 };
    game.played_time += g.played_time || 0;
    games.set(g.game_id, game);
  }
  return [...games.values()];
}

/** The same list in random order (Fisher-Yates); `random` is injectable for tests. */
export function shuffle(list, random = Math.random) {
  const out = [...list];
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(random() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}
