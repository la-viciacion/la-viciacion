// "Mi IA" of the Ajustes tab: the player's own OpenAI key for the chat and the game guide, and the model they want to use with it.
// GET/PUT/DELETE /users/{username}/ai, GET /ai/models and POST /ai/test. The key is checked by the API with OpenAI before it is
// kept, it is stored encrypted and it never comes back: the screen only knows whether there is one and its last characters.
import { api, jsonRequest } from '../../lib/api.js';
import { featureLabel, tokens } from '../../lib/ai-calls.js';
import { money, monthLabel } from '../../lib/ai-usage.js';
import { forgetGuideStatus } from '../../lib/guide.js';
import { html, mount } from '../../lib/html.js';
import { FEATURES, blockedText, budgetLines, costNote, keyText, looksLikeKey, modelLabel, paidBy } from '../../lib/user-ai.js';
import { sectionTitle } from '../../ui/profile-summary.js';
import { flash } from './flash.js';

const OPENAI_KEYS = 'https://platform.openai.com/api-keys';

export async function initAi(el, { username }) {
  const path = `/users/${encodeURIComponent(username)}/ai`;
  let state = await api(path);
  if (!state) return;
  let models = null; // the list of the key's models, asked the first time it is needed
  let changing = false; // the key field is open although there is a key (to replace it)
  let spend = null; // what the player has used of the AI, asked the first time and when the month changes
  let spendMonth = ''; // '' is all of it

  // What each card last said: the screen is drawn again when the models or the spending arrive, and a message must survive it
  const notes = { key: null, model: null };
  const tell = (where, message, ok = false) => {
    notes[where] = message ? { message, ok } : null;
    flash(el.querySelector(`[data-msg="${where}"]`), message, ok);
  };
  const say = (message, ok = false) => tell('key', message, ok);

  function keyCard() {
    const { key } = state;
    const form = !key.has_key || changing;
    return html`
      ${sectionTitle('Tu clave de OpenAI')}
      <div class="pf-card pf-form">
        <div class="pf-sub">Con tu propia clave puedes usar la guía de cada juego y seguir con el chat cuando se agote el presupuesto del grupo (o tu parte). El coste de lo que preguntes con ella va a tu cuenta de OpenAI. Se guarda cifrada y <strong>nadie puede verla</strong> desde la app, ni siquiera un administrador; solo puedes quitarla o cambiarla tú.</div>
        ${key.unreadable ? html`<div class="pf-msg err">No se puede abrir la clave que tenías guardada. Vuelve a guardarla.</div>` : ''}
        ${key.has_key ? html`<div class="ai-saved"><strong>${keyText(key)}</strong> <span class="pf-sub">· modelo ${key.model}</span></div>` : ''}
        ${form ? html`
          <form class="pf-form" data-form="key" autocomplete="off" novalidate>
            <label>${key.has_key ? 'Clave nueva' : 'Clave de OpenAI'}
              <input class="adm-input" type="password" name="api_key" placeholder="sk-…" autocomplete="off" spellcheck="false" />
            </label>
            <div><button class="pf-btn primary" type="submit">${key.has_key ? 'Guardar la clave nueva' : 'Guardar clave'}</button>
              ${changing ? html`<button class="pf-btn" type="button" data-act="cancel">Cancelar</button>` : ''}</div>
            <div class="pf-sub">Se comprueba con OpenAI al guardarla; esa comprobación no gasta nada. Te recomendamos crear en <a href="${OPENAI_KEYS}" target="_blank" rel="noopener noreferrer">platform.openai.com</a> un proyecto solo para La Viciación con un <strong>límite de gasto mensual</strong> y usar una clave de ese proyecto: así lo máximo que puede costarte es lo que fijes.</div>
          </form>` : html`
          <div><button class="pf-btn" type="button" data-act="change">Cambiar la clave</button> <button class="pf-btn" type="button" data-act="remove">Quitar la clave</button></div>`}
        <div class="pf-msg" data-msg="key" role="status"></div>
      </div>`;
  }

  function modelCard() {
    if (!state.key.has_key) return '';
    return html`
      ${sectionTitle('Modelo')}
      <div class="pf-card pf-form">
        <div class="pf-sub">El modelo lo eliges tú y su coste va a tu cuenta: los más potentes cuestan mucho más por pregunta. Los precios son orientativos, por millón de tokens (entrada / salida). La guía busca en internet, y cada búsqueda se cobra aparte; hace falta un modelo que lo admita.</div>
        ${models
          ? html`<label>Modelo
              <select class="adm-input" name="model">
                ${models.models.some((m) => m.id === state.key.model) ? '' : html`<option value="${state.key.model}" selected>${state.key.model}</option>`}
                ${models.models.map((m) => html`<option value="${m.id}" ${m.id === state.key.model ? 'selected' : ''}>${modelLabel(m)}</option>`)}
              </select></label>`
          : html`<div class="pf-sub">Cargando los modelos de tu cuenta…</div>`}
        <div><button class="pf-btn" type="button" data-act="test">Probar con la guía</button>
          <span class="pf-sub">Hace una pregunta con una búsqueda web: gasta unos céntimos de tu cuenta.</span></div>
        <div class="pf-msg" data-msg="model" role="status"></div>
      </div>`;
  }

  // Where the cost goes, as a quiet note above the key and not a section of its own
  function costNoteView() {
    const lines = state.budget ? budgetLines(state.budget) : [];
    const stopped = FEATURES.map(([id]) => blockedText(state[id])).find(Boolean);
    const note = costNote(state);
    if (!note && !lines.length && !stopped) return '';
    return html`
      <div class="ai-cost-note" role="note">
        <span class="ai-cost-icon" aria-hidden="true">i</span>
        <div class="ai-cost-text">
          ${note ? html`<div>${note}</div>` : ''}
          ${lines.length ? html`<div class="ai-budget">${lines.map((line) => html`<div>${line}</div>`)}</div>` : ''}
          ${stopped ? html`<div class="ai-stopped">${stopped} ${state.key.has_key ? '' : 'Mientras tanto puedes seguir con tu propia clave de OpenAI.'}</div>` : ''}
        </div>
      </div>`;
  }

  function spendCard() {
    if (!spend) return '';
    const { own, group } = paidBy(spend);
    const months = spend.months.map((m) => m.month).reverse();
    const tile = (value, label) => html`<div class="pf-stat"><div class="pf-stat-value">${value}</div><div class="pf-stat-label">${label}</div></div>`;
    const list = (items, label) => items.map((i) => html`<li><span>${label(i.name)}</span> <span class="pf-sub">${i.calls} ${i.calls === 1 ? 'pregunta' : 'preguntas'} · ${i.unpriced === i.calls && i.calls ? 'sin precio' : money(i.cost)}</span></li>`);
    return html`
      ${sectionTitle('Tu gasto')}
      <div class="pf-card" data-spend>
        <div class="pf-sub">Lo que has usado de la IA con tu cuenta, según el registro de tus preguntas (no se guarda lo que escribes, solo cuántas y cuánto pesaron). El coste es una <strong>estimación</strong> con los precios de cada modelo: lo que de verdad te cobra OpenAI lo ves en tu cuenta de OpenAI.</div>
        ${months.length ? html`<label>Periodo
          <select class="adm-input" name="spend-month">
            <option value="" ${spendMonth === '' ? 'selected' : ''}>Todo</option>
            ${months.map((m) => html`<option value="${m}" ${m === spendMonth ? 'selected' : ''}>${monthLabel(m)}</option>`)}
          </select></label>` : ''}
        ${spend.total.calls
    ? html`
          <div class="pf-stats">
            ${tile(money(own), 'Coste con tu clave')}
            ${tile(money(group), 'Coste cubierto por el grupo')}
            ${tile(spend.total.calls, 'Preguntas')}
            ${tile(`${tokens(spend.total.input_tokens)} / ${tokens(spend.total.output_tokens)}`, 'Tokens (entrada / salida)')}
          </div>
          <ul class="ai-spend-list" data-by="feature">${list(spend.by_feature, featureLabel)}</ul>
          <ul class="ai-spend-list" data-by="model">${list(spend.by_model, (name) => name)}</ul>
          ${spendMonth
    ? html`<ul class="ai-spend-list" data-by="day">${spend.days.map((d) => html`<li><span>${d.date}</span> <span class="pf-sub">${d.calls} · ${money(d.cost)}</span></li>`)}</ul>`
    : html`<ul class="ai-spend-list" data-by="month">${spend.months.slice().reverse().map((m) => html`<li><span>${monthLabel(m.month)}</span> <span class="pf-sub">${m.calls} · tu clave ${money(m.user_cost)} · grupo ${money(m.group_cost)}</span></li>`)}</ul>`}`
    : html`<div class="pf-sub">${spendMonth ? 'No has usado la IA ese mes.' : 'Todavía no has usado la IA.'}</div>`}
      </div>`;
  }

  function render() {
    const draft = el.querySelector('[name="api_key"]')?.value ?? '';
    mount(el, html`${costNoteView()}${keyCard()}${modelCard()}${spendCard()}`);
    const field = el.querySelector('[name="api_key"]');
    if (field && draft) field.value = draft; // what was being typed survives a redraw (the models arriving, the spending loading)
    for (const [where, note] of Object.entries(notes)) if (note) flash(el.querySelector(`[data-msg="${where}"]`), note.message, note.ok);
  }

  async function loadModels() {
    if (!state.key.has_key || models) return;
    try {
      models = await api(`${path}/models`);
    } catch (err) {
      models = { models: [], current: state.key.model };
      render();
      tell('model', err.message);
      return;
    }
    render();
  }

  async function loadSpend() {
    try {
      spend = await api(`${path}/usage${spendMonth ? `?month=${spendMonth}` : ''}`);
    } catch {
      return; // optional: the rest of the screen works without it
    }
    render();
  }

  async function refresh() {
    forgetGuideStatus(); // whether the game page offers the guide depends on whose key pays
    notes.model = null;
    state = await api(path);
    models = null;
    changing = false;
    render();
    loadModels();
    loadSpend();
  }

  async function saveKey(form) {
    const value = form.elements.api_key.value;
    if (!looksLikeKey(value)) return say('Eso no parece una clave de OpenAI: empieza por sk-');
    say('Comprobando la clave con OpenAI…', true);
    try {
      await api(path, jsonRequest('PUT', { api_key: value.trim() }));
      form.reset();
      await refresh();
      say('Clave guardada', true);
    } catch (err) {
      form.elements.api_key.value = '';
      say(err.message);
    }
  }

  async function chooseModel(select) {
    try {
      await api(path, jsonRequest('PUT', { model: select.value }));
      state = await api(path);
      tell('model', `Modelo guardado: ${select.value}`, true);
    } catch (err) {
      tell('model', err.message);
    }
  }

  async function test(button) {
    button.disabled = true;
    tell('model', 'Probando… (puede tardar unos segundos)', true);
    try {
      const result = await api(`${path}/test`, { method: 'POST' });
      tell('model', `Funciona con ${result.model}: ${result.reply}`, true);
    } catch (err) {
      tell('model', err.message);
    } finally {
      button.disabled = false;
    }
  }

  async function remove() {
    try {
      await api(path, { method: 'DELETE' });
      await refresh();
      say('Clave quitada: se ha borrado de la aplicación', true);
    } catch (err) {
      say(err.message);
    }
  }

  el.addEventListener('submit', (e) => {
    const form = e.target.closest('[data-form="key"]');
    if (!form) return;
    e.preventDefault();
    saveKey(form);
  });
  el.addEventListener('change', (e) => {
    if (e.target.name === 'model') chooseModel(e.target);
    else if (e.target.name === 'spend-month') {
      spendMonth = e.target.value;
      loadSpend();
    }
  });
  el.addEventListener('click', (e) => {
    const button = e.target.closest('[data-act]');
    if (!button) return;
    if (button.dataset.act === 'change') { changing = true; render(); } else if (button.dataset.act === 'cancel') { changing = false; render(); } else if (button.dataset.act === 'remove') remove();
    else if (button.dataset.act === 'test') test(button);
  });

  render();
  loadModels();
  loadSpend();
}
