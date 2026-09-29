// Platform catalogue ([{id, name}]) shared by the home page and the admin panel.
import { api } from './api.js';

let list = [];

export async function loadPlatforms() {
  try {
    list = (await api('/utils/platforms')) || [];
  } catch (err) {
    console.error('Error loading platforms:', err);
  }
  return list;
}

export const platformList = () => list;

/** Human name of a platform id (falls back to the id itself). */
export const platformName = (id) => list.find((p) => p.id === id)?.name || id;
