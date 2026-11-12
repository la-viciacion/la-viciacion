// An "i" button that opens a short explanation below it (a native <details>, so it works with touch and keyboard).
// Put it inside a `.pf-info-head`, which anchors the popover.
import { html } from '../lib/html.js';
import { iconInfo } from './icons.js';

export const infoTip = (text, label = 'Más información') => html`<details class="pf-info"><summary aria-label="${label}" title="${label}">${iconInfo()}</summary><div class="pf-info-text">${text}</div></details>`;

/** The title of a card with an "i" beside it that opens what used to be a paragraph under it: the explanation is one tap away and
 * takes no room until it is wanted. `text` is html (a string, or an html`` template, or several of them). */
export const cardTitle = (title, text) => html`<div class="pf-info-head pf-info-title"><h3>${title}</h3>${infoTip(text, `Más información: ${title}`)}</div>`;
