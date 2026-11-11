// Global search: the matching of what the player types against the pages of the menu and the players of the group.
// Pure, so it can be tested; the games are looked up by the API (GET /games/catalog?q=), see ui/search.js.

/** Lower case without accents, so "tu" finds "Tú" and "jose" finds "José". */
export const fold = (text) => String(text ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();

// 0: starts with the query, 1: a word starts with it, 2: contains it; null when it does not match
function rank(text, query) {
  const name = fold(text);
  if (name.startsWith(query)) return 0;
  if (name.split(/[\s._-]+/).some((word) => word.startsWith(query))) return 1;
  return name.includes(query) ? 2 : null;
}

/** The items whose text (`keys` of each one) matches `query`, the best match first (ties keep their order). */
export function matchBy(query, items, keys, limit = 5) {
  const q = fold(query);
  if (!q) return [];
  return items
    .map((item, order) => {
      const ranks = keys.map((key) => rank(item[key], q)).filter((r) => r !== null);
      return ranks.length ? { item, score: Math.min(...ranks), order } : null;
    })
    .filter(Boolean)
    .sort((a, b) => a.score - b.score || a.order - b.order)
    .slice(0, limit)
    .map((entry) => entry.item);
}

export const matchPages = (query, pages, limit = 5) => matchBy(query, pages, ['label'], limit);
export const matchPlayers = (query, players, limit = 5) => matchBy(query, players, ['name', 'username'], limit);
