// The floating chat: a round button at the bottom right that opens a panel (a full-screen sheet on a phone).
//
// It lives outside #app, so changing page does not close it nor lose the conversation; it goes away with the
// session (unmountChat). The conversation is kept in memory only: the API stores nothing of it.
import { api, jsonRequest } from '../lib/api.js';
import { MAX_QUESTION, parseAnswer, pickSuggestions, toRequest } from '../lib/chat.js';
import { html, mount } from '../lib/html.js';
import { iconClose } from './icons.js';

const ID = 'chat-root';
const ICON_CHAT = html`<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 15a2 2 0 0 1-2 2H8l-5 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/><circle cx="9" cy="10" r="0.6" fill="currentColor"/><circle cx="13" cy="10" r="0.6" fill="currentColor"/><circle cx="17" cy="10" r="0.6" fill="currentColor"/></svg>`;

let turns = []; // { role: 'user' | 'assistant' | 'error', content, failed? }
let suggestions = pickSuggestions(); // the questions offered while the conversation is empty: others each time one starts
let open = false;
let busy = false;
let abort = null;
let cleanup = null;
let switchedOff = false; // the API said the chat is off (503): the button goes when the panel is closed

const root = () => document.getElementById(ID);

const part = (p) => (p.bold ? html`<strong>${p.text}</strong>` : p.text);

function answerMarkup(text) {
  return parseAnswer(text).map((b) => (
    b.type === 'ul'
      ? html`<ul>${b.items.map((item) => html`<li>${item.map(part)}</li>`)}</ul>`
      : html`<p>${b.parts.map(part)}</p>`
  ));
}

function bubble(turn) {
  if (turn.role === 'user') return html`<div class="chat-msg chat-me">${turn.content}</div>`;
  if (turn.role === 'error') return html`<div class="chat-msg chat-error" role="alert">${turn.content}</div>`;
  return html`<div class="chat-msg chat-bot">${answerMarkup(turn.content)}</div>`;
}

function welcome() {
  return html`
    <div class="chat-welcome">
      <p><strong>¡Hola!</strong> Pregúntame por juegos, horas, rankings, rachas o logros del grupo.</p>
      <div class="chat-suggestions">
        ${suggestions.map((s) => html`<button type="button" class="chat-chip" data-suggestion="${s}">${s}</button>`)}
      </div>
    </div>`;
}

function panel() {
  return html`
    <section class="chat-panel" role="dialog" aria-label="Asistente de La Viciación" ${open ? '' : 'hidden'}>
      <header class="chat-head">
        <strong>Asistente</strong>
        <span class="chat-head-actions">
          <button type="button" class="chat-icon-btn" data-reset aria-label="Empezar una conversación nueva" title="Conversación nueva" ${turns.length ? '' : 'hidden'}>↺</button>
          <button type="button" class="chat-icon-btn" data-close aria-label="Cerrar el chat">${iconClose()}</button>
        </span>
      </header>
      <div class="chat-log" role="log" aria-live="polite" tabindex="-1">
        ${turns.length ? turns.map(bubble) : welcome()}
        ${busy ? html`<div class="chat-msg chat-bot chat-typing" aria-label="Escribiendo"><span></span><span></span><span></span></div>` : ''}
      </div>
      <form class="chat-form" autocomplete="off">
        <textarea class="chat-input" rows="1" maxlength="${MAX_QUESTION}" placeholder="Pregunta algo…" aria-label="Tu pregunta" ${busy ? 'disabled' : ''}></textarea>
        <button type="submit" class="chat-send" aria-label="Enviar" ${busy ? 'disabled' : ''}>➤</button>
      </form>
    </section>`;
}

