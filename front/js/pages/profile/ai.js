// "Mi IA" of the Ajustes tab: the player's own AI keys, one for each provider (OpenAI, Anthropic, Google, OpenRouter), the model they want
// to use with each and which provider comes first. GET /users/{username}/ai, PUT/DELETE /ai/{provider}, GET /ai/{provider}/models,
// POST /ai/{provider}/test, PUT /ai/preferred and POST /ai/unlock. A key is checked by the API with its provider before it is kept, it is
// sealed in a vault that only the player's password opens and it never comes back: the screen only knows whether there is one, its last
// characters while the session is unlocked and its model. A session that cannot open the vault is **locked**: the player types their
// password (POST /ai/unlock) and the API answers a new token, which carries the key that opens it.
import { api, jsonRequest, session } from '../../lib/api.js';
import { featureLabel, tokens } from '../../lib/ai-calls.js';
import { money, monthLabel } from '../../lib/ai-usage.js';
import { forgetGuideStatus } from '../../lib/guide.js';
import { html, mount } from '../../lib/html.js';
import { ABOUT, FEATURES, PROVIDERS, blockedText, budgetLines, costNote, hasAnyKey, keyText, looksLikeKey, modelLabel, paidBy, providerName } from '../../lib/user-ai.js';
import { walletLine } from '../../lib/ai-wallet.js';
import { iconChevron } from '../../ui/icons.js';
import { searchable } from '../../ui/combobox.js';
import { sectionTitle } from '../../ui/profile-summary.js';
import { flash } from './flash.js';

// What used to be paragraphs under the titles of Mi IA: each one is the "i" of its title now
const KEY_INFO = html`
  <p>Con tu propia clave puedes usar la guía de cada juego y seguir con el chat cuando se agote el presupuesto del grupo (o tu parte). Puedes guardar una clave de cada proveedor (OpenAI, Anthropic, Google u OpenRouter), y el coste de lo que preguntes con ella va a tu cuenta de ese proveedor.</p>
  <p>Se guarda cifrada con tu contraseña: solo se abre mientras tienes la sesión iniciada con ella, y ni una copia de la base de datos ni un administrador pueden leerla. Si recuperas la contraseña por correo o te la cambia un administrador, <strong>las claves se borran</strong> (nadie puede abrirlas sin la contraseña anterior) y hay que volver a guardarlas. Cambiar tú tu propia contraseña no las pierde.</p>
  <p>Se comprueba con el proveedor al guardarla; esa comprobación no gasta nada. Te recomendamos usar una clave creada solo para La Viciación con un <strong>límite de gasto mensual</strong>: así lo máximo que puede costarte es lo que fijes.</p>
  <p>El modelo de cada clave lo eliges tú y su coste va a tu cuenta: los más potentes cuestan mucho más por pregunta. Los precios son orientativos, por millón de tokens (entrada / salida). La guía busca en internet, y cada búsqueda se cobra aparte; hace falta un modelo que lo admita.</p>`;
const SPEND_INFO = html`<p>Lo que has usado de la IA con tu cuenta, según el registro de tus preguntas (no se guarda lo que escribes, solo cuántas y cuánto pesaron). El coste es una <strong>estimación</strong> con los precios de cada modelo: lo que de verdad te cobra el proveedor lo ves en tu cuenta de él.</p>`;
const PREFERRED_INFO = html`<p>Con claves de varios proveedores, esta es la que se usa primero. Si no eliges ninguna, la app usa la del proveedor que el grupo usa para esa función (si tienes clave de él) y, si no, la primera que tengas.</p>`;


