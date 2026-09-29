// ============================================================
//  La Viciación — Profile page (lazy-loaded from app.js)
//  Stats, in-progress games (mark as completed), personal data and
//  password change. All routes are /api/v1/users/{username}/...
// ============================================================

let api, esc, root, user, avatarUrl;

const PASSWORD_RE = [/^.{12,24}$/, /[A-Z]/, /[a-z]/, /\d/, /[!@#$%^&*()_+{}[\]:;<>,.?/~\\-]/];
const PASSWORD_HINT = '12-24 caracteres, con mayúscula, minúscula, número y un carácter especial.';

const fmtDur = (sec) => {
  const s = Math.max(0, Math.round(sec || 0));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (h > 0) return m ? `${h} h ${m} min` : `${h} h`;
  if (m > 0) return `${m} min`;
  return `${s} s`;
};
const fmtDate = (d) => (d ? new Date(d).toLocaleDateString('es-ES', { day: 'numeric', month: 'short', year: 'numeric' }) : '—');
const jsonReq = (method, body) => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
});

function flash(el, msg, ok = false) {
  el.textContent = msg;
  el.className = `pf-msg ${msg ? (ok ? 'ok' : 'err') : ''}`;
}

export async function initProfile(rootEl, ctx) {
  ({ apiFetch: api, escapeHtml: esc } = ctx);
  root = rootEl;
  user = ctx.me;
  const blob = await api(`/users/${encodeURIComponent(user.username)}/avatar`).catch(() => null);
  avatarUrl = blob instanceof Blob && blob.size ? URL.createObjectURL(blob) : null;
  await load();
}

// Center-crop to a square and shrink, so the stored avatar stays small.
function resizeImage(file, size = 256) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    const src = URL.createObjectURL(file);
    img.onload = () => {
      const side = Math.min(img.width, img.height);
      const canvas = document.createElement('canvas');
      canvas.width = canvas.height = size;
      canvas.getContext('2d').drawImage(img, (img.width - side) / 2, (img.height - side) / 2, side, side, 0, 0, size, size);
      URL.revokeObjectURL(src);
      canvas.toBlob((b) => (b ? resolve(b) : reject(new Error('No se pudo procesar la imagen'))), 'image/jpeg', 0.9);
    };
    img.onerror = () => { URL.revokeObjectURL(src); reject(new Error('El archivo no es una imagen válida')); };
    img.src = src;
  });
}

function avatarHtml(d) {
  const initial = esc((d.user.name || d.user.username)[0].toUpperCase());
  return avatarUrl
    ? `<img src="${avatarUrl}" alt="" class="pf-avatar" id="pfAvatar" />`
    : `<div class="pf-avatar pf-avatar-placeholder" id="pfAvatar" aria-hidden="true">${initial}</div>`;
}

async function changeAvatar(e) {
  const file = e.target.files[0];
  e.target.value = '';
  if (!file) return;
  const msg = root.querySelector('#pfAvatarMsg');
  if (!['image/jpeg', 'image/png'].includes(file.type)) return flash(msg, 'Solo se admiten imágenes JPG o PNG');
  flash(msg, 'Subiendo…', true);
  try {
    const small = await resizeImage(file);
    const form = new FormData();
    form.append('file', small, 'avatar.jpg');
    await api(`/users/${encodeURIComponent(user.username)}/avatar`, { method: 'PATCH', body: form });
    avatarUrl = URL.createObjectURL(small);
    for (const el of [root.querySelector('#pfAvatar'), document.querySelector('.navbar-avatar')]) {
      if (!el) continue;
      const img = document.createElement('img');
      img.src = avatarUrl;
      img.alt = '';
      img.className = el.className.replace('navbar-avatar-placeholder', '').replace('pf-avatar-placeholder', '').trim();
      if (el.id) img.id = el.id;
      el.replaceWith(img);
    }
    flash(msg, 'Foto actualizada', true);
  } catch (err) {
    flash(msg, err.message);
  }
}

async function load() {
  const data = await api(`/users/${encodeURIComponent(user.username)}/profile`);
  if (!data) return;
  render(data);
}

