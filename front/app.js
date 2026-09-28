// ============================================================
//  La Viciación — PWA App
//  API: FastAPI + JWT (OAuth2PasswordRequestForm)
//  Routes used:
//    POST /api/v1/token          → login
//    GET  /api/v1/auth/active_user → get user info
//    GET  /api/v1/users/{username}/games → user games
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

// ── Home page ────────────────────────────────────────────────
async function renderHome() {
  // Skeleton placeholder while loading
  renderPage(`
    <div id="loading-overlay">
      <div class="spinner"></div>
    </div>
  `);

  try {
    const user = await apiFetch('/auth/active_user');
    if (!user) return;

    // Fetch games (non-blocking)
    const [games, avatarBlob] = await Promise.allSettled([
      apiFetch(`/users/${user.username}/games`),
      apiFetch(`/users/${user.username}/avatar`),
    ]);

    const avatarUrl = avatarBlob.status === 'fulfilled' && avatarBlob.value instanceof Blob
      ? URL.createObjectURL(avatarBlob.value)
      : null;

    const gamesData = games.status === 'fulfilled' ? (games.value || []) : [];
    const completedCount = gamesData.filter(g => g.completed).length;

    renderPage(`
      <div class="home-page">
        ${renderNavbar(user)}

        <main class="home-main">
          <!-- Profile Hero -->
          <section class="profile-hero" aria-label="Perfil del usuario">
            <div class="profile-avatar-wrap">
              ${avatarUrl
                ? `<img src="${avatarUrl}" alt="Avatar de ${user.username}" class="profile-avatar" />`
                : `<div class="profile-avatar-placeholder" aria-hidden="true">${user.name?.[0]?.toUpperCase() || '?'}</div>`
              }
              ${user.is_active ? '<div class="online-dot" title="Activo"></div>' : ''}
            </div>

            <div class="profile-info">
              <h1 class="profile-name">${escapeHtml(user.name || user.username)}</h1>
              <div class="profile-username">@${escapeHtml(user.username)}</div>
              <div class="profile-badges">
                ${user.is_admin ? '<span class="badge badge-admin">⚡ Admin</span>' : ''}
                <span class="badge ${user.is_active ? 'badge-active' : 'badge-inactive'}">
                  ${user.is_active ? '✓ Activo' : '✗ Inactivo'}
                </span>
              </div>
            </div>

            <div class="profile-stats">
              <div class="stat-value">${gamesData.length}</div>
              <div class="stat-label">Juegos</div>
              <div class="stat-value" style="margin-top:12px">${completedCount}</div>
              <div class="stat-label">Completados</div>
            </div>
          </section>

          <!-- Info Cards -->
          <div class="section-header">
            <h2 class="section-title">Información</h2>
            <div class="section-line"></div>
          </div>
          <div class="info-grid" style="margin-bottom:40px">
            ${infoCard('📧', 'teal', 'Correo electrónico', escapeHtml(user.email || '—'), false)}
            ${user.telegram_id ? infoCard('✈️', 'gold', 'Telegram ID', escapeHtml(String(user.telegram_id)), true) : ''}
            ${user.clockify_id ? infoCard('⏱️', 'purple', 'Clockify ID', escapeHtml(user.clockify_id), true) : ''}
            ${infoCard('🆔', 'pink', 'ID de usuario', String(user.id), true)}
          </div>

          <!-- Timer Section -->
          <div class="section-header">
            <h2 class="section-title">Timer de Juego</h2>
            <div class="section-line"></div>
          </div>
          <div id="timerSection">
            <div class="loading-spinner">Cargando timer...</div>
          </div>

          <!-- Games -->
          <div class="section-header">
            <h2 class="section-title">Mis juegos</h2>
            <div class="section-line"></div>
          </div>
          <div class="games-grid" id="gamesGrid">
            ${renderGames(gamesData)}
          </div>
        </main>
      </div>
    `);

    // Bind logout
    document.getElementById('logoutBtn').addEventListener('click', handleLogout);
    
    // Load timer section asynchronously
    loadTimerSection(user.id, gamesData);

  } catch (err) {
    console.error(err);
    storage.clearToken();
    renderLogin();
  }
}