export async function initAi(el, { username }) {
  const path = `/users/${encodeURIComponent(username)}/ai`;
  let state = await api(path);
  if (!state) return;
  const models = {}; // provider -> the list of the key's models, asked the first time it is needed
  let changing = null; // the provider whose key field is open although there is a key (to replace it)
  let spend = null; // what the player has used of the AI, asked the first time and when the month changes
  let spendMonth = ''; // '' is all of it
  let aboutOpen = false; // the section of what the chat and the guide do is folded until the player opens it

  // What each card last said: the screen is drawn again when the models or the spending arrive, and a message must survive it
  const notes = {};
  const tell = (where, message, ok = false) => {
    notes[where] = message ? { message, ok } : null;
    flash(el.querySelector(`[data-msg="${where}"]`), message, ok);
  };

  // What the chat and the guide do, what each costs and what the guide adds: so a player knows what they are choosing to use
  function aboutView() {
    const list = (items) => html`<ul class="ai-about-list">${items.map((item) => html`<li>${item}</li>`)}</ul>`;
    const { chat, guide } = ABOUT;
    return html`
      <details class="ai-fold" data-about-fold>
        <summary class="section-header ai-fold-head">
          <h2 class="section-title">Qué hacen el chat y la guía</h2><span class="ai-fold-chevron" aria-hidden="true">${iconChevron()}</span><div class="section-line"></div>
        </summary>
      <div class="ai-about">
        <div class="pf-card ai-about-card" data-about="chat">
          <h3>${chat.title}</h3>
          ${list(chat.what)}
          <div class="pf-sub ai-about-cost"><strong>Coste.</strong> ${chat.cost}</div>
        </div>
        <div class="pf-card ai-about-card" data-about="guide">
          <h3>${guide.title}</h3>
          ${list(guide.what)}
          <h4>${guide.addsTitle}</h4>
          ${list(guide.adds)}
          <div class="pf-sub ai-about-limit">${guide.limit}</div>
          <div class="pf-sub ai-about-cost"><strong>Coste.</strong> ${guide.cost}</div>
        </div>
      </div>
      </details>`;
  }

  const held = () => PROVIDERS.filter((p) => state.keys[p.id]?.has_key);

  // The password opens the keys of this session. Also needed to save the first one: nothing is kept without it
  function unlockCard() {
    if (state.unlocked) return '';
    return html`
      <div class="pf-card pf-form ai-locked" data-locked>
        <strong>${state.locked ? 'Tus claves están bloqueadas en esta sesión' : 'Para guardar una clave, confirma tu contraseña'}</strong>
        <div class="pf-sub">${state.locked
    ? 'Están cifradas con tu contraseña y esta sesión no la ha usado todavía (se abre sola al iniciar sesión; si la tenías abierta de antes, escríbela una vez).'
    : 'Las claves se cifran con tu contraseña: escríbela una vez en esta sesión para poder guardarlas.'}</div>
        <form class="pf-form" data-form="unlock" autocomplete="off" novalidate>
          <label>Tu contraseña <input class="adm-input" type="password" name="password" autocomplete="current-password" /></label>
          <div><button class="pf-btn primary" type="submit">${state.locked ? 'Desbloquear' : 'Confirmar'}</button></div>
        </form>
        <div class="pf-msg" data-msg="unlock" role="status"></div>
      </div>`;
  }

  function providerCard(provider) {
    const key = state.keys[provider.id];
    const form = !key.has_key || changing === provider.id;
    const list = models[provider.id];
    return html`
      <div class="pf-card pf-form ai-provider" data-provider="${provider.id}">
        <h3>${provider.name}</h3>
        ${key.unreadable ? html`<div class="pf-msg err">No se puede abrir la clave que tenías guardada. Vuelve a guardarla.</div>` : ''}
        ${key.has_key ? html`<div class="ai-saved"><strong>${keyText(key)}</strong> <span class="pf-sub">· modelo ${key.model}</span></div>` : html`<div class="pf-sub">Sin clave de ${provider.name}.</div>`}
        ${form ? html`
          <form class="pf-form" data-form="key" data-provider="${provider.id}" autocomplete="off" novalidate>
            <label>${key.has_key ? 'Clave nueva' : `Clave de ${provider.name}`}
              <input class="adm-input" type="password" name="api_key" placeholder="${provider.placeholder}" autocomplete="off" spellcheck="false" ${state.unlocked ? '' : html`disabled`} />
            </label>
            <div><button class="pf-btn primary" type="submit" ${state.unlocked ? '' : html`disabled`}>${key.has_key ? 'Guardar la clave nueva' : 'Guardar clave'}</button>
              ${changing === provider.id ? html`<button class="pf-btn" type="button" data-act="cancel">Cancelar</button>` : ''}</div>
            <div class="pf-sub">Se comprueba con ${provider.name} al guardarla (no gasta nada). ${provider.limit} <a href="${provider.url}" target="_blank" rel="noopener noreferrer">${provider.where}</a></div>
          </form>` : html`
          <div><button class="pf-btn" type="button" data-act="change" ${state.unlocked ? '' : html`disabled`}>Cambiar la clave</button> <button class="pf-btn" type="button" data-act="remove">Quitar la clave</button></div>`}
        ${key.has_key && state.unlocked && !key.unreadable ? (list
    ? html`<label>Modelo
              <select class="adm-input" name="model" data-provider="${provider.id}">
                ${list.models.some((m) => m.id === key.model) ? '' : html`<option value="${key.model}" selected>${key.model}</option>`}
                ${list.models.map((m) => html`<option value="${m.id}" ${m.id === key.model ? 'selected' : ''}>${modelLabel(m)}</option>`)}
              </select></label>
            <div><button class="pf-btn" type="button" data-act="test">Probar con la guía</button>
              <span class="pf-sub">Hace una pregunta con una búsqueda web: gasta unos céntimos de tu cuenta.</span></div>`
    : html`<div class="pf-sub">Cargando los modelos de tu cuenta…</div>`) : ''}
        <div class="pf-msg" data-msg="${provider.id}" role="status"></div>
      </div>`;
  }

  function keysCard() {
    return html`
      ${sectionTitle('Tus claves de IA', undefined, KEY_INFO)}
      ${unlockCard()}
      ${PROVIDERS.map(providerCard)}
      ${held().length ? html`
        <div class="pf-card pf-form" data-preferred>
          <label>Usar primero la clave de
            <select class="adm-input" name="preferred">
              <option value="" ${state.preferred ? '' : 'selected'}>La que elija la app</option>
              ${held().map((p) => html`<option value="${p.id}" ${p.id === state.preferred ? 'selected' : ''}>${p.name}</option>`)}
            </select></label>
          <div class="pf-sub">${PREFERRED_INFO.textContent}</div>
          <div class="pf-msg" data-msg="preferred" role="status"></div>
        </div>` : ''}`;
  }

  // Where the cost goes, as a quiet note above the key and not a section of its own
  function costNoteView() {
    const lines = [...(state.budget ? budgetLines(state.budget) : []), walletLine(state.wallet)].filter(Boolean);
    const stopped = FEATURES.map(([id]) => blockedText(state[id])).find(Boolean);
    const note = costNote({ chat: state.chat, guide: state.guide, keys: state.keys });
    if (!note && !lines.length && !stopped) return '';
    return html`
      <div class="ai-cost-note" role="note">
        <span class="ai-cost-icon" aria-hidden="true">i</span>
        <div class="ai-cost-text">
          ${note ? html`<div>${note}</div>` : ''}
          ${lines.length ? html`<div class="ai-budget">${lines.map((line) => html`<div>${line}</div>`)}</div>` : ''}
          ${stopped ? html`<div class="ai-stopped">${stopped} ${hasAnyKey(state.keys) ? '' : 'Mientras tanto puedes seguir con una clave tuya.'}</div>` : ''}
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
      ${sectionTitle('Tu gasto', undefined, SPEND_INFO)}
      <div class="pf-card" data-spend>
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
    const drafts = [...el.querySelectorAll('[name="api_key"], [name="password"]')].map((f) => [f.closest('[data-provider], [data-locked]')?.dataset.provider ?? 'unlock', f.name, f.value]);
    mount(el, html`${costNoteView()}${aboutView()}${keysCard()}${spendCard()}`);
    for (const [owner, name, value] of drafts) {
      const field = owner === 'unlock' ? el.querySelector('[data-locked] [name="password"]') : el.querySelector(`[data-provider="${owner}"] [name="${name}"]`);
      if (field && value) field.value = value; // what was being typed survives a redraw (the models arriving, the spending loading)
    }
    for (const select of el.querySelectorAll('select[name="model"]')) searchable(select); // a long list of models is searched, not scrolled
    for (const [where, note] of Object.entries(notes)) if (note) flash(el.querySelector(`[data-msg="${where}"]`), note.message, note.ok);
    const fold = el.querySelector('[data-about-fold]');
    fold.open = aboutOpen; // a redraw (the models arriving) keeps it as the player left it
    fold.addEventListener('toggle', () => { aboutOpen = fold.open; });
  }

  async function loadModels() {
    if (!state.unlocked) return;
    await Promise.all(held().filter((p) => !models[p.id] && !state.keys[p.id].unreadable).map(async (p) => {
      try {
        models[p.id] = await api(`${path}/${p.id}/models`);
      } catch (err) {
        models[p.id] = { models: [], current: state.keys[p.id].model };
        render();
        tell(p.id, err.message);
        return;
      }
      render();
    }));
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
    for (const id of Object.keys(notes)) if (id !== 'unlock') notes[id] = null;
    state = await api(path);
    for (const id of Object.keys(models)) delete models[id];
    changing = null;
    render();
    loadModels();
    loadSpend();
  }

  // 423: the session cannot open the vault. The state says so and the password box appears
  async function lockedAgain(err, where) {
    state = await api(path);
    render();
    tell('unlock', err.message);
    if (where) tell(where, '');
  }

  async function unlock(form) {
    const password = form.elements.password.value;
    if (!password) return tell('unlock', 'Escribe tu contraseña');
    tell('unlock', 'Comprobando…', true);
    try {
      const result = await api(`${path}/unlock`, jsonRequest('POST', { password }));
      session.setToken(result.access_token); // the new token carries the key that opens the vault
      state = { ...result };
      delete state.access_token;
      delete state.token_type;
      for (const id of Object.keys(models)) delete models[id];
      forgetGuideStatus();
      notes.unlock = null;
      render();
      loadModels();
    } catch (err) {
      form.elements.password.value = '';
      tell('unlock', err.message);
    }
  }

  async function saveKey(form) {
    const provider = PROVIDERS.find((p) => p.id === form.dataset.provider);
    const value = form.elements.api_key.value;
    if (!looksLikeKey(provider.id, value)) return tell(provider.id, `Eso no parece una clave de ${provider.name}: empieza por ${provider.placeholder.replace('…', '')}`);
    tell(provider.id, `Comprobando la clave con ${provider.name}…`, true);
    try {
      await api(`${path}/${provider.id}`, jsonRequest('PUT', { api_key: value.trim() }));
      form.reset();
      await refresh();
      tell(provider.id, 'Clave guardada', true);
    } catch (err) {
      form.elements.api_key.value = '';
      if (err.status === 423) return lockedAgain(err, provider.id);
      tell(provider.id, err.message);
    }
  }

  async function chooseModel(select) {
    const id = select.dataset.provider;
    try {
      await api(`${path}/${id}`, jsonRequest('PUT', { model: select.value }));
      state = await api(path);
      tell(id, `Modelo guardado: ${select.value}`, true);
    } catch (err) {
      tell(id, err.message);
    }
  }

  async function choosePreferred(select) {
    try {
      state = await api(`${path}/preferred`, jsonRequest('PUT', { provider: select.value || null }));
      forgetGuideStatus();
      tell('preferred', select.value ? `Se usará primero la clave de ${providerName(select.value)}` : 'La app elegirá la clave', true);
    } catch (err) {
      tell('preferred', err.message);
    }
  }

  async function test(button) {
    const id = button.closest('[data-provider]').dataset.provider;
    button.disabled = true;
    tell(id, 'Probando… (puede tardar unos segundos)', true);
    try {
      const result = await api(`${path}/${id}/test`, { method: 'POST' });
      tell(id, `Funciona con ${result.model}: ${result.reply}`, true);
    } catch (err) {
      if (err.status === 423) await lockedAgain(err, id);
      else tell(id, err.message);
    } finally {
      button.disabled = false;
    }
  }

  async function remove(id) {
    try {
      await api(`${path}/${id}`, { method: 'DELETE' });
      await refresh();
      tell(id, 'Clave quitada: se ha borrado de la aplicación', true);
    } catch (err) {
      tell(id, err.message);
    }
  }

  el.addEventListener('submit', (e) => {
    const form = e.target.closest('[data-form]');
    if (!form) return;
    e.preventDefault();
    if (form.dataset.form === 'unlock') unlock(form);
    else saveKey(form);
  });
  el.addEventListener('change', (e) => {
    if (e.target.name === 'model') chooseModel(e.target);
    else if (e.target.name === 'preferred') choosePreferred(e.target);
    else if (e.target.name === 'spend-month') {
      spendMonth = e.target.value;
      loadSpend();
    }
  });
  el.addEventListener('click', (e) => {
    const button = e.target.closest('[data-act]');
    if (!button) return;
    const id = button.closest('[data-provider]')?.dataset.provider;
    if (button.dataset.act === 'change') { changing = id; render(); } else if (button.dataset.act === 'cancel') { changing = null; render(); } else if (button.dataset.act === 'remove') remove(id);
    else if (button.dataset.act === 'test') test(button);
  });

  render();
  loadModels();
  loadSpend();
}