function statTile(label, value) {
  return `<div class="pf-stat"><div class="pf-stat-value">${esc(value)}</div><div class="pf-stat-label">${esc(label)}</div></div>`;
}

function render(d) {
  const s = d.stats;
  const maxTop = Math.max(1, ...d.top_games.map((g) => g.played_time));
  root.innerHTML = `
    <div class="pf-head">
      ${avatarHtml(d)}
      <div class="pf-head-text">
        <h1 class="pf-title">${esc(d.user.name || d.user.username)}</h1>
        <div class="pf-sub">@${esc(d.user.username)} · Temporada ${esc(d.season)}</div>
        <div class="pf-avatar-actions">
          <label class="pf-btn">Cambiar foto<input type="file" id="pfAvatarInput" accept="image/png,image/jpeg" hidden /></label>
          <span class="pf-msg" id="pfAvatarMsg" role="status"></span>
        </div>
      </div>
    </div>

    <section class="pf-stats" aria-label="Estadísticas">
      ${statTile('Tiempo jugado', fmtDur(s.played_time))}
      ${statTile('Días jugados', s.played_days)}
      ${statTile('Juegos jugados', s.played_games)}
      ${statTile('Completados', s.completed_games)}
      ${statTile('Racha actual', `${s.current_streak} d`)}
      ${statTile('Mejor racha', `${s.best_streak} d`)}
      ${statTile('Logros', s.achievements)}
    </section>

    <div class="section-header"><h2 class="section-title">En curso</h2><div class="section-line"></div></div>
    <div class="pf-card" id="pfProgress">
      ${d.in_progress.length ? d.in_progress.map((g) => `
        <div class="pf-row" data-game="${esc(g.game_id)}">
          <div class="pf-row-main">
            <strong>${esc(g.game_name)}</strong>
            <div class="pf-sub">${esc(g.platform_name || 'Sin plataforma')} · ${fmtDur(g.played_time)} · desde ${fmtDate(g.started_date)}</div>
          </div>
          <button class="pf-btn primary" data-complete="${esc(g.game_id)}" data-name="${esc(g.game_name)}">Marcar completado</button>
        </div>`).join('') : '<div class="pf-empty">No tienes juegos en curso esta temporada.</div>'}
      <div class="pf-msg" id="pfProgressMsg" role="status"></div>
    </div>

    <div class="pf-cols">
      <div>
        <div class="section-header"><h2 class="section-title">Más jugados</h2><div class="section-line"></div></div>
        <div class="pf-card">
          ${d.top_games.length ? d.top_games.map((g) => `
            <div class="pf-bar-row">
              <div class="pf-bar-label"><span>${esc(g.game_name)}</span><span>${fmtDur(g.played_time)}</span></div>
              <div class="pf-bar"><div style="width:${Math.max(3, Math.round((g.played_time / maxTop) * 100))}%"></div></div>
            </div>`).join('') : '<div class="pf-empty">Aún no hay tiempo registrado.</div>'}
        </div>
      </div>
      <div>
        <div class="section-header"><h2 class="section-title">Últimos logros</h2><div class="section-line"></div></div>
        <div class="pf-card">
          ${d.achievements.length ? d.achievements.map((a) => `
            <div class="pf-row"><div class="pf-row-main"><strong>${esc(a.title)}</strong></div><div class="pf-sub">${fmtDate(a.date)}</div></div>`).join('') : '<div class="pf-empty">Todavía no has conseguido logros.</div>'}
        </div>
      </div>
    </div>

    <div class="section-header"><h2 class="section-title">Mis datos</h2><div class="section-line"></div></div>
    <form class="pf-card pf-form" id="pfData" novalidate>
      <label>Usuario<input class="adm-input" type="text" value="${esc(d.user.username)}" disabled /></label>
      <label>Nombre<input class="adm-input" type="text" name="name" value="${esc(d.user.name || '')}" autocomplete="name" /></label>
      <label>Email<input class="adm-input" type="email" name="email" value="${esc(d.user.email || '')}" autocomplete="email" /></label>
      <label>Telegram ID<input class="adm-input" type="number" name="telegram_id" value="${esc(d.user.telegram_id ?? '')}" /></label>
      <div class="pf-msg" id="pfDataMsg" role="status"></div>
      <div><button class="pf-btn primary" type="submit">Guardar datos</button></div>
    </form>

    <div class="section-header"><h2 class="section-title">Cambiar contraseña</h2><div class="section-line"></div></div>
    <form class="pf-card pf-form" id="pfPass" novalidate>
      <label>Contraseña actual<input class="adm-input" type="password" name="current" autocomplete="current-password" /></label>
      <label>Nueva contraseña<input class="adm-input" type="password" name="next" autocomplete="new-password" /></label>
      <label>Repite la nueva contraseña<input class="adm-input" type="password" name="again" autocomplete="new-password" /></label>
      <div class="pf-sub">${PASSWORD_HINT}</div>
      <div class="pf-msg" id="pfPassMsg" role="status"></div>
      <div><button class="pf-btn primary" type="submit">Cambiar contraseña</button></div>
    </form>
  `;
  bind();
}

