// ============================================================
//  La Viciación — PWA App
//  API: FastAPI + JWT (OAuth2PasswordRequestForm)
//  Routes used:
//    POST /api/v1/token          → login
//    GET  /api/v1/auth/active_user → get user info
//    GET  /api/v1/timers/history/{id}/grouped → session history per game
//    GET  /api/v1/users/{username}/avatar → avatar image
// ============================================================

const API_BASE = '/api/v1';

// ── Storage helpers ──────────────────────────────────────────
const storage = {
  getToken: () => localStorage.getItem('lv_token'),
  setToken: (t) => localStorage.setItem('lv_token', t),
  clearToken: () => localStorage.removeItem('lv_token'),
};

// ── API client ───────────────────────────────────────────────
async function apiFetch(path, options = {}) {
  const token = storage.getToken();
  const headers = { ...options.headers };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });

  if (res.status === 401) {
    storage.clearToken();
    renderLogin();
    return null;
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Error desconocido' }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }

  const ct = res.headers.get('content-type') || '';
  if (ct.includes('application/json')) return res.json();
  if (ct.includes('image/')) return res.blob();
  return res.text();
}

// ── Router ───────────────────────────────────────────────────
const app = document.getElementById('app');

function renderPage(html) {
  app.innerHTML = html;
}

// ── Login page ───────────────────────────────────────────────
function renderLogin() {
  renderPage(`
    <div class="login-page">
      <div class="login-card">
        <div class="login-brand">
          <img src="icon.svg" alt="La Viciación logo" class="login-logo" />
          <h1>La Viciación</h1>
          <p>Accede a tu cuenta de gamer</p>
        </div>

        <form id="loginForm" novalidate>
          <div class="form-group">
            <label for="username">Usuario</label>
            <div class="input-wrap">
              ${iconUser()}
              <input
                type="text"
                id="username"
                name="username"
                placeholder="tu_usuario"
                autocomplete="username"
                required
              />
            </div>
          </div>

          <div class="form-group">
            <label for="password">Contraseña</label>
            <div class="input-wrap">
              ${iconLock()}
              <input
                type="password"
                id="password"
                name="password"
                placeholder="••••••••••••"
                autocomplete="current-password"
                required
              />
              <button type="button" class="password-toggle" id="pwToggle" aria-label="Mostrar/ocultar contraseña">
                ${iconEye()}
              </button>
            </div>
          </div>

          <div class="login-error" id="loginError" role="alert"></div>

          <button type="submit" class="btn-primary" id="loginBtn">
            <span class="btn-text">Entrar</span>
            <div class="btn-spinner"></div>
          </button>
        </form>
      </div>
    </div>
  `);

  // Password toggle
  const pwToggle = document.getElementById('pwToggle');
  const pwInput = document.getElementById('password');
  let visible = false;
  pwToggle.addEventListener('click', () => {
    visible = !visible;
    pwInput.type = visible ? 'text' : 'password';
    pwToggle.innerHTML = visible ? iconEyeOff() : iconEye();
  });

  // Form submit
  document.getElementById('loginForm').addEventListener('submit', handleLogin);
}

async function handleLogin(e) {
  e.preventDefault();
  const btn = document.getElementById('loginBtn');
  const errorEl = document.getElementById('loginError');

  const username = document.getElementById('username').value.trim();
  const password = document.getElementById('password').value;

  errorEl.textContent = '';
  errorEl.classList.remove('visible');

  if (!username || !password) {
    showLoginError('Rellena todos los campos');
    return;
  }

  btn.disabled = true;
  btn.classList.add('loading');

  try {
    // OAuth2PasswordRequestForm requires application/x-www-form-urlencoded
    const body = new URLSearchParams({ username, password });
    const res = await fetch(`${API_BASE}/token`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body,
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Usuario o contraseña incorrectos');
    }

    const data = await res.json();
    storage.setToken(data.access_token);
    await renderHome();
  } catch (err) {
    showLoginError(err.message);
    btn.disabled = false;
    btn.classList.remove('loading');
  }
}

