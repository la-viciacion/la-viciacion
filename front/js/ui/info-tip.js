// An "i" button that opens a short explanation below it (a native <details>, so it works with touch and keyboard).
// Put it inside a `.pf-info-head`, which anchors the popover.
import { html } from '../lib/html.js';
import { iconInfo } from './icons.js';

export const infoTip = (text, label = 'Más información') => html`<details class="pf-info"><summary aria-label="${label}" title="${label}">${iconInfo()}</summary><div class="pf-info-text">${text}</div></details>`;
