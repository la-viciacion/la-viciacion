// Addresses inside the app.

/** The page of a game (see pages/game/index.js). */
export const gameHref = (gameId) => `#/game/${encodeURIComponent(gameId)}`;

const BODY_LINK = /\[((?:\\.|[^\]\\])*)\]\((https?:\/\/[^)\s]+)\)/g;

/**
 * The body of a notice with its game links ([name](url)) as anchors: RAWG's pages open in a new tab and the ones of this
 * app (same origin) navigate inside it. Any other address stays as plain text. Returns the pieces for `html`.
 */
export function noticeBody(body) {
  const parts = [];
  let last = 0;
  for (const found of body.matchAll(BODY_LINK)) {
    const [whole, text, url] = found;
    const href = noticeHref(url);
    if (!href) continue;
    parts.push(body.slice(last, found.index), { text, ...href });
    last = found.index + whole.length;
  }
  parts.push(body.slice(last));
  return parts;
}

function noticeHref(url) {
  try {
    const { origin, hash, host, pathname } = new URL(url);
    if (host === 'rawg.io' && pathname.startsWith('/games/')) return { href: url, external: true };
    if (origin === window.location.origin && hash.startsWith('#/game/')) return { href: hash, external: false };
  } catch {
    // not an address
  }
  return null;
}
