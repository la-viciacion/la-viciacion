// Generic create/edit form driven by the entity field definitions.
//
// Field: { key, label, type, required?, omitEmpty?, step? }
// Types: text | number | date | datetime | checkbox | platform | user | game | password
import { api, jsonRequest } from '../../lib/api.js';
import { html } from '../../lib/html.js';
import { PASSWORD_HINT, generatePassword, isValidPassword } from '../../lib/password.js';
import { platformList } from '../../lib/platforms.js';
import { modalHeader, openModal } from '../../ui/modal.js';
import { toast } from '../../ui/toast.js';
import { store } from './components.js';
import { pickGame } from './dialogs.js';

const inputId = (f) => `f_${f.key}`;

function fieldHtml(f, value) {
  const id = inputId(f);
  const v = value ?? '';
  switch (f.type) {
    case 'checkbox':
      return html`<label class="adm-check"><input type="checkbox" id="${id}" ${value ? html`checked` : ''} /> ${f.label}</label>`;
    case 'platform': {
      const known = platformList();
      return html`<label>${f.label}<select class="adm-input" id="${id}">
        <option value="">—</option>
        ${known.map((p) => html`<option value="${p.id}" ${p.id === v ? html`selected` : ''}>${p.name}</option>`)}
        ${v && !known.some((p) => p.id === v) ? html`<option value="${v}" selected>${v}</option>` : ''}
      </select></label>`;
    }
    case 'user':
      return html`<label>${f.label}<select class="adm-input" id="${id}">
        <option value="">Elegir…</option>
        ${store.users.map((u) => html`<option value="${u.id}">${u.username}</option>`)}
      </select></label>`;
    case 'game':
      return html`<div class="adm-field-game"><span>${f.label}</span>
        <div><span class="adm-picked" id="${id}_name">Ninguno</span> <button type="button" class="adm-btn sm" data-pickfor="${f.key}">Elegir…</button></div>
        <input type="hidden" id="${id}" /></div>`;
    case 'password':
      return html`<div class="adm-field-pw"><span>${f.label}</span>
        <div>
          <input class="adm-input" type="password" id="${id}" autocomplete="new-password" />
          <button type="button" class="adm-btn sm" data-pw-show="${id}">Mostrar</button>
          <button type="button" class="adm-btn sm" data-pw-gen="${id}">Generar</button>
        </div>
        <div class="adm-sub">${PASSWORD_HINT}</div></div>`;
    case 'datetime':
      return html`<label>${f.label}<input class="adm-input" type="datetime-local" step="1" id="${id}" value="${String(v).slice(0, 19)}" /></label>`;
    case 'date':
      return html`<label>${f.label}<input class="adm-input" type="date" id="${id}" value="${String(v).slice(0, 10)}" /></label>`;
    case 'number':
      return html`<label>${f.label}<input class="adm-input" type="number" step="${f.step || '1'}" id="${id}" value="${v}" /></label>`;
    default:
      return html`<label>${f.label}<input class="adm-input" type="text" id="${id}" value="${v}" /></label>`;
  }
}

function readField(f) {
  const el = document.getElementById(inputId(f));
  switch (f.type) {
    case 'checkbox': return el.checked;
    case 'number': return el.value === '' ? null : Number(el.value);
    case 'datetime': return el.value ? (el.value.length === 16 ? `${el.value}:00` : el.value) : null;
    case 'user': return el.value ? Number(el.value) : null;
    case 'date':
    case 'platform':
    case 'game': return el.value || null;
    default: return el.value === '' ? null : el.value;
  }
}

// Buttons inside the form: show/hide password, generate password, pick a game.
async function onFormClick(e, modal) {
  const show = e.target.closest('[data-pw-show]');
  if (show) {
    const input = modal.el.querySelector(`#${show.dataset.pwShow}`);
    input.type = input.type === 'password' ? 'text' : 'password';
    show.textContent = input.type === 'password' ? 'Mostrar' : 'Ocultar';
    return;
  }
  const gen = e.target.closest('[data-pw-gen]');
  if (gen) {
    const input = modal.el.querySelector(`#${gen.dataset.pwGen}`);
    input.value = generatePassword();
    input.type = 'text';
    modal.el.querySelector(`[data-pw-show="${gen.dataset.pwGen}"]`).textContent = 'Ocultar';
    input.select();
    return;
  }
  const pick = e.target.closest('[data-pickfor]');
  if (pick) {
    const game = await pickGame();
    if (game) {
      modal.el.querySelector(`#f_${pick.dataset.pickfor}`).value = game.id;
      modal.el.querySelector(`#f_${pick.dataset.pickfor}_name`).textContent = game.name;
    }
  }
}

/** Open the create (row = null) or edit form of an entity. */
export function openForm(entity, row, admin) {
  const creating = !row;
  const fields = creating ? entity.createFields : entity.fields;
  const modal = openModal(html`
    ${modalHeader(creating ? entity.createLabel : `Editar · ${entity.name(row)}`)}
    <form class="adm-form" novalidate>
      ${fields.map((f) => fieldHtml(f, row ? row[f.key] : undefined))}
      <div class="adm-error" role="alert"></div>
      <div class="adm-actions">
        <button type="button" class="adm-btn" data-close>Cancelar</button>
        <button type="submit" class="adm-btn primary">${creating ? 'Crear' : 'Guardar'}</button>
      </div>
    </form>`, { wide: true });

  modal.el.addEventListener('click', (e) => onFormClick(e, modal));
  modal.el.querySelector('form').addEventListener('submit', (e) => {
    e.preventDefault();
    submit(entity, row, fields, modal, admin);
  });
}

async function submit(entity, row, fields, modal, admin) {
  const errorEl = modal.el.querySelector('.adm-error');
  errorEl.textContent = '';
  const body = {};
  let newPassword = null;

  for (const f of fields) {
    if (f.type === 'password') {
      newPassword = document.getElementById(inputId(f)).value || null;
      continue;
    }
    const value = readField(f);
    if (f.required && (value === null || value === '')) { errorEl.textContent = `Falta: ${f.label}`; return; }
    if (f.omitEmpty && value === null) continue;
    body[f.key] = value;
  }
  if (newPassword !== null && !isValidPassword(newPassword)) {
    errorEl.textContent = `La contraseña debe tener ${PASSWORD_HINT.toLowerCase()}`;
    return;
  }

  try {
    if (!row) {
      await api(entity.endpoint, jsonRequest('POST', body));
    } else {
      await api(`${entity.endpoint}/${row.id}`, jsonRequest('PATCH', body));
      if (newPassword !== null) await api(`${entity.endpoint}/${row.id}/password`, jsonRequest('POST', { password: newPassword }));
    }
    modal.close();
    toast(!row ? 'Creado' : newPassword !== null ? 'Guardado y contraseña cambiada' : 'Guardado');
    await admin.reload();
  } catch (err) {
    errorEl.textContent = err.message;
  }
}