function showLoginError(msg) {
  const el = document.getElementById('loginError');
  if (!el) return;
  el.textContent = msg;
  el.classList.add('visible');
}

// ── Home page (time tracking) ────────────────────────────────
const HISTORY_PAGE_SIZE = 8;   // games per page in the history list
const historyState = { groups: [], total: 0, expanded: new Set(), hasActive: false, userId: null };

async function renderHome() {
  stopTimerDisplay();
  renderPage(`
    <div id="loading-overlay">
      <div class="spinner"></div>
    </div>
  `);

  try {
    const user = await apiFetch('/auth/active_user');
    if (!user) return;

    await loadPlatforms();
    const avatarBlob = await apiFetch(`/users/${user.username}/avatar`).catch(() => null);
    const avatarUrl = avatarBlob instanceof Blob ? URL.createObjectURL(avatarBlob) : null;

    historyState.userId = user.id;
    historyState.groups = [];
    historyState.total = 0;
    historyState.expanded = new Set();

    renderPage(`
      <div class="home-page">
        ${renderNavbar(user, avatarUrl)}

        <main class="home-main">
          <section id="timerSection" aria-label="Timer">
            <div class="loading-spinner">Cargando timer...</div>
          </section>

          <div class="section-header">
            <h2 class="section-title">Mis sesiones</h2>
            <div class="section-line"></div>
          </div>
          <div id="historyList" class="history-list">
            <div class="loading-spinner">Cargando historial...</div>
          </div>
          <div class="history-more" id="historyMore"></div>
        </main>
      </div>
    `);

    document.getElementById('logoutBtn').addEventListener('click', handleLogout);
    document.getElementById('historyList').addEventListener('click', onHistoryClick);
    document.getElementById('historyMore').addEventListener('click', (e) => {
      if (e.target.closest('#historyMoreBtn')) loadHistory(false);
    });

    // Active timer first: it decides whether "continue playing" buttons are enabled.
    await loadTimerSection(user.id);
    await loadHistory(true);
  } catch (err) {
    console.error(err);
    storage.clearToken();
    renderLogin();
  }
}

function renderNavbar(user, avatarUrl) {
  const initial = escapeHtml(user.name?.[0]?.toUpperCase() || user.username[0].toUpperCase());
  return `
    <nav class="navbar" role="navigation" aria-label="Navegación principal">
      <a href="#" class="navbar-brand" aria-label="La Viciación inicio">
        <img src="icon.svg" alt="" class="navbar-logo" aria-hidden="true" />
        La Viciación
      </a>
      <div class="navbar-actions">
        <div class="navbar-user" title="@${escapeHtml(user.username)}">
          ${avatarUrl
            ? `<img src="${avatarUrl}" alt="" class="navbar-avatar" />`
            : `<div class="navbar-avatar navbar-avatar-placeholder" aria-hidden="true">${initial}</div>`}
          <span class="navbar-username">${escapeHtml(user.name || user.username)}</span>
        </div>
        <button class="btn-logout" id="logoutBtn" aria-label="Cerrar sesión">
          ${iconLogout()} Salir
        </button>
      </div>
    </nav>
  `;
}

// ── Timer Section ───────────────────────────────────────────────
async function loadTimerSection(userId) {
  const timerSection = document.getElementById('timerSection');
  if (!timerSection) return;

  historyState.hasActive = false;
  try {
    const active = await apiFetch(`/timers/active/${userId}`);
    if (active && active.is_active && active.timer) {
      historyState.hasActive = true;
      const game = await apiFetch(`/games/${encodeURIComponent(active.timer.game_id)}`).catch(() => null);
      timerSection.innerHTML = renderActiveTimer(active.timer, game);
      document.getElementById('stopTimerBtn').addEventListener('click', (e) => {
        stopTimer(e.currentTarget.dataset.timerId, userId);
      });
      startTimerDisplay(active.timer.start_time);
      return;
    }
  } catch (err) {
    console.error('Error fetching timer:', err);
  }
  timerSection.innerHTML = renderTimerIdle();
  document.getElementById('chooseGameBtn').addEventListener('click', () => openGamePickerModal(userId));
}

