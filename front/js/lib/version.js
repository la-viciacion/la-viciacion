// The release the API runs (`dev` for a build from a checkout), asked once per page load.
import { api } from './api.js';

let known = '';

/** The version, or '' when it could not be asked (it is only decoration, so nothing depends on it). */
export async function loadVersion() {
  if (!known) known = (await api('/utils/version').catch(() => null))?.version || '';
  return known;
}
