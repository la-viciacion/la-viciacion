// Pure logic of the "Mis juegos" list of the profile: the state of a library entry, the filters, and the
// games still without a rating (what the random rating walks through).

/** Where an entry stands: "completed", "abandoned", "unfinished" (pending in a closed season) or "playing". */
export function entryState(entry) {
  if (entry.completed) return 'completed';
  if (entry.abandoned) return 'abandoned';
  return entry.complete_blocked === 'closed_season' ? 'unfinished' : 'playing';
}

export const STATES = [
  ['playing', 'En curso'],
  ['completed', 'Completados'],
  ['abandoned', 'Abandonados'],
  ['unfinished', 'Sin completar'],
];

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
