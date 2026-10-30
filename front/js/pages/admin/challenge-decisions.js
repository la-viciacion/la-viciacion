// What an admin does with a challenge a player proposed (admin panel → Retos → Propuestas): approve it, which
// launches it as a challenge of the group, or reject it with a note the proposer reads.
import { api, jsonRequest } from '../../lib/api.js';
import { html } from '../../lib/html.js';
import { modalHeader, openModal } from '../../ui/modal.js';
import { toast } from '../../ui/toast.js';

export function ask({ title, body, submit, run, admin }) {
  const m = openModal(html`
    ${modalHeader(title)}
    <form class="adm-form" novalidate>
      ${body}
      <div class="adm-error" role="alert"></div>
      <div class="adm-actions">
        <button type="button" class="adm-btn" data-close>Cancelar</button>
        <button type="submit" class="adm-btn primary">${submit}</button>
      </div>
    </form>`);
  const form = m.el.querySelector('form');
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    try {
      await run(form.elements);
      m.close();
      await admin.reload();
    } catch (err) {
      form.querySelector('.adm-error').textContent = err.message;
    }
  });
}

/** Launch what was proposed: tell the group or not, and who takes part (everybody or only who joins). */
export function approveProposal(row, admin) {
  ask({
    title: `Aprobar · ${row.title}`,
    admin,
    submit: 'Aprobar y lanzar',
    body: html`
      <p class="adm-sub">Propuesto por ${row.proposer?.name ?? 'alguien'}. Se lanza como un reto del grupo, con las opciones que eligió.</p>
      <label>Participación<select class="adm-input" name="participation">
        <option value="auto">Participan todos (pueden salirse)</option>
        <option value="opt_in">Voluntario (hay que apuntarse)</option>
      </select></label>
      <label class="adm-check"><input type="checkbox" name="announce" checked /> Avisar al grupo (Telegram y notificaciones)</label>`,
    run: async (el) => {
      await api(`/manage/challenge-proposals/${row.id}/approve`, jsonRequest('POST', { participation: el.participation.value, announce: el.announce.checked }));
      toast('Reto lanzado');
    },
  });
}

/** Turn it down; the note (optional) is what the proposer reads. */
export function rejectProposal(row, admin) {
  ask({
    title: `Rechazar · ${row.title}`,
    admin,
    submit: 'Rechazar',
    body: html`
      <p class="adm-sub">Propuesto por ${row.proposer?.name ?? 'alguien'}. Quien la propuso verá tu nota en la página Retos.</p>
      <label>Nota (opcional)<textarea class="adm-input" name="note" rows="3" maxlength="255"></textarea></label>`,
    run: async (el) => {
      await api(`/manage/challenge-proposals/${row.id}/reject`, jsonRequest('POST', { note: el.note.value.trim() || null }));
      toast('Propuesta rechazada');
    },
  });
}
