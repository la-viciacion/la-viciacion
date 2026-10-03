// Statistics (#/stats): a placeholder until the statistics are ready.
import { html, mount } from '../../lib/html.js';

export const active = null; // it belongs to no item of the top bar

export function render({ main }) {
  mount(main, html`
    <div class="section-header"><h2 class="section-title">Estadísticas</h2><div class="section-line"></div></div>
    <div class="pf-card wip-card">
      <span class="menu-wip">WIP</span>
      <strong>Estamos trabajando en ello</strong>
      <div class="pf-sub">Aquí irán las estadísticas del grupo: rankings, comparativas y más. Todavía no están listas.</div>
    </div>`);
}