function render() {
  const el = root();
  if (!el) return;
  const draft = el.querySelector('.chat-input')?.value ?? '';
  mount(el, html`
    <button type="button" class="chat-fab" data-toggle aria-label="${open ? 'Cerrar el chat' : 'Abrir el chat'}" aria-expanded="${open}" ${open ? 'hidden' : ''}>${ICON_CHAT}</button>
    ${panel()}`);
  const input = el.querySelector('.chat-input');
  input.value = draft;
  const log = el.querySelector('.chat-log');
  log.scrollTop = log.scrollHeight;
  if (open && !busy) input.focus();
}

async function send(text) {
  const question = text.trim();
  if (!question || busy) return;
  const body = toRequest(turns, question);
  turns.push({ role: 'user', content: body.message });
  busy = true;
  const mine = new AbortController();
  abort = mine;
  render();
  try {
    const answer = await api('/chat', { ...jsonRequest('POST', body), signal: mine.signal });
    if (!answer) return; // 401: the session ended and the widget with it
    turns.push({ role: 'assistant', content: answer.answer });
  } catch (err) {
    if (err.name === 'AbortError') return;
    if (err.status === 503) switchedOff = true;
    turns[turns.length - 1].failed = true;
    turns.push({ role: 'error', content: err.message || 'No he podido responder. Inténtalo de nuevo' });
  } finally {
    // a reset (or a new question after it) may have taken over while this one was in flight
    if (abort === mine) {
      busy = false;
      abort = null;
      render();
    }
  }
}

function setOpen(value) {
  open = value;
  if (!open && switchedOff) return unmountChat();
  render();
  if (!open) root()?.querySelector('.chat-fab')?.focus();
}

function reset() {
  abort?.abort();
  abort = null;
  turns = [];
  suggestions = pickSuggestions();
  busy = false;
  render();
}

function onClick(e) {
  const target = e.target.closest('button');
  if (!target) return;
  if (target.matches('[data-toggle]')) setOpen(true);
  else if (target.matches('[data-close]')) setOpen(false);
  else if (target.matches('[data-reset]')) reset();
  else if (target.matches('[data-suggestion]')) send(target.dataset.suggestion);
}

function onSubmit(e) {
  e.preventDefault();
  const input = e.target.querySelector('.chat-input');
  const text = input.value;
  input.value = '';
  send(text);
}

// Enter sends, Shift+Enter breaks the line; the box grows with the text up to a few lines
function onKeydown(e) {
  if (!e.target.matches('.chat-input')) return;
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    e.target.form.requestSubmit();
  }
}

function onInput(e) {
  if (!e.target.matches('.chat-input')) return;
  e.target.style.height = 'auto';
  e.target.style.height = `${Math.min(e.target.scrollHeight, 120)}px`;
}

// The story player is full screen: the button would sit on top of it
const hiddenHere = () => location.hash.startsWith('#/story');

function syncVisibility() {
  const el = root();
  if (el) el.hidden = hiddenHere();
}

/** Puts the button on the page if the API says the chat can answer (once per session; calling it again does nothing). */
export async function mountChat() {
  if (root()) return;
  let status;
  try {
    status = await api('/chat/status');
  } catch {
    return; // optional: a failure here must never show on any page
  }
  if (!status?.available || root()) return;
  const el = document.createElement('div');
  el.id = ID;
  document.body.append(el);
  render();
  const onEscape = (e) => { if (e.key === 'Escape' && open) setOpen(false); };
  el.addEventListener('click', onClick);
  el.addEventListener('submit', onSubmit);
  el.addEventListener('keydown', onKeydown);
  el.addEventListener('input', onInput);
  document.addEventListener('keydown', onEscape);
  window.addEventListener('hashchange', syncVisibility);
  cleanup = () => {
    document.removeEventListener('keydown', onEscape);
    window.removeEventListener('hashchange', syncVisibility);
  };
  syncVisibility();
}

/** Takes the button away and forgets the conversation (the session ended). */
export function unmountChat() {
  abort?.abort();
  cleanup?.();
  root()?.remove();
  turns = [];
  suggestions = pickSuggestions();
  open = false;
  busy = false;
  cleanup = null;
  switchedOff = false;
}
