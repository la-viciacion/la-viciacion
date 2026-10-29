// Generic create/edit form driven by the entity field definitions.
//
// Field: { key, label, type, required?, omitEmpty?, step?, nameKey? (game: the row's key holding the game's name),
//   clearable? (game: a button to leave it empty), checks? (game: the key of a checkbox that choosing a game checks) }
// Types: text | textarea (rows?) | number | date | datetime | checkbox | select | month | platform | user | game | games | password | image
// games: a list of games (the value is [{ id, name }], what is sent is the ids): each is added with the same picker as `game`
// options: a list of short texts (the value is [text, ...]), one input row each, added and removed in the form: { min, max, maxLength }
// select: { options: [[number, label], ...] }
// month: the running month and the next ones, as a "YYYY-MM" text (the challenges are launched for a month)
// choice: { options: [[text, label], ...], default? } a select whose value stays text (select reads it as a number)
// An entity may have several ways to create a row (`creates`: [{ label, fields, body }]): `fields` is the form and
// `body` what is always sent with it (the kind of challenge, for instance); openForm takes the chosen one as `variant`.
// image (editing only): { current: (row) => url of the picture or null, upload: (row) => route that takes the new file }
import { api, jsonRequest } from '../../lib/api.js';
import { launchMonths } from '../../lib/challenges.js';
import { html } from '../../lib/html.js';
import { PASSWORD_HINT, generatePassword, isValidPassword } from '../../lib/password.js';
import { platformList } from '../../lib/platforms.js';
import { modalHeader, openModal } from '../../ui/modal.js';
import { toast } from '../../ui/toast.js';
import { store } from './components.js';
import { pickGame } from './dialogs.js';

const inputId = (f) => `f_${f.key}`;

