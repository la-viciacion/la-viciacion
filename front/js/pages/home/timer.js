// Timer card: shows the running timer (live clock) or the "start one" prompt,
// and starts/stops timers through the API.
import { api, jsonRequest } from '../../lib/api.js';
import { formatClock, formatDuration, formatRelative } from '../../lib/format.js';
import { html, mount } from '../../lib/html.js';
import { auraColor } from '../../lib/timer-aura.js';
import { iconPlay, iconStop } from '../../ui/icons.js';
import { scoreBadge } from '../../ui/score-badge.js';
import { toast } from '../../ui/toast.js';

let userId = null;
let onChange = () => {};
let onChoose = () => {};
let onContinue = () => {};
let clock = null;
let loadedAt = 0;
let listening = false;
const REFRESH_AFTER_MS = 20_000; // coming back to the tab after longer than this asks the server again

/** True while the user has a running timer (the history disables "Seguir"). */
export let hasActive = false;

/** onChange: a timer was started/stopped; onChoose: "Nuevo timer" was pressed; onContinue(group): "Continuar" on the last game. */
export function initTimer(options) {
  ({ userId, onChange, onChoose, onContinue } = options);
  hasActive = false;
  if (!listening) {
    listening = true;
    // the timer may have been stopped from another device while this tab slept or sat in the background
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible' && document.getElementById('timerSection') && Date.now() - loadedAt > REFRESH_AFTER_MS) onChange();
    });
  }
}

export function stopClock() {
  if (clock) clearInterval(clock);
  clock = null;
}

function startClock(startTime) {
  stopClock();
  const tick = () => {
    const el = document.getElementById('timerDuration');
    const seconds = (Date.now() - new Date(startTime)) / 1000;
    if (el) el.textContent = formatClock(seconds);
    document.querySelector('.timer-active')?.style.setProperty('--aura', auraColor(seconds));
  };
  tick();
  clock = setInterval(tick, 1000);
}

const activeCard = (timer, gameName, score) => html`
  <div class="timer-active">
    <div class="timer-info">
      <div class="timer-label"><span class="live-dot"></span> Jugando ahora</div>
      <div class="timer-game">${gameName || timer.game_id} ${scoreBadge(score)}</div>
      <div class="timer-duration" id="timerDuration">00:00:00</div>
    </div>
    <div class="timer-actions">
      <button class="btn-cancel-timer" id="cancelTimerBtn" data-timer-id="${timer.id}">Cancelar</button>
      <button class="btn-stop-timer" id="stopTimerBtn" data-timer-id="${timer.id}">${iconStop()} Detener</button>
    </div>
  </div>`;

const unknownCard = () => html`
  <div class="timer-idle">
    <div class="timer-idle-text">
      <div class="timer-idle-title">No se ha podido comprobar tu timer</div>
      <div class="timer-idle-sub">Si tienes uno en marcha, sigue contando. Vuelve a intentarlo.</div>
    </div>
    <button class="btn-start-timer" id="retryTimerBtn">Reintentar</button>
  </div>`;

const idleCard = () => html`
  <div class="timer-idle">
    <div class="timer-idle-text">
      <div class="timer-idle-title">¿A qué toca jugar?</div>
      <div class="timer-idle-sub">Inicia un timer y registra tu sesión.</div>
    </div>
    <button class="btn-start-timer" id="chooseGameBtn">${iconPlay()} Nuevo timer</button>
  </div>`;

// With a latest game, "Continuar" is the main action and "Nuevo timer" stays one press away.
const resumeCard = (last) => html`
  <div class="timer-idle timer-resume">
    ${last.image_url
      ? html`<img src="${last.image_url}" alt="" class="timer-resume-cover" />`
      : html`<div class="timer-resume-cover timer-resume-placeholder" aria-hidden="true">🎮</div>`}
    <div class="timer-idle-text">
      <div class="timer-resume-label">Seguir donde lo dejaste</div>
      <div class="timer-idle-title">${last.game_name || last.game_id} ${scoreBadge(last.score)}</div>
      <div class="timer-idle-sub">${formatRelative(last.last_played)} · ${formatDuration(last.total_seconds)}${last.session_count > 1 ? ' en total' : ''}</div>
    </div>
    <div class="timer-resume-actions">
      <button class="btn-start-timer" id="continueGameBtn">${iconPlay()} Continuar</button>
      <button class="btn-new-timer" id="chooseGameBtn">+ Nuevo timer</button>
    </div>
  </div>`;