function renderActiveTimer(timer, game) {
  const gameName = game?.name || timer.game_id;
  return `
    <div class="timer-active">
      <div class="timer-info">
        <div class="timer-label"><span class="live-dot"></span> Jugando ahora</div>
        <div class="timer-game">${escapeHtml(gameName)}</div>
        <div class="timer-duration" id="timerDuration">00:00:00</div>
      </div>
      <button class="btn-stop-timer" id="stopTimerBtn" data-timer-id="${timer.id}">
        ${iconStop()} Detener
      </button>
    </div>
  `;
}

function renderTimerIdle() {
  return `
    <div class="timer-idle">
      <div class="timer-idle-text">
        <div class="timer-idle-title">¿A qué toca jugar?</div>
        <div class="timer-idle-sub">Inicia un timer y registra tu sesión.</div>
      </div>
      <button class="btn-start-timer" id="chooseGameBtn">
        ${iconPlay()} Nuevo timer
      </button>
    </div>
  `;
}

// ── History (grouped by game) ───────────────────────────────────
async function loadHistory(reset) {
  const list = document.getElementById('historyList');
  if (!list) return;
  const btn = document.getElementById('historyMoreBtn');
  if (btn) { btn.disabled = true; btn.textContent = 'Cargando...'; }

  try {
    const offset = reset ? 0 : historyState.groups.length;
    const page = await apiFetch(
      `/timers/history/${historyState.userId}/grouped?limit=${HISTORY_PAGE_SIZE}&offset=${offset}`
    );
    if (!page) return;
    historyState.total = page.total_games;
    historyState.groups = reset ? page.groups : historyState.groups.concat(page.groups);
  } catch (err) {
    list.innerHTML = `<div class="empty-state"><span>⚠️</span>Error cargando el historial: ${escapeHtml(err.message)}</div>`;
    return;
  }
  renderHistory();
}

function renderHistory() {
  const list = document.getElementById('historyList');
  const more = document.getElementById('historyMore');
  if (!list) return;

  if (!historyState.groups.length) {
    list.innerHTML = `
      <div class="empty-state">
        <span>⏱️</span>
        Aún no tienes sesiones registradas. ¡Inicia tu primer timer!
      </div>`;
    more.innerHTML = '';
    return;
  }

  list.innerHTML = historyState.groups.map(renderHistoryGroup).join('');

  const remaining = historyState.total - historyState.groups.length;
  more.innerHTML = remaining > 0
    ? `<button class="btn-load-more" id="historyMoreBtn">Mostrar más (${remaining})</button>`
    : '';
}

function renderHistoryGroup(g) {
  const name = g.game_name || g.game_id;
  const multi = g.session_count > 1;
  const open = historyState.expanded.has(g.game_id);
  const canPlay = !historyState.hasActive;
  const hidden = g.session_count - g.sessions.length;

  return `
    <article class="history-group ${open ? 'open' : ''}" data-game-id="${escapeHtml(g.game_id)}">
      <div class="history-row ${multi ? 'expandable' : ''}" ${multi ? `data-action="toggle" role="button" tabindex="0" aria-expanded="${open}"` : ''}>
        ${g.image_url
          ? `<img src="${escapeHtml(g.image_url)}" alt="" class="history-thumb" loading="lazy" />`
          : '<div class="history-thumb history-thumb-placeholder" aria-hidden="true">🎮</div>'}
        <div class="history-main">
          <div class="history-title" title="${escapeHtml(name)}">${escapeHtml(name)}</div>
          <div class="history-meta">
            <span>${formatRelative(g.last_played)}</span>
            <span class="dot">·</span>
            <span>${formatDuration(g.total_seconds)}${multi ? ' en total' : ''}</span>
            ${multi ? `<span class="session-pill">${g.session_count} sesiones</span>` : ''}
            ${g.platforms.map(p => `<span class="platform-pill">${escapeHtml(platformName(p))}</span>`).join('')}
          </div>
        </div>
        <button class="btn-continue" data-action="continue" data-game-id="${escapeHtml(g.game_id)}"
                ${canPlay ? '' : 'disabled title="Ya tienes un timer activo"'} aria-label="Seguir jugando a ${escapeHtml(name)}">
          ${iconPlay()} <span>Seguir</span>
        </button>
        ${multi ? `<span class="history-chevron" aria-hidden="true">${iconChevron()}</span>` : ''}
      </div>
      ${multi && open ? `
        <ul class="history-sessions">
          ${g.sessions.map(s => `
            <li>
              <span>${formatDateTime(s.start_time)}${s.platform ? ` · ${escapeHtml(platformName(s.platform))}` : ''}</span>
              <span class="session-duration">${formatDuration(s.duration_seconds || 0)}</span>
            </li>`).join('')}
          ${hidden > 0 ? `<li class="session-more">… y ${hidden} sesiones anteriores</li>` : ''}
        </ul>` : ''}
    </article>
  `;
}

