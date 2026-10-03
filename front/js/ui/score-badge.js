// A rating next to a game's name: the number in a small ring whose colour follows the score
// (red to green, kept soft). Empty when the game has no rating.
import { html } from '../lib/html.js';
import { scoreHue } from '../lib/score.js';

export const scoreBadge = (score) => (score == null
  ? ''
  : html`<span class="score-badge" style="--h:${scoreHue(score)}" title="Tu nota: ${score}" aria-label="Tu nota: ${score}">${score}</span>`);