function renderNavbar(user) {
  return `
    <nav class="navbar" role="navigation" aria-label="Navegación principal">
      <a href="#" class="navbar-brand" aria-label="La Viciación inicio">
        <img src="icon.svg" alt="" class="navbar-logo" aria-hidden="true" />
        La Viciación
      </a>
      <div class="navbar-actions">
        <button class="btn-logout" id="logoutBtn" aria-label="Cerrar sesión">
          ${iconLogout()} Salir
        </button>
      </div>
    </nav>
  `;
}

function renderGames(games) {
  if (!games.length) {
    return `
      <div class="empty-state">
        <span>🎮</span>
        No tienes juegos registrados todavía.
      </div>
    `;
  }

  return games.map((g, i) => `
    <article class="game-card" style="animation-delay: ${i * 0.05}s">
      <div class="game-cover-placeholder" aria-hidden="true">🎮</div>
      <div class="game-info">
        <div class="game-title" title="${escapeHtml(g.game?.name || g.game_id)}">${escapeHtml(g.game?.name || g.game_id)}</div>
        <div class="game-meta">
          <span class="game-tag ${g.completed ? 'completed' : 'playing'}">
            ${g.completed ? '✓ Completado' : '▶ Jugando'}
          </span>
        </div>
        ${g.score != null ? `<div class="game-score">⭐ ${g.score.toFixed(1)}</div>` : ''}
      </div>
    </article>
  `).join('');
}

// ── Timer Section ───────────────────────────────────────────────
async function loadTimerSection(userId, games) {
  const timerSection = document.getElementById('timerSection');
  if (!timerSection) return;
  
  try {
    const activeTimer = await apiFetch(`/timers/active/${userId}`);
    
    if (activeTimer && activeTimer.is_active && activeTimer.timer) {
      timerSection.innerHTML = renderActiveTimer(activeTimer.timer, games);
      bindTimerEvents(userId, games);
      
      // Start timer display
      startTimerDisplay(activeTimer.timer.start_time);
    } else {
      timerSection.innerHTML = renderTimerSelector(userId, games);
      bindTimerEvents(userId, games);
    }
  } catch (err) {
    console.error('Error fetching timer:', err);
    timerSection.innerHTML = renderTimerSelector(userId, games);
    bindTimerEvents(userId, games);
  }
}

function renderActiveTimer(timer, games) {
  const game = games.find(g => g.game_id === timer.game_id);
  const gameName = game?.game?.name || timer.game_id;
  
  return `
    <div class="timer-active" data-timer='${JSON.stringify(timer)}'>
      <div class="timer-info">
        <div class="timer-label">Jugando ahora:</div>
        <div class="timer-game">${escapeHtml(gameName)}</div>
        <div class="timer-duration" id="timerDuration">00:00:00</div>
      </div>
      <button class="btn-stop-timer" id="stopTimerBtn" data-timer-id="${timer.id}">
        ${iconStop()} Detener
      </button>
    </div>
  `;
}

function renderActiveTimer(timer, games) {
  const game = games.find(g => g.game_id === timer.game_id);
  const gameName = game?.game?.name || timer.game_id;
  
  return `
    <div class="timer-active">
      <div class="timer-info">
        <div class="timer-label">Jugando ahora:</div>
        <div class="timer-game">${escapeHtml(gameName)}</div>
        <div class="timer-duration" id="timerDuration">00:00:00</div>
      </div>
      <button class="btn-stop-timer" id="stopTimerBtn" data-timer-id="${timer.id}">
        ${iconStop()} Detener
      </button>
    </div>
  `;
}

