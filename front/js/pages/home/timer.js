// Timer card: shows the running timer (live clock) or the "start one" prompt,
// and starts/stops timers through the API.
import { api, jsonRequest } from '../../lib/api.js';
import { formatClock } from '../../lib/format.js';
import { html, mount } from '../../lib/html.js';
import { iconPlay, iconStop } from '../../ui/icons.js';
import { toast } from '../../ui/toast.js';

let userId = null;
let onChange = () => {};
let onChoose = () => {};
let clock = null;

/** True while the user has a running timer (the history disables "Seguir"). */
export let hasActive = false;

/** onChange: a timer was started/stopped; onChoose: "Nuevo timer" was pressed. */
export function initTimer(options) {
  ({ userId, onChange, onChoose } = options);
  hasActive = false;
}

export function stopClock() {
  if (clock) clearInterval(clock);
  clock = null;
}

function startClock(startTime) {
  stopClock();
  const tick = () => {
    const el = document.getElementById('timerDuration');
    if (el) el.textContent = formatClock((Date.now() - new Date(startTime)) / 1000);
  };
  tick();
  clock = setInterval(tick, 1000);
}

const activeCard = (timer, game) => html`
  <div class="timer-active">
    <div class="timer-info">
      <div class="timer-label"><span class="live-dot"></span> Jugando ahora</div>
      <div class="timer-game">${game?.name || timer.game_id}</div>
      <div class="timer-duration" id="timerDuration">00:00:00</div>
    </div>
    <div class="timer-actions">
      <button class="btn-cancel-timer" id="cancelTimerBtn" data-timer-id="${timer.id}">Cancelar</button>
      <button class="btn-stop-timer" id="stopTimerBtn" data-timer-id="${timer.id}">${iconStop()} Detener</button>
    </div>
  </div>`;

const idleCard = () => html`
  <div class="timer-idle">
    <div class="timer-idle-text">
      <div class="timer-idle-title">¿A qué toca jugar?</div>
      <div class="timer-idle-sub">Inicia un timer y registra tu sesión.</div>
    </div>
    <button class="btn-start-timer" id="chooseGameBtn">${iconPlay()} Nuevo timer</button>
  </div>`;

export async function loadTimerCard() {
  const section = document.getElementById('timerSection');
  if (!section) return;

  hasActive = false;
  try {
    const active = await api(`/timers/active/${userId}`);
    if (active?.is_active && active.timer) {
      hasActive = true;
      const game = await api(`/games/${encodeURIComponent(active.timer.game_id)}`).catch(() => null);
      if (!section.isConnected) return; // page was re-rendered meanwhile
      mount(section, activeCard(active.timer, game));
      document.getElementById('stopTimerBtn').addEventListener('click', (e) => stopTimer(e.currentTarget.dataset.timerId));
      document.getElementById('cancelTimerBtn').addEventListener('click', (e) => cancelTimer(e.currentTarget.dataset.timerId));
      startClock(active.timer.start_time);
      return;
    }
  } catch (err) {
    console.error('Error fetching timer:', err);
  }
  if (!section.isConnected) return;
  mount(section, idleCard());
  document.getElementById('chooseGameBtn').addEventListener('click', () => onChoose());
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
  }
}

async function stopTimer(timerId) {
  try {
    const stopped = await api(`/timers/stop/${timerId}?user_id=${userId}`, { method: 'POST' });
    if (stopped) await onChange();
  } catch (err) {
    console.error('Error stopping timer:', err);
    toast(`Error al detener el timer: ${err.message}`, 'err');
  }
}
