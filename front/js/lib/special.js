// The levels of a special achievement (achievements.special): 1 silver, 2 gold, 3 purple. Each is a colour: the
// `special-N` classes (css/base.css) set it and every aura, tag and badge is painted with it. 0 is an ordinary one.
import { html } from './html.js';

export const SPECIAL_NAMES = { 1: 'Plateado', 2: 'Dorado', 3: 'Morado' };

/** The class that gives something the colour of the level ('' for an ordinary achievement). */
export const specialClass = (level) => (SPECIAL_NAMES[level] ? ` special-${level}` : '');

/** The tag that says an achievement is special and its level, in its colour ('' for an ordinary one). */
export const specialTag = (level) => (SPECIAL_NAMES[level]
  ? html`<span class="pf-tag${specialClass(level)}">Especial nivel ${level}</span>`
  : '');