function renderTimerSelector(userId, games) {
  const recentGames = games.slice(0, 5); // Last 5 games
  
  return `
    <div class="timer-selector">
      <div class="timer-label">Iniciar sesión de juego:</div>
      
      <div class="game-selector">
        <select id="gameSelect" class="game-select">
          <option value="">Selecciona un juego...</option>
          ${recentGames.map(g => `
            <option value="${g.game_id}">
              ${escapeHtml(g.game?.name || g.game_id)}
            </option>
          `).join('')}
        </select>
        <button class="btn-add-game" id="addGameBtn" title="Añadir nuevo juego">
          ${iconPlus()}
        </button>
      </div>
      
      <div class="timer-actions">
        <button class="btn-start-timer" id="startTimerBtn" data-user-id="${userId}">
          ${iconPlay()} Iniciar Timer
        </button>
      </div>
      
      <div class="recent-games">
        <div class="recent-label">Juegos recientes:</div>
        <div class="recent-list">
          ${recentGames.map(g => `
            <button class="recent-game-btn" data-game-id="${g.game_id}" data-user-id="${userId}">
              ${escapeHtml(g.game?.name || g.game_id)}
            </button>
          `).join('')}
        </div>
      </div>
    </div>
  `;
}

// ── Timer Actions ───────────────────────────────────────────────
async function startTimer(userId, gameId) {
  try {
    const response = await apiFetch('/timers/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: userId,
        game_id: gameId,
        platform: 'Unknown',
        season: new Date().getFullYear()
      })
    });
    
    if (response) {
      await renderHome(); // Refresh to show active timer
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
      await renderHome(); // Refresh to show timer selector
    }
  } catch (err) {
    console.error('Error stopping timer:', err);
    alert('Error al detener el timer: ' + err.message);
  }
}

// ── Timer Timer Update ───────────────────────────────────────────
let timerInterval = null;

function startTimerDisplay(startTime) {
  if (timerInterval) clearInterval(timerInterval);
  
  const updateTimer = () => {
    const now = new Date();
    const diff = Math.floor((now - new Date(startTime)) / 1000);
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

function bindTimerEvents(userId, games) {
  // Start timer button
  const startBtn = document.getElementById('startTimerBtn');
  if (startBtn) {
    startBtn.addEventListener('click', () => {
      const gameSelect = document.getElementById('gameSelect');
      const gameId = gameSelect.value;
      if (gameId) {
        startTimer(userId, gameId);
      } else {
        alert('Por favor selecciona un juego');
      }
    });
  }
  
  // Stop timer button
  const stopBtn = document.getElementById('stopTimerBtn');
  if (stopBtn) {
    stopBtn.addEventListener('click', () => {
      const timerId = stopBtn.dataset.timerId;
      stopTimer(timerId, userId);
    });
  }
  
  // Recent game buttons
  const recentBtns = document.querySelectorAll('.recent-game-btn');
  recentBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const gameId = btn.dataset.gameId;
      startTimer(userId, gameId);
    });
  });
  
  // Add game button (placeholder for now)
  const addGameBtn = document.getElementById('addGameBtn');
  if (addGameBtn) {
    addGameBtn.addEventListener('click', () => {
      alert('Funcionalidad para añadir nuevo juego próximamente');
    });
  }
  
  // Check if there's an active timer and start the display
  const activeTimerEl = document.querySelector('.timer-active');
  if (activeTimerEl) {
    const timerInfo = activeTimerEl.querySelector('.timer-duration');
    if (timerInfo) {
      // Get the start time from the timer data
      const timerData = JSON.parse(activeTimerEl.dataset.timer || '{}');
      if (timerData.start_time) {
        startTimerDisplay(timerData.start_time);
      }
    }
  }
}

function infoCard(icon, colorClass, label, value, mono = false) {
  return `
    <div class="info-card">
      <div class="info-card-icon ${colorClass}">${icon}</div>
      <div class="info-card-label">${label}</div>
      <div class="info-card-value ${mono ? 'mono' : ''}">${value}</div>
    </div>
  `;
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
