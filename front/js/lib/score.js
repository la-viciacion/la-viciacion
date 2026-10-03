// The rating of a game: an integer from 1 to 100, one per game and player (the API enforces it).
import { api, jsonRequest } from './api.js';

export const SCORE_MIN = 1;
export const SCORE_MAX = 100;

/** What was typed in a rating field -> the number, null when empty, NaN when it is not a valid rating. */
export function parseScore(text) {
  const value = String(text ?? '').trim();
  if (!value) return null;
  if (!/^\d+$/.test(value)) return NaN;
  const number = Number(value);
  return number >= SCORE_MIN && number <= SCORE_MAX ? number : NaN;
}

export const SCORE_HINT = `Un número entero de ${SCORE_MIN} a ${SCORE_MAX}`;

/** Rate a game, or remove the rating when `score` is null. */
export function saveScore(username, gameId, score) {
  const path = `/users/${encodeURIComponent(username)}/games/${encodeURIComponent(gameId)}/score`;
  return score == null ? api(path, { method: 'DELETE' }) : api(path, jsonRequest('PUT', { score }));
}