/** The game played last (the first of the grouped history), or null when there is none or it can't be fetched. */
async function fetchLastGame() {
  try {
    const page = await api(`/timers/history/${userId}/grouped?limit=1&offset=0`);
    return page?.groups?.[0] || null;
  } catch (err) {
    console.error('Error fetching the last game:', err);
    return null;
  }
}

export async function loadTimerCard() {
  const section = document.getElementById('timerSection');
  if (!section) return;

  const hadActive = hasActive;
  loadedAt = Date.now();
  let active;
  try {
    active = await api(`/timers/active/${userId}`);
  } catch (err) {
    console.error('Error fetching timer:', err);
    // not knowing is not "no timer": a card that offers a new one over a running one would be wrong
    if (hadActive) return;
    if (!section.isConnected) return;
    mount(section, unknownCard());
    document.getElementById('retryTimerBtn').addEventListener('click', () => onChange());
    return;
  }
  hasActive = false;
  if (active?.is_active && active.timer) {
    hasActive = true;
    if (!section.isConnected) return; // page was re-rendered meanwhile
    mount(section, activeCard(active.timer, active.game_name, active.score));
    document.getElementById('stopTimerBtn').addEventListener('click', (e) => stopTimer(e.currentTarget.dataset.timerId));
    document.getElementById('cancelTimerBtn').addEventListener('click', (e) => cancelTimer(e.currentTarget.dataset.timerId));
    startClock(active.timer.start_time);
    return;
  }
  stopClock();
  const last = await fetchLastGame();
  if (!section.isConnected) return;
  mount(section, last ? resumeCard(last) : idleCard());
  document.getElementById('chooseGameBtn').addEventListener('click', () => onChoose());
  document.getElementById('continueGameBtn')?.addEventListener('click', () => onContinue(last));
}

export async function startTimer(gameId, platform = null) {
  try {
    const started = await api('/timers/start', jsonRequest('POST', {
      user_id: userId,
      game_id: gameId,
      platform,
    }));
    if (started) await onChange();
  } catch (err) {
    console.error('Error starting timer:', err);
    toast(`Error al iniciar el timer: ${err.message}`, 'err');
  }
}

// Cancelling deletes the timer for good: the first click asks, the second (within 4 s) confirms.
async function cancelTimer(timerId) {
  const button = document.getElementById('cancelTimerBtn');
  if (!button.dataset.armed) {
    button.dataset.armed = '1';
    button.textContent = '¿Seguro? Pulsa otra vez';
    setTimeout(() => {
      if (button.isConnected) { delete button.dataset.armed; button.textContent = 'Cancelar'; }
    }, 4000);
    return;
  }
  try {
    const cancelled = await api(`/timers/cancel/${timerId}?user_id=${userId}`, { method: 'DELETE' });
    if (cancelled) {
      toast('Timer cancelado');
      await onChange();
    }
  } catch (err) {
    console.error('Error cancelling timer:', err);
    toast(`Error al cancelar el timer: ${err.message}`, 'err');
    if (err.status === 404) await onChange(); // already gone (another device): show what is true now
  }
}

async function stopTimer(timerId) {
  try {
    const stopped = await api(`/timers/stop/${timerId}?user_id=${userId}`, { method: 'POST' });
    if (stopped) await onChange();
  } catch (err) {
    console.error('Error stopping timer:', err);
    toast(`Error al detener el timer: ${err.message}`, 'err');
    if (err.status === 404) await onChange(); // already stopped (another device): show what is true now
  }
}
