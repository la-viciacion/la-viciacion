// The game guide: a card on the game page where the player asks for help with that game (POST /guide/{id}).
//
// It reuses the chat's bubbles and answer rendering. The conversation is kept in memory only (lib/guide.js), per game.
import { api, jsonRequest } from '../lib/api.js';
import { parseAnswer } from '../lib/chat.js';
import { LEVELS, MAX_QUESTION, conversationOf, guideAvailable, toGuideRequest } from '../lib/guide.js';
import { html, mount } from '../lib/html.js';
import { modalHeader, openModal } from './modal.js';

function part(p) {
  if (p.code) return html`<code>${p.text}</code>`;
  if (p.bold) return html`<strong>${p.text}</strong>`;
  if (p.italic) return html`<em>${p.text}</em>`;
  return p.text;
}

function answerMarkup(text) {
  return parseAnswer(text).map((b) => {
    const items = (list) => list.map((item) => html`<li>${item.map(part)}</li>`);
    if (b.type === 'ul') return html`<ul>${items(b.items)}</ul>`;
    if (b.type === 'ol') return html`<ol>${items(b.items)}</ol>`;
    return html`<p>${b.parts.map(part)}</p>`;
  });
}

function bubble(turn) {
  if (turn.role === 'user') return html`<div class="chat-msg chat-me">${turn.content}</div>`;
  if (turn.role === 'error') return html`<div class="chat-msg chat-error" role="alert">${turn.content}</div>`;
  return html`<div class="chat-msg chat-bot">${answerMarkup(turn.content)}</div>`;
}

/** Opens the guide of `game` ({ id, name }) in a dialog, with the conversation of its page. */
export function openGuide(game) {
  const modal = openModal(html`${modalHeader(`Guía: ${game.name}`)}<div class="gd-modal"></div>`, { wide: true, sheet: true });
  showGuide(modal.el.querySelector('.gd-modal'), game, { dialog: true });
  return modal;
}

/** Fills `el` with the guide of `game` ({ id, name }). Quiet when the API says the guide is not available.
 * In a dialog (`dialog`) it has no title of its own and starts open. */
export async function showGuide(el, game, { dialog = false } = {}) {
  if (!(await guideAvailable()) || !el.isConnected) return;

  const chat = conversationOf(game.id);
  let busy = false;
  let open = dialog || chat.turns.length > 0;

  function render() {
    const draft = el.querySelector('.chat-input')?.value ?? '';
    const level = LEVELS.find((l) => l.id === chat.level);
    mount(el, html`
      ${dialog ? '' : html`<div class="section-header"><h2 class="section-title">Guía del juego</h2><div class="section-line"></div></div>`}
      <div class="${dialog ? 'gd-card' : 'pf-card gd-card'}">
        ${open ? html`
          <fieldset class="gd-levels">
            <legend class="pf-sub">¿Cuánta ayuda quieres?</legend>
            ${LEVELS.map((l) => html`
              <label class="gd-level"><input type="radio" name="gd-level" value="${l.id}" ${l.id === chat.level ? 'checked' : ''} /> ${l.label}</label>`)}
          </fieldset>
          <div class="pf-sub gd-level-hint">${level.hint}</div>
          <div class="gd-log chat-log" role="log" aria-live="polite">
            ${chat.turns.length ? chat.turns.map(bubble) : html`<div class="chat-welcome">Cuéntame dónde te has atascado en <strong>${game.name}</strong> y cómo vas.</div>`}
            ${busy ? html`<div class="chat-msg chat-bot chat-typing" aria-label="Buscando"><span></span><span></span><span></span></div>` : ''}
          </div>
          <form class="chat-form gd-form" autocomplete="off">
            <textarea class="chat-input" rows="1" maxlength="${MAX_QUESTION}" placeholder="¿Dónde te has quedado?" aria-label="Tu pregunta" ${busy ? 'disabled' : ''}></textarea>
            <button type="submit" class="chat-send" aria-label="Enviar" ${busy ? 'disabled' : ''}>➤</button>
          </form>
          ${chat.turns.length ? html`<button type="button" class="pf-btn gd-reset" data-reset>Conversación nueva</button>` : ''}` : html`
          <div class="gd-intro">
            <span class="pf-sub">¿Atascado en ${game.name}? Te oriento sin destripar más de lo que pidas.</span>
            <button type="button" class="pf-btn" data-open>Pedir ayuda</button>
          </div>`}
      </div>`);
    const input = el.querySelector('.chat-input');
    if (input) input.value = draft;
    const log = el.querySelector('.gd-log');
    if (log) log.scrollTop = log.scrollHeight;
  }

  async function send(text) {
    const question = text.trim();
    if (!question || busy) return;
    const body = toGuideRequest(chat.turns, question, chat.level);
    chat.turns.push({ role: 'user', content: body.message });
    busy = true;
    render();
    try {
      const answer = await api(`/guide/${encodeURIComponent(game.id)}`, jsonRequest('POST', body));
      if (answer) chat.turns.push({ role: 'assistant', content: answer.answer });
    } catch (err) {
      chat.turns[chat.turns.length - 1].failed = true;
      chat.turns.push({ role: 'error', content: err.message || 'No he podido responder. Inténtalo de nuevo' });
    } finally {
      busy = false;
      if (el.isConnected) render();
    }
  }

  el.addEventListener('click', (e) => {
    const button = e.target.closest('button');
    if (button?.matches('[data-open]')) {
      open = true;
      render();
      el.querySelector('.chat-input')?.focus();
    } else if (button?.matches('[data-reset]') && !busy) {
      chat.turns.length = 0;
      render();
    }
  });
  el.addEventListener('change', (e) => {
    if (e.target.matches('input[name="gd-level"]')) {
      chat.level = e.target.value;
      render();
    }
  });
  el.addEventListener('submit', (e) => {
    e.preventDefault();
    const input = e.target.querySelector('.chat-input');
    const text = input.value;
    input.value = '';
    send(text);
  });
  el.addEventListener('keydown', (e) => {
    if (e.target.matches('.chat-input') && e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      e.target.form.requestSubmit();
    }
  });
  render();
}
