// Home: time tracking (timer card + latest games).
import { html, mount } from '../../lib/html.js';
import { loadPlatforms } from '../../lib/platforms.js';
import { closeAllModals } from '../../ui/modal.js';
import { openCompletion } from './completion.js';
import { initGamePicker, startTimerFlow } from './game-picker.js';
import { initHistory, loadHistory, onHistoryClick, onHistoryKey } from './history.js';
import { initSessions, openManualSession, openSessionForm } from './sessions.js';
import { hasActive, initTimer, loadTimerCard, startTimer, stopClock } from './timer.js';

export const active = 'home';

/** Re-render only the timer card and the history, keeping the page in place. */
async function refresh() {
  stopClock();
  await loadTimerCard();
  await loadHistory(true);
}

export async function render({ user, main, isCurrent }) {
  await loadPlatforms();
  if (!isCurrent()) return;

  mount(main, html`
    <section id="timerSection" aria-label="Timer">
      <div class="loading-spinner">Cargando timer...</div>
    </section>

    <div class="section-header sessions-head">
      <h2 class="section-title">Mis sesiones</h2>
      <div class="section-line"></div>
    </div>
    <div class="manual-session-row">
      <button class="btn-manual" id="manualSessionBtn">+ Sesión manual</button>
    </div>
    <div id="historyList" class="history-list">
      <div class="loading-spinner">Cargando historial...</div>
    </div>
    <div class="history-more" id="historyMore"></div>`);

  initTimer({ userId: user.id, onChange: refresh, onChoose: startTimerFlow });
  initGamePicker(user.id);
  initSessions({ userId: user.id, onChange: refresh });
  initHistory({
    userId: user.id,
    onContinue: (group) => startTimer(group.game_id, group.platform),
    onComplete: (group) => openCompletion({ username: user.username, game: { id: group.game_id, name: group.game_name || group.game_id, score: group.score }, onChange: refresh }),
    onEditSession: (group, session) => openSessionForm({ game: { id: group.game_id, name: group.game_name || group.game_id }, session }),
  });
  main.querySelector('#manualSessionBtn').addEventListener('click', openManualSession);
  main.querySelector('#historyList').addEventListener('click', onHistoryClick);
  main.querySelector('#historyList').addEventListener('keydown', onHistoryKey);
  main.querySelector('#historyMore').addEventListener('click', onHistoryClick);

  // Active timer first: it decides whether "Seguir" buttons are enabled.
  await loadTimerCard();
  if (!isCurrent()) return;
  await loadHistory(true);

  if (location.hash === '#/new') {
    // the shortcut of the installed app: pick a game, unless a timer is already running
    history.replaceState(null, '', location.pathname);
    if (!hasActive && isCurrent()) startTimerFlow();
  }
}

export function dispose() {
  stopClock();
  closeAllModals();
}