function fieldHtml(f, value, row) {
  const id = inputId(f);
  const v = value ?? f.default ?? '';
  switch (f.type) {
    case 'checkbox':
      return html`<label class="adm-check"><input type="checkbox" id="${id}" ${v ? html`checked` : ''} /> ${f.label}</label>`;
    case 'select':
      return html`<label>${f.label}<select class="adm-input" id="${id}">
        ${f.options.map(([value, name]) => html`<option value="${value}" ${String(value) === String(v) ? html`selected` : ''}>${name}</option>`)}
      </select></label>`;
    case 'month':
      return html`<label>${f.label}<select class="adm-input" id="${id}">
        ${launchMonths().map((m) => html`<option value="${m.value}">${m.label}</option>`)}
      </select></label>`;
    case 'choice':
      return html`<label>${f.label}<select class="adm-input" id="${id}">
        ${f.options.map(([value, name]) => html`<option value="${value}" ${value === v ? html`selected` : ''}>${name}</option>`)}
      </select></label>`;
    case 'games':
      return html`<div class="adm-field-games"><span>${f.label}</span>
        <ol class="adm-games" id="${id}">${(Array.isArray(value) ? value : []).map((g) => html`<li data-id="${g.id}"><span>${g.name}</span> <button type="button" class="adm-btn sm" data-gameremove>Quitar</button></li>`)}</ol>
        <button type="button" class="adm-btn sm" data-gameadd="${f.key}">Añadir juego…</button></div>`;
    case 'options': {
      const texts = Array.isArray(value) ? [...value] : [];
      while (texts.length < (f.min ?? 0)) texts.push('');
      return html`<div class="adm-field-games"><span>${f.label}</span>
        <ol class="adm-games" id="${id}">${texts.map((text) => html`<li class="adm-option-row"><input class="adm-input" type="text" maxlength="${f.maxLength}" value="${text}" /> <button type="button" class="adm-btn sm" data-optionremove>Quitar</button></li>`)}</ol>
        <button type="button" class="adm-btn sm" data-optionadd="${f.key}">Añadir opción</button></div>`;
    }
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
        <div><span class="adm-picked" id="${id}_name">${(f.nameKey && row?.[f.nameKey]) || (v ? v : 'Ninguno')}</span> <button type="button" class="adm-btn sm" data-pickfor="${f.key}">${v ? 'Cambiar…' : 'Elegir…'}</button>${f.clearable ? html` <button type="button" class="adm-btn sm" data-clearfor="${f.key}">Quitar</button>` : ''}</div>
        <input type="hidden" id="${id}" value="${v}" /></div>`;
    case 'image':
      return html`<label>${f.label}
        ${row && f.current(row) ? html`<img class="adm-ach" src="${f.current(row)}?v=${Date.now()}" alt="" />` : ''}
        <input class="adm-input" type="file" accept="image/png,image/jpeg" id="${id}" /></label>`;
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
    case 'textarea':
      return html`<label>${f.label}<textarea class="adm-input${f.grow ? ' adm-grow' : ''}" id="${id}" rows="${f.rows || (f.grow ? 1 : 4)}" maxlength="${f.maxLength || ''}">${v}</textarea></label>`;
    case 'number':
      return html`<label>${f.label}<input class="adm-input" type="number" step="${f.step || '1'}" id="${id}" value="${v}" /></label>`;
    default:
      return html`<label>${f.label}<input class="adm-input" type="text" id="${id}" value="${v}" /></label>`;
  }
}

// The rows of an `options` field say which one they are, and say it again when one goes away.
function numberOptions(list) {
  list.querySelectorAll('input').forEach((input, i) => {
    input.placeholder = `Opción ${i + 1}`;
    input.setAttribute('aria-label', `Opción ${i + 1}`);
  });
}

// A one-line text that may run long: the box grows downward instead of scrolling sideways.
function autoGrow(area) {
  const fit = () => {
    area.style.height = 'auto';
    area.style.height = `${area.scrollHeight}px`;
  };
  area.addEventListener('input', fit);
  area.addEventListener('keydown', (e) => { if (e.key === 'Enter') e.preventDefault(); });
  fit();
}

function readField(f) {
  const el = document.getElementById(inputId(f));
  switch (f.type) {
    case 'checkbox': return el.checked;
    case 'select':
    case 'number': return el.value === '' ? null : Number(el.value);
    case 'datetime': return el.value ? (el.value.length === 16 ? `${el.value}:00` : el.value) : null;
    case 'user': return el.value ? Number(el.value) : null;
    case 'games': return [...el.querySelectorAll('li')].map((li) => li.dataset.id);
    case 'options': return [...el.querySelectorAll('input')].map((input) => input.value.trim()).filter(Boolean);
    case 'date':
    case 'month':
    case 'choice':
    case 'platform':
    case 'game': return el.value || null;
    default: return el.value === '' ? null : el.value;
  }
}

// Buttons inside the form: show/hide password, generate password, pick a game.
async function onFormClick(e, modal, fields) {
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
      const checks = fields.find((f) => f.key === pick.dataset.pickfor)?.checks;
      if (checks) modal.el.querySelector(`#f_${checks}`).checked = true;
    }
    return;
  }
  const add = e.target.closest('[data-gameadd]');
  if (add) {
    const game = await pickGame();
    const list = modal.el.querySelector(`#f_${add.dataset.gameadd}`);
    if (game && ![...list.querySelectorAll('li')].some((li) => li.dataset.id === game.id)) {
      const item = document.createElement('li');
      item.dataset.id = game.id;
      const name = document.createElement('span');
      name.textContent = game.name;
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'adm-btn sm';
      remove.dataset.gameremove = '';
      remove.textContent = 'Quitar';
      item.append(name, ' ', remove);
      list.append(item);
    }
    return;
  }
  const addOption = e.target.closest('[data-optionadd]');
  if (addOption) {
    const field = fields.find((f) => f.key === addOption.dataset.optionadd);
    const list = modal.el.querySelector(`#f_${field.key}`);
    if (list.children.length >= field.max) return;
    const item = document.createElement('li');
    item.className = 'adm-option-row';
    const input = document.createElement('input');
    input.className = 'adm-input';
    input.type = 'text';
    input.maxLength = field.maxLength;
    const remove = document.createElement('button');
    remove.type = 'button';
    remove.className = 'adm-btn sm';
    remove.dataset.optionremove = '';
    remove.textContent = 'Quitar';
    item.append(input, ' ', remove);
    list.append(item);
    numberOptions(list);
    addOption.disabled = list.children.length >= field.max;
    input.focus();
    return;
  }
  const removeOption = e.target.closest('[data-optionremove]');
  if (removeOption) {
    const list = removeOption.closest('ol');
    const add = removeOption.closest('.adm-field-games').querySelector('[data-optionadd]');
    removeOption.closest('li').remove();
    numberOptions(list);
    add.disabled = list.children.length >= fields.find((f) => `f_${f.key}` === list.id).max;
    return;
  }
  const removeGame = e.target.closest('[data-gameremove]');
  if (removeGame) {
    removeGame.closest('li').remove();
    return;
  }
  const clear = e.target.closest('[data-clearfor]');
  if (clear) {
    modal.el.querySelector(`#f_${clear.dataset.clearfor}`).value = '';
    modal.el.querySelector(`#f_${clear.dataset.clearfor}_name`).textContent = 'Ninguno';
  }
}

