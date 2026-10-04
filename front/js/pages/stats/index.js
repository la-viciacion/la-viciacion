// Statistics (#/stats): a placeholder until the statistics are ready.
import { html, mount } from '../../lib/html.js';

export const active = null; // it belongs to no item of the top bar

export function render({ main }) {
  mount(main, html`
    <h1 class="pf-title pg-title">Estadísticas</h1>
    <div class="pf-card wip-card">
      <span class="menu-wip">WIP</span>
      <strong>Estamos trabajando en ello</strong>
      <div class="pf-sub">Aquí irán las estadísticas del grupo: rankings, comparativas y más. Todavía no están listas.</div>
    </div>`);
}
