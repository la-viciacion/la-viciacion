// "Mi IA" of the Ajustes tab: the player's own OpenAI key for the chat and the game guide, and the model they want to use with it.
// GET/PUT/DELETE /users/{username}/ai, GET /ai/models and POST /ai/test. The key is checked by the API with OpenAI before it is
// kept, it is stored encrypted and it never comes back: the screen only knows whether there is one and its last characters.
import { api, jsonRequest } from '../../lib/api.js';
import { forgetGuideStatus } from '../../lib/guide.js';
import { html, mount } from '../../lib/html.js';
import { FEATURES, keyText, looksLikeKey, modelLabel, payerText } from '../../lib/user-ai.js';
import { sectionTitle } from '../../ui/profile-summary.js';
import { flash } from './flash.js';

const OPENAI_KEYS = 'https://platform.openai.com/api-keys';

export async function initAi(el, { username }) {
  const path = `/users/${encodeURIComponent(username)}/ai`;
  let state = await api(path);
  if (!state) return;
  let models = null; // the list of the key's models, asked the first time it is needed
  let changing = false; // the key field is open although there is a key (to replace it)

  const say = (message, ok = false) => flash(el.querySelector('[data-msg="key"]'), message, ok);

  function keyCard() {
    const { key } = state;
    const form = !key.has_key || changing;
    return html`
      ${sectionTitle('Tu clave de OpenAI')}
      <div class="pf-card pf-form">
        <div class="pf-sub">Con tu propia clave, lo que preguntes al chat y a la guía se paga de tu cuenta de OpenAI y no del cupo del grupo. Se guarda cifrada y <strong>nadie puede verla</strong> desde la app, ni siquiera un administrador; solo puedes quitarla o cambiarla tú.</div>
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
        <div class="pf-sub">El modelo lo eliges tú y se paga de tu cuenta: los más potentes cuestan mucho más por pregunta. Los precios son orientativos, por millón de tokens (entrada / salida). La guía busca en internet, y cada búsqueda se cobra aparte; hace falta un modelo que lo admita.</div>
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

  function payersCard() {
    return html`
      ${sectionTitle('Quién paga')}
      <div class="pf-card">
        <ul class="ai-payers">
          ${FEATURES.map(([id, label]) => html`<li><strong>${label}.</strong> ${payerText({ ...state[id] })}</li>`)}
        </ul>
      </div>`;
  }

  function render() {
    mount(el, html`${payersCard()}${keyCard()}${modelCard()}`);
  }

  async function loadModels() {
    if (!state.key.has_key || models) return;
    try {
      models = await api(`${path}/models`);
    } catch (err) {
      models = { models: [], current: state.key.model };
      render();
      flash(el.querySelector('[data-msg="model"]'), err.message);
      return;
    }
    render();
  }

  async function refresh() {
    forgetGuideStatus(); // whether the game page offers the guide depends on whose key pays
    state = await api(path);
    models = null;
    changing = false;
    render();
    loadModels();
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
    const msg = el.querySelector('[data-msg="model"]');
    try {
      await api(path, jsonRequest('PUT', { model: select.value }));
      state = await api(path);
      flash(msg, `Modelo guardado: ${select.value}`, true);
    } catch (err) {
      flash(msg, err.message);
    }
  }

  async function test(button) {
    const msg = el.querySelector('[data-msg="model"]');
    button.disabled = true;
    flash(msg, 'Probando… (puede tardar unos segundos)', true);
    try {
      const result = await api(`${path}/test`, { method: 'POST' });
      flash(msg, `Funciona con ${result.model}: ${result.reply}`, true);
    } catch (err) {
      flash(msg, err.message);
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
  });
  el.addEventListener('click', (e) => {
    const button = e.target.closest('[data-act]');
    if (!button) return;
    if (button.dataset.act === 'change') { changing = true; render(); } else if (button.dataset.act === 'cancel') { changing = false; render(); } else if (button.dataset.act === 'remove') remove();
    else if (button.dataset.act === 'test') test(button);
  });

  render();
  loadModels();
}
