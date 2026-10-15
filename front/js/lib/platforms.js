// Platform catalogue ([{id, name}]) shared by the home page and the admin panel.
import { api } from './api.js';

let list = [];
let loaded = false; // the catalogue was read at least once in this session

/** Ask for the catalogue again (the admin panel, after changing it). */
export async function loadPlatforms() {
  try {
    const answer = await api('/utils/platforms');
    list = answer || [];
    loaded = Boolean(answer);
  } catch (err) {
    console.error('Error loading platforms:', err);
  }
  return list;
}

/** The catalogue, asked for only the first time: it rarely changes, and the home page needs it on every visit. */
export const ensurePlatforms = () => (loaded ? Promise.resolve(list) : loadPlatforms());

export const platformList = () => list;

/** Human name of a platform id (falls back to the id itself). */
export const platformName = (id) => list.find((p) => p.id === id)?.name || id;