/** Open the create (row = null) or edit form of an entity. */
export function openForm(entity, row, admin, variant = null) {
  const creating = !row;
  const fields = creating ? (variant?.fields ?? entity.createFields) : entity.fields;
  const modal = openModal(html`
    ${modalHeader(creating ? (variant?.label ?? entity.createLabel) : `Editar · ${entity.name(row)}`)}
    <form class="adm-form" novalidate>
      ${fields.map((f) => fieldHtml(f, row ? row[f.key] : undefined, row))}
      <div class="adm-error" role="alert"></div>
      <div class="adm-actions">
        <button type="button" class="adm-btn" data-close>Cancelar</button>
        <button type="submit" class="adm-btn primary">${creating ? 'Crear' : 'Guardar'}</button>
      </div>
    </form>`, { wide: true });

  fields.filter((f) => f.type === 'options').forEach((f) => numberOptions(modal.el.querySelector(`#f_${f.key}`)));
  modal.el.querySelectorAll('textarea.adm-grow').forEach(autoGrow);
  modal.el.addEventListener('click', (e) => onFormClick(e, modal, fields));
  modal.el.querySelector('form').addEventListener('submit', (e) => {
    e.preventDefault();
    submit(entity, row, fields, modal, admin, variant?.body);
  });
}

async function submit(entity, row, fields, modal, admin, extra = {}) {
  const errorEl = modal.el.querySelector('.adm-error');
  errorEl.textContent = '';
  const body = {};
  let newPassword = null;
  const uploads = [];

  for (const f of fields) {
    if (f.type === 'image') {
      // A new picture goes to its own route once the rest is saved; no file chosen leaves the current one.
      const file = document.getElementById(inputId(f)).files[0];
      if (file) uploads.push({ file, url: f.upload(row) });
      continue;
    }
    if (f.type === 'password') {
      // Editing: an optional new password sent separately. Creating: a normal field.
      const typed = document.getElementById(inputId(f)).value || null;
      if (row) { newPassword = typed; continue; }
      if (f.required && typed === null) { errorEl.textContent = `Falta: ${f.label}`; return; }
      if (typed !== null && !isValidPassword(typed)) {
        errorEl.textContent = `La contraseña debe tener ${PASSWORD_HINT.toLowerCase()}`;
        return;
      }
      body[f.key] = typed;
      continue;
    }
    const value = readField(f);
    if (f.required && (value === null || value === '' || (Array.isArray(value) && !value.length))) { errorEl.textContent = `Falta: ${f.label}`; return; }
    if (f.min && Array.isArray(value) && value.length < f.min) { errorEl.textContent = `Hacen falta al menos ${f.min} opciones`; return; }
    if (f.omitEmpty && value === null) continue;
    body[f.key] = value;
  }
  if (newPassword !== null && !isValidPassword(newPassword)) {
    errorEl.textContent = `La contraseña debe tener ${PASSWORD_HINT.toLowerCase()}`;
    return;
  }

  try {
    if (!row) {
      await api(entity.endpoint, jsonRequest('POST', { ...body, ...extra }));
    } else {
      await api(`${entity.endpoint}/${row.id}`, jsonRequest('PATCH', body));
      if (newPassword !== null) await api(`${entity.endpoint}/${row.id}/password`, jsonRequest('POST', { password: newPassword }));
      for (const { file, url } of uploads) {
        const form = new FormData();
        form.append('file', file);
        await api(url, { method: 'PATCH', body: form });
      }
    }
    modal.close();
    toast(!row ? 'Creado' : newPassword !== null ? 'Guardado y contraseña cambiada' : 'Guardado');
    await admin.reload();
  } catch (err) {
    errorEl.textContent = err.message;
  }
}
