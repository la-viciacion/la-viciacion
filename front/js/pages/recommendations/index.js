// Recommendations page (#/recommendations): games the others have and you have never had, a weighted random pick
// that can be redrawn. GET /users/{username}/recommendations decides; list.js only shows it.
import { html, mount } from '../../lib/html.js';
import { initRecommendations } from './list.js';

export const active = null; // it belongs to no item of the top bar

export async function render({ main, user }) {
  mount(main, html`
    <h1 class="pf-title">Recomendados</h1>
    <div class="pf-sub pf-note">Juegos que tienen los demás y tú nunca has jugado, empezando por los que más gente comparte.</div>
    <div id="pfRecommended"></div>`);
  await initRecommendations(main.querySelector('#pfRecommended'), { username: user.username });
}
