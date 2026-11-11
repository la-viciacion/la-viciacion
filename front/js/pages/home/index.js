// Home: time tracking (timer card + latest games).
import { html, mount } from '../../lib/html.js';
import { ensurePlatforms } from '../../lib/platforms.js';
import { closeAllModals } from '../../ui/modal.js';
import { openCompletion } from './completion.js';
import { showMyChallenges } from './challenges.js';
import { initGamePicker, startTimerFlow } from './game-picker.js';
import { initHistory, loadHistory, onHistoryClick, onHistoryKey } from './history.js';
import { initSessions, openManualSession, openSessionForm } from './sessions.js';
import { hasActive, initTimer, loadTimerCard, startTimer, stopClock } from './timer.js';

export const active = 'home';

/** Re-render only the timer card and the history, keeping the page in place. */
async function refresh() {
  stopClock();
  await loadHistory(true, loadTimerCard());
}

export async function render({ user, main, isCurrent }) {
  mount(main, html`
    <section id="timerSection" aria-label="Timer">
      <div class="loading-spinner">Cargando timer...</div>
    </section>

    <section id="myChallenges" aria-label="Mis retos"></section>

    <div class="section-header sessions-head">
      <h2 class="section-title">Mis sesiones</h2>
      <div class="section-line"></div>
    </div>
    <div id="historyList" class="history-list">
      <div class="loading-spinner">Cargando historial...</div>
    </div>
    <div class="history-more" id="historyMore"></div>`);

  initTimer({
    userId: user.id,
    onChange: refresh,
    onChoose: startTimerFlow,
    onContinue: (group) => startTimer(group.game_id, group.platform),
    onManual: openManualSession,
  });
  initGamePicker(user.id);
  initSessions({ userId: user.id, onChange: refresh });
  initHistory({
    userId: user.id,
    onContinue: (group) => startTimer(group.game_id, group.platform),
    onComplete: (group) => openCompletion({ username: user.username, game: { id: group.game_id, name: group.game_name || group.game_id, score: group.score }, onChange: refresh }),
    onEditSession: (group, session) => openSessionForm({ game: { id: group.game_id, name: group.game_name || group.game_id }, session }),
  });
  main.querySelector('#historyList').addEventListener('click', onHistoryClick);
  main.querySelector('#historyList').addEventListener('keydown', onHistoryKey);
  main.querySelector('#historyMore').addEventListener('click', onHistoryClick);

  // Everything is asked at once; the history is drawn once the timer (it decides whether "Seguir" is enabled) and
  // the platforms (it names them) are known.
  showMyChallenges(main.querySelector('#myChallenges'), user.id);
  const ready = Promise.all([ensurePlatforms(), loadTimerCard()]);
  await loadHistory(true, ready);
  if (!isCurrent()) return;

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