function onHistoryClick(e) {
  const cont = e.target.closest('[data-action="continue"]');
  if (cont) {
    if (!cont.disabled) {
      // Reuse the info of the most recent session (same platform).
      const g = historyState.groups.find(x => x.game_id === cont.dataset.gameId);
      startTimer(historyState.userId, g.game_id, g.platform);
    }
    return;
  }
  const row = e.target.closest('[data-action="toggle"]');
  if (row) {
    const id = row.closest('.history-group').dataset.gameId;
    if (historyState.expanded.has(id)) historyState.expanded.delete(id);
    else historyState.expanded.add(id);
    renderHistory();
  }
}

// ── Formatting ──────────────────────────────────────────────────
// The API returns naive local timestamps (datetime.now() on the server).
function parseTs(ts) {
  return new Date(ts);
}

function formatDuration(totalSeconds) {
  const s = Math.max(0, Math.round(totalSeconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (h > 0) return m ? `${h} h ${m} min` : `${h} h`;
  if (m > 0) return `${m} min`;
  return `${s} s`;
}

function formatRelative(ts) {
  const d = parseTs(ts);
  const startOfDay = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate());
  const days = Math.round((startOfDay(new Date()) - startOfDay(d)) / 86400000);
  if (days <= 0) return 'Hoy';
  if (days === 1) return 'Ayer';
  if (days < 7) return `Hace ${days} días`;
  return d.toLocaleDateString('es-ES', { day: 'numeric', month: 'short', year: d.getFullYear() === new Date().getFullYear() ? undefined : 'numeric' });
}

function formatDateTime(ts) {
  const d = parseTs(ts);
  return d.toLocaleString('es-ES', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
}

// Re-render only the timer card and the history, keeping the page in place.
async function refreshTracking(userId) {
  stopTimerDisplay();
  await loadTimerSection(userId);
  await loadHistory(true);
}

// ── Timer Actions ───────────────────────────────────────────────
async function startTimer(userId, gameId, platform = null) {
  try {
    const response = await apiFetch('/timers/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: userId,
        game_id: gameId,
        platform,
        season: new Date().getFullYear()
      })
    });

    if (response) {
      await refreshTracking(userId);
    }
  } catch (err) {
    console.error('Error starting timer:', err);
    alert('Error al iniciar el timer: ' + err.message);
  }
}

async function stopTimer(timerId, userId) {
  try {
    const response = await apiFetch(`/timers/stop/${timerId}?user_id=${userId}`, {
      method: 'POST'
    });

    if (response) {
      await refreshTracking(userId); // no full-page reload: just timer + history
    }
  } catch (err) {
    console.error('Error stopping timer:', err);
    alert('Error al detener el timer: ' + err.message);
  }
}

// ── Timer display ────────────────────────────────────────────────
let timerInterval = null;