function bind() {
  root.querySelector('#pfAvatarInput').addEventListener('change', changeAvatar);
  root.querySelector('#pfProgress').addEventListener('click', onComplete);
  root.querySelector('#pfData').addEventListener('submit', saveData);
  root.querySelector('#pfPass').addEventListener('submit', changePassword);
}

// Two-step button: first click asks, second click within 4s confirms.
async function onComplete(e) {
  const btn = e.target.closest('[data-complete]');
  if (!btn) return;
  const msg = root.querySelector('#pfProgressMsg');
  if (!btn.dataset.armed) {
    btn.dataset.armed = '1';
    btn.textContent = '¿Seguro? Pulsa otra vez';
    setTimeout(() => {
      if (btn.isConnected && btn.dataset.armed) {
        delete btn.dataset.armed;
        btn.textContent = 'Marcar completado';
      }
    }, 4000);
    return;
  }
  btn.disabled = true;
  btn.textContent = 'Completando…';
  flash(msg, '');
  try {
    await api(`/users/${encodeURIComponent(user.username)}/complete-game?game_id=${encodeURIComponent(btn.dataset.complete)}`, { method: 'PATCH' });
    await load();
    flash(root.querySelector('#pfProgressMsg'), `«${btn.dataset.name}» marcado como completado`, true);
  } catch (err) {
    btn.disabled = false;
    delete btn.dataset.armed;
    btn.textContent = 'Marcar completado';
    flash(msg, err.message);
  }
}

async function saveData(e) {
  e.preventDefault();
  const f = e.currentTarget;
  const msg = root.querySelector('#pfDataMsg');
  const tg = f.telegram_id.value.trim();
  try {
    const updated = await api(`/users/${encodeURIComponent(user.username)}/profile`, jsonReq('PATCH', {
      name: f.name.value,
      email: f.email.value,
      telegram_id: tg === '' ? null : Number(tg),
    }));
    user.name = updated.name;
    user.email = updated.email;
    user.telegram_id = updated.telegram_id;
    const title = root.querySelector('.pf-title');
    if (title) title.textContent = updated.name || updated.username;
    const nav = document.querySelector('.navbar-username');
    if (nav) nav.textContent = updated.name || updated.username;
    flash(msg, 'Datos guardados', true);
  } catch (err) {
    flash(msg, err.message);
  }
}

async function changePassword(e) {
  e.preventDefault();
  const f = e.currentTarget;
  const msg = root.querySelector('#pfPassMsg');
  if (!f.current.value) return flash(msg, 'Introduce tu contraseña actual');
  if (!PASSWORD_RE.every((re) => re.test(f.next.value))) return flash(msg, `La contraseña debe tener ${PASSWORD_HINT.toLowerCase()}`);
  if (f.next.value !== f.again.value) return flash(msg, 'Las contraseñas nuevas no coinciden');
  try {
    await api(`/users/${encodeURIComponent(user.username)}/password`, jsonReq('POST', {
      current_password: f.current.value,
      new_password: f.next.value,
    }));
    f.reset();
    flash(msg, 'Contraseña actualizada', true);
  } catch (err) {
    flash(msg, err.message);
  }
}
