// Manual sessions: add one by hand (game, platform, start, end) or correct /
// delete one of your finished sessions. The API enforces the rules (current
// season, no overlaps, under 24 h, not in the future); the form checks the same
// things first so mistakes are explained before sending.
import { api, jsonRequest } from '../../lib/api.js';
import { formatDuration, fromInputValue, toInputValue } from '../../lib/format.js';
import { html } from '../../lib/html.js';
import { platformList } from '../../lib/platforms.js';
import * as seasons from '../../lib/seasons.js';
import { modalHeader, openModal } from '../../ui/modal.js';
import { toast } from '../../ui/toast.js';
import { NOTES_MAX, openGamePicker } from './game-picker.js';

const MAX_MS = 24 * 3600 * 1000;
const CONFIRM_MS = 4000;

let userId = null;
let onChange = () => {};

/** onChange runs after a session was created, edited or deleted. */
export function initSessions(options) {
  ({ userId, onChange } = options);
}

/** "+ Sesión manual": pick the game, then fill the form. */
export function openManualSession() {
  openGamePicker((id, name) => openSessionForm({ game: { id, name } }));
}

/** What is wrong with these times (message), or null. Mirrors the API rules. */
export function sessionProblem(start, end, now = new Date()) {
  if (!start || !end) return 'Indica el inicio y el fin';
  const s = new Date(start);
  const e = new Date(end);
  if (e <= s) return 'El fin debe ser posterior al inicio';
  if (e > now) return 'La sesión no puede terminar en el futuro';
  if (e - s > MAX_MS) return 'Una sesión no puede durar más de 24 horas';
  if (!seasons.isCurrent(s) || !seasons.isCurrent(e)) return `Solo puedes registrar sesiones de la temporada actual (${seasons.current(now)})`;
  return null;
}

const platformOptions = (selected) => platformList().map((p) => html`<option value="${p.id}" ${p.id === selected ? html`selected` : ''}>${p.name}</option>`);

/**
 * Form modal. `session` given = edit that session (the game cannot change:
 * for a wrong game, delete the session and add it again).
 */
export async function openSessionForm({ game, session = null }) {
  let platform = session?.platform || '';
  if (!session) {
    // the platform this user used last time for that game
    const info = await api(`/timers/history/${userId}/platforms/${encodeURIComponent(game.id)}`).catch(() => null);
    platform = info?.platforms?.[0] || '';
  }
  const now = toInputValue(new Date());

  const modal = openModal(html`
    ${modalHeader(session ? `Editar sesión · ${game.name}` : `Sesión manual · ${game.name}`)}
    <form class="sess-form" novalidate>
      <label>Plataforma
        <select class="sess-input" name="platform" required>
          <option value="">Elegir…</option>${platformOptions(platform)}
        </select>
      </label>
      <label>Inicio <input class="sess-input" type="datetime-local" name="start" step="60" max="${now}" value="${session ? toInputValue(session.start_time) : ''}" required /></label>
      <label>Fin <input class="sess-input" type="datetime-local" name="end" step="60" max="${now}" value="${session ? toInputValue(session.end_time) : ''}" required /></label>
      <label>Nota (opcional) <textarea class="sess-input" name="notes" rows="2" maxlength="${NOTES_MAX}">${session?.notes || ''}</textarea></label>
      <div class="sess-hint">Solo sesiones de esta temporada (${seasons.current()}), de menos de 24 horas y que no se solapen con otras tuyas.</div>
      <div class="sess-error" role="alert"></div>
      <div class="sess-actions">
        ${session ? html`<button type="button" class="sess-btn danger" data-delete>Eliminar sesión</button>` : ''}
        <span class="sess-spacer"></span>
        <button type="button" class="sess-btn" data-close>Cancelar</button>
        <button type="submit" class="sess-btn primary">${session ? 'Guardar' : 'Añadir'}</button>
      </div>
    </form>`);

  const form = modal.el.querySelector('form');
  const error = form.querySelector('.sess-error');
  const fail = (message) => { error.textContent = message; };

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    fail('');
    if (!form.platform.value) return fail('Elige la plataforma');
    const problem = sessionProblem(form.start.value, form.end.value);
    if (problem) return fail(problem);
    const body = {
      platform: form.platform.value,
      start_time: fromInputValue(form.start.value),
      end_time: fromInputValue(form.end.value),
      notes: form.notes.value.trim() || null,
    };
    try {
      if (session) await api(`/timers/${session.id}`, jsonRequest('PATCH', body));
      else await api('/timers/manual', jsonRequest('POST', { ...body, game_id: game.id }));
      modal.close();
      const start = new Date(form.start.value);
      const end = new Date(form.end.value);
      toast(`${session ? 'Sesión actualizada' : 'Sesión añadida'} (${formatDuration((end - start) / 1000)})`);
      await onChange();
    } catch (err) {
      fail(err.message);
    }
  });

  const remove = form.querySelector('[data-delete]');
  remove?.addEventListener('click', async () => {
    if (!remove.dataset.armed) {
      remove.dataset.armed = '1';
      remove.textContent = '¿Seguro? Pulsa otra vez';
      setTimeout(() => {
        if (remove.isConnected) { delete remove.dataset.armed; remove.textContent = 'Eliminar sesión'; }
      }, CONFIRM_MS);
      return;
    }
    try {
      await api(`/timers/${session.id}`, { method: 'DELETE' });
      modal.close();
      toast('Sesión eliminada');
      await onChange();
    } catch (err) {
      fail(err.message);
    }
  });
}
