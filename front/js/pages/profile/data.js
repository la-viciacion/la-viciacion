// "Tus datos" of the Ajustes tab: download everything that is yours as a file, and import such a file back.
// The import first asks the API what it would do (`?dry_run=true`) and only writes after the person confirms.
// The API decides what can be imported (never overwrites, closed seasons only for admins, unknown games are
// skipped): this only shows its answer.
import { api, jsonRequest } from '../../lib/api.js';
import { addsSomething, describeFile, parseExport, summarize } from '../../lib/data-import.js';
import { saveFile } from '../../lib/download.js';
import { html, mount } from '../../lib/html.js';
import { sectionTitle } from '../../ui/profile-summary.js';
import { flash } from './flash.js';

const PROBLEMS_SHOWN = 8;

const reviewView = (data, report) => html`
  <div class="pf-import">
    <div><strong>El archivo trae:</strong> ${describeFile(data)}.</div>
    <ul>${summarize(report).map((line) => html`<li>${line}</li>`)}</ul>
    ${report.problems.length ? html`
      <details>
        <summary>${report.problems_total} ${report.problems_total === 1 ? 'fila no se puede importar' : 'filas no se pueden importar'}</summary>
        <ul>${report.problems.slice(0, PROBLEMS_SHOWN).map((p) => html`<li>${p.label}: ${p.reason}</li>`)}
        ${report.problems_total > PROBLEMS_SHOWN ? html`<li>… y ${report.problems_total - PROBLEMS_SHOWN} más</li>` : ''}</ul>
      </details>` : ''}
    <div class="pf-sub">Solo se añade lo que te falta: nada de lo que ya tienes se cambia ni se borra.</div>
    ${addsSomething(report)
    ? html`<div><button class="pf-btn primary" data-act="confirm">Importar</button> <button class="pf-btn" data-act="cancel">Cancelar</button></div>`
    : html`<div class="pf-sub">No hay nada nuevo que importar.</div>`}
  </div>`;

export async function initData(el, { username }) {
  const path = `/users/${encodeURIComponent(username)}`;
  let pending = null; // the file waiting for the person's yes

  mount(el, html`
    ${sectionTitle('Tus datos')}
    <div class="pf-card">
      <div class="pf-sub">Descarga un archivo con tus sesiones, biblioteca, puntuaciones, deseados y logros: una copia tuya para guardar. También puedes importar uno de esos archivos (por ejemplo, el de otra instalación de La Viciación).</div>
      <div><button class="pf-btn" data-act="export">Descargar mis datos</button></div>
      <div><label class="pf-btn">Importar datos…<input type="file" accept=".json,application/json" hidden /></label></div>
      <div id="pfImportReview"></div>
      <div class="pf-msg" role="status"></div>
    </div>`);
  const msg = el.querySelector('.pf-msg');
  const review = el.querySelector('#pfImportReview');
  const input = el.querySelector('input[type=file]');

  async function exportData() {
    flash(msg, '');
    try {
      const data = await api(`${path}/export`);
      saveFile(`laviciacion-${username}-${new Date().toLocaleDateString('sv-SE')}.json`, JSON.stringify(data, null, 2), 'application/json');
      flash(msg, 'Archivo descargado', true);
    } catch (err) {
      flash(msg, err.message);
    }
  }

  async function chooseFile(file) {
    flash(msg, '');
    mount(review, html``);
    pending = null;
    try {
      const data = parseExport(await file.text(), file.size);
      const report = await api(`${path}/import?dry_run=true`, jsonRequest('POST', data));
      if (!report) return;
      pending = data;
      mount(review, reviewView(data, report));
    } catch (err) {
      flash(msg, err.message);
    }
  }

  async function confirmImport(button) {
    button.disabled = true;
    try {
      const report = await api(`${path}/import`, jsonRequest('POST', pending));
      pending = null;
      mount(review, html`<div class="pf-import"><ul>${summarize(report).map((line) => html`<li>${line}</li>`)}</ul>
        <div><button class="pf-btn primary" data-act="reload">Ver los cambios</button></div></div>`);
      flash(msg, 'Importación terminada', true);
    } catch (err) {
      button.disabled = false;
      flash(msg, err.message);
    }
  }

  input.addEventListener('change', () => {
    if (input.files[0]) chooseFile(input.files[0]);
    input.value = ''; // the same file can be chosen again
  });
  el.addEventListener('click', (e) => {
    const button = e.target.closest('[data-act]');
    if (!button) return;
    if (button.dataset.act === 'export') exportData();
    else if (button.dataset.act === 'confirm' && pending) confirmImport(button);
    else if (button.dataset.act === 'cancel') { pending = null; mount(review, html``); }
    else if (button.dataset.act === 'reload') location.reload();
  });
}