function startTimerDisplay(startTime) {
  if (timerInterval) clearInterval(timerInterval);

  const updateTimer = () => {
    const diff = Math.max(0, Math.floor((new Date() - parseTs(startTime)) / 1000));
    const hours = Math.floor(diff / 3600);
    const minutes = Math.floor((diff % 3600) / 60);
    const seconds = diff % 60;

    const durationEl = document.getElementById('timerDuration');
    if (durationEl) {
      durationEl.textContent =
        `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
    }
  };

  updateTimer();
  timerInterval = setInterval(updateTimer, 1000);
}

function stopTimerDisplay() {
  if (timerInterval) {
    clearInterval(timerInterval);
    timerInterval = null;
  }
}

// ── Platform selection ──────────────────────────────────────────
let platformNames = {};

async function loadPlatforms() {
  try {
    const list = await apiFetch('/utils/platforms');
    platformNames = Object.fromEntries((list || []).map(p => [p.id, p.name]));
  } catch (err) {
    console.error('Error loading platforms:', err);
  }
}

function platformName(id) {
  return platformNames[id] || id;
}

// Decides how to start a timer for a game picked from the search:
// never played -> ask the platform; played before -> same platform or another one.
async function beginTimerForGame(userId, gameId, gameName) {
  let info = { has_history: false, platforms: [] };
  try {
    info = await apiFetch(`/timers/history/${userId}/platforms/${encodeURIComponent(gameId)}`) || info;
  } catch (err) {
    console.error('Error fetching game platforms:', err);
  }
  openPlatformModal(userId, gameId, gameName, info.platforms, false, info.has_history);
}

function openPlatformModal(userId, gameId, gameName, used, forceAll = false, hasHistory = used.length > 0) {
  closeModal();
  const showAll = forceAll || used.length === 0;  // no known platform to offer as "same"
  const options = Object.keys(platformNames);

  const body = showAll
    ? `<div class="modal-hint">${forceAll ? 'Elige la nueva plataforma' : hasHistory ? 'Ya has jugado a este juego, pero no consta la plataforma. ¿En cuál juegas?' : 'Este juego es nuevo para ti. ¿En qué plataforma juegas?'}</div>
       <div class="modal-results-list">
         ${options.map(id => `
           <button class="modal-result-row" data-platform="${escapeHtml(id)}">
             <span class="modal-result-name">${escapeHtml(platformName(id))}${used.includes(id) ? ' <span class="modal-result-badge">Ya usada</span>' : ''}</span>
           </button>`).join('') || '<div class="modal-hint">No hay plataformas disponibles</div>'}
       </div>`
    : `<div class="modal-hint">Ya has jugado a este juego. ¿En qué plataforma?</div>
       <div class="modal-results-list">
         ${used.map((id, i) => `
           <button class="modal-result-row" data-platform="${escapeHtml(id)}">
             <span class="modal-result-name">${escapeHtml(platformName(id))}${i === 0 ? ' <span class="modal-result-badge">Misma que la última vez</span>' : ''}</span>
           </button>`).join('')}
       </div>
       <div class="modal-footer">
         <button class="btn-modal-secondary" id="otherPlatformBtn">${iconPlus()} Otra plataforma</button>
       </div>`;

  document.body.insertAdjacentHTML('beforeend', `
    <div class="modal-overlay" id="gvModal">
      <div class="modal-content">
        <div class="modal-header">
          <h3>${escapeHtml(gameName || 'Plataforma')}</h3>
          <button class="modal-close" id="modalCloseBtn" aria-label="Cerrar">&times;</button>
        </div>
        ${body}
      </div>
    </div>
  `);

  document.getElementById('modalCloseBtn').addEventListener('click', closeModal);
  document.getElementById('gvModal').addEventListener('click', (e) => {
    if (e.target.id === 'gvModal') closeModal();
  });
  document.querySelectorAll('#gvModal [data-platform]').forEach(btn => {
    btn.addEventListener('click', () => {
      closeModal();
      startTimer(userId, gameId, btn.dataset.platform);
    });
  });
  const other = document.getElementById('otherPlatformBtn');
  if (other) other.addEventListener('click', () => openPlatformModal(userId, gameId, gameName, used, true, hasHistory));
}

// ── Game picker / add-game modals ─────────────────────────────
let modalSearchTimeout = null;

function closeModal() {
  const modal = document.getElementById('gvModal');
  if (modal) modal.remove();
  clearTimeout(modalSearchTimeout);
}

function openGamePickerModal(userId) {
  closeModal();
  document.body.insertAdjacentHTML('beforeend', `
    <div class="modal-overlay" id="gvModal">
      <div class="modal-content">
        <div class="modal-header">
          <h3>Elegir juego</h3>
          <button class="modal-close" id="modalCloseBtn" aria-label="Cerrar">&times;</button>
        </div>
        <input type="text" id="gamePickerSearch" class="modal-search-input" placeholder="Buscar en tu catálogo..." autocomplete="off" />
        <div class="modal-results-list" id="gamePickerResults">
          <div class="modal-hint">Escribe para buscar un juego</div>
        </div>
        <div class="modal-footer">
          <button class="btn-modal-secondary" id="modalAddGameBtn">${iconPlus()} ¿No está? Añadir nuevo juego</button>
        </div>
      </div>
    </div>
  `);

  document.getElementById('modalCloseBtn').addEventListener('click', closeModal);
  document.getElementById('gvModal').addEventListener('click', (e) => {
    if (e.target.id === 'gvModal') closeModal();
  });
  document.getElementById('modalAddGameBtn').addEventListener('click', () => {
    openAddGameModal(userId);
  });

  const searchInput = document.getElementById('gamePickerSearch');
  searchInput.addEventListener('input', () => {
    clearTimeout(modalSearchTimeout);
    const query = searchInput.value.trim();
    modalSearchTimeout = setTimeout(() => searchGamesForPicker(query, userId), 250);
  });
  searchInput.focus();
}

async function searchGamesForPicker(query, userId) {
  const resultsEl = document.getElementById('gamePickerResults');
  if (!resultsEl) return;
  if (query.length < 2) {
    resultsEl.innerHTML = '<div class="modal-hint">Escribe al menos 2 caracteres</div>';
    return;
  }
  resultsEl.innerHTML = '<div class="modal-hint">Buscando...</div>';
  try {
    const results = await apiFetch(`/games/?name=${encodeURIComponent(query)}`);
    if (!resultsEl.isConnected) return; // modal closed while awaiting
    if (!results || !results.length) {
      resultsEl.innerHTML = '<div class="modal-hint">Sin resultados en tu catálogo</div>';
      return;
    }
    resultsEl.innerHTML = results.map(g => `
      <button class="modal-result-row" data-game-id="${g.id}">
        ${g.image_url
          ? `<img src="${g.image_url}" alt="" class="modal-result-thumb" />`
          : '<div class="modal-result-thumb-placeholder">🎮</div>'}
        <span class="modal-result-name">${escapeHtml(g.name)}</span>
      </button>
    `).join('');
    resultsEl.querySelectorAll('.modal-result-row').forEach(btn => {
      btn.addEventListener('click', () => {
        const game = results.find(g => String(g.id) === btn.dataset.gameId);
        closeModal();
        beginTimerForGame(userId, btn.dataset.gameId, game?.name);
      });
    });
  } catch (err) {
    if (resultsEl.isConnected) {
      resultsEl.innerHTML = `<div class="modal-hint">Error buscando: ${escapeHtml(err.message)}</div>`;
    }
  }
}

function openAddGameModal(userId) {
  closeModal();
  document.body.insertAdjacentHTML('beforeend', `
    <div class="modal-overlay" id="gvModal">
      <div class="modal-content">
        <div class="modal-header">
          <h3>Añadir juego nuevo</h3>
          <button class="modal-close" id="modalCloseBtn" aria-label="Cerrar">&times;</button>
        </div>
        <input type="text" id="addGameSearch" class="modal-search-input" placeholder="Buscar en RAWG..." autocomplete="off" />
        <div class="modal-results-list" id="addGameResults">
          <div class="modal-hint">Escribe el nombre del juego</div>
        </div>
      </div>
    </div>
  `);

  document.getElementById('modalCloseBtn').addEventListener('click', closeModal);
  document.getElementById('gvModal').addEventListener('click', (e) => {
    if (e.target.id === 'gvModal') closeModal();
  });

  const searchInput = document.getElementById('addGameSearch');
  searchInput.addEventListener('input', () => {
    clearTimeout(modalSearchTimeout);
    const query = searchInput.value.trim();
    modalSearchTimeout = setTimeout(() => searchRawgForAddGame(query, userId), 300);
  });
  searchInput.focus();
}

async function searchRawgForAddGame(query, userId) {
  const resultsEl = document.getElementById('addGameResults');
  if (!resultsEl) return;
  if (query.length < 2) {
    resultsEl.innerHTML = '<div class="modal-hint">Escribe al menos 2 caracteres</div>';
    return;
  }
  resultsEl.innerHTML = '<div class="modal-hint">Buscando en RAWG...</div>';
  try {
    const candidates = await apiFetch(`/games/search-rawg?query=${encodeURIComponent(query)}`);
    if (!resultsEl.isConnected) return; // modal closed while awaiting
    if (!candidates || !candidates.length) {
      resultsEl.innerHTML = '<div class="modal-hint">Sin resultados</div>';
      return;
    }
    resultsEl.innerHTML = candidates.map((c, i) => `
      <button class="modal-result-row" data-index="${i}">
        ${c.image_url
          ? `<img src="${c.image_url}" alt="" class="modal-result-thumb" />`
          : '<div class="modal-result-thumb-placeholder">🎮</div>'}
        <span class="modal-result-name">
          ${escapeHtml(c.name)}${c.released ? ` <span class="modal-result-year">(${escapeHtml(c.released.slice(0, 4))})</span>` : ''}
          ${c.exists_in_db ? '<span class="modal-result-badge">Ya en tu catálogo</span>' : ''}
        </span>
      </button>
    `).join('');
    resultsEl.querySelectorAll('.modal-result-row').forEach(btn => {
      btn.addEventListener('click', () => {
        handlePickRawgCandidate(candidates[Number(btn.dataset.index)], userId);
      });
    });
  } catch (err) {
    if (resultsEl.isConnected) {
      resultsEl.innerHTML = `<div class="modal-hint">Error buscando: ${escapeHtml(err.message)}</div>`;
    }
  }
}

async function handlePickRawgCandidate(candidate, userId) {
  const resultsEl = document.getElementById('addGameResults');
  try {
    if (candidate.exists_in_db && candidate.db_game_id) {
      closeModal();
      await beginTimerForGame(userId, candidate.db_game_id, candidate.name);
      return;
    }
    if (resultsEl) resultsEl.innerHTML = '<div class="modal-hint">Añadiendo juego...</div>';
    const newGame = await apiFetch('/games/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: candidate.name,
        rawg_id: candidate.rawg_id,
        release_date: candidate.released || null,
        image_url: candidate.image_url || null,
        genres: (candidate.genres || []).join(','),
        slug: candidate.slug || null,
      }),
    });
    closeModal();
    // Brand-new game: it can't have any history, go straight to platform choice.
    openPlatformModal(userId, newGame.id, newGame.name, []);
  } catch (err) {
    if (resultsEl && resultsEl.isConnected) {
      resultsEl.innerHTML = `<div class="modal-hint">Error: ${escapeHtml(err.message)}</div>`;
    }
  }
}

// ── Logout ───────────────────────────────────────────────────
function handleLogout() {
  stopTimerDisplay(); // Stop timer display
  storage.clearToken();
  renderLogin();
}

// ── Icons (inline SVG) ───────────────────────────────────────
function iconUser() {
  return `<svg class="input-icon" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>`;
}
function iconLock() {
  return `<svg class="input-icon" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>`;
}
function iconEye() {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>`;
}
function iconEyeOff() {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>`;
}
function iconLogout() {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>`;
}
function iconPlay() {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>`;
}
function iconStop() {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="6" width="12" height="12"/></svg>`;
}
function iconChevron() {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>`;
}
function iconPlus() {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>`;
}

// ── Utils ────────────────────────────────────────────────────
function escapeHtml(str) {
  const d = document.createElement('div');
  d.textContent = str;
  return d.innerHTML;
}

// ── Service Worker ───────────────────────────────────────────
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(console.warn);
  });
}

// ── Boot ─────────────────────────────────────────────────────
(async () => {
  if (storage.getToken()) {
    await renderHome();
  } else {
    renderLogin();
  }
})();
