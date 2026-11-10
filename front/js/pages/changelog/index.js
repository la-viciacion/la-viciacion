// Changelog page (#/changelog): what changed for the players, newest first. The entries are written by hand in
// lib/changelog.js; nothing is asked of the API.
import { html, mount } from '../../lib/html.js';
import { CHANGELOG, DOCS_URL, groups } from '../../lib/changelog.js';
import { formatDate } from '../../lib/format.js';

export const active = null; // it belongs to no item of the top bar

const entry = (e) => html`
  <section class="pf-card cl-entry" aria-label="Versión ${e.version}">
    <header class="cl-head">
      <h2 class="cl-version">${e.title}</h2>
      <span class="cl-meta">v${e.version} · ${formatDate(e.date)}</span>
    </header>
    ${groups(e).map((g) => html`
      <div class="cl-group">
        <span class="cl-kind cl-${g.kind}">${g.label}</span>
        <ul class="cl-items">${g.items.map((text) => html`<li>${text}</li>`)}</ul>
      </div>`)}
  </section>`;

export function render({ main }) {
  mount(main, html`
    <div class="cl-top">
      <h1 class="pf-title pg-title">Novedades</h1>
      <a class="cl-docs" href="${DOCS_URL}" target="_blank" rel="noopener noreferrer">Documentación completa <span aria-hidden="true">↗</span></a>
    </div>
    <div class="cl-list">${CHANGELOG.map(entry)}</div>`);
}
