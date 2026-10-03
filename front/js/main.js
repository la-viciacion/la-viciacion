// Entry point: hash router + session handling.
//
// A page module exports:
//   active      navbar item to highlight ('home' | 'group' | 'profile' | 'admin')
//   mainClass   optional class for <main>
//   adminOnly   optional; non-admins are sent home
//   render({ user, main, avatarUrl, isCurrent, onLogout })   fills <main>; isCurrent() turns false
//                                       once the user navigated elsewhere; onLogout ends the session
//   dispose()   optional cleanup when leaving the page
import { api, loadAvatarUrl, session, setUnauthorizedHandler } from './lib/api.js';
import { RESET_ROUTE, isResetRoute, resetTokenFromHash } from './lib/recovery.js';
import * as home from './pages/home/index.js';
import { showLogin } from './pages/auth/login.js';
import { showForgotPassword, showResetPassword } from './pages/auth/recover.js';
import { stopPresence } from './lib/presence.js';
import { renderShell, showLoading } from './ui/layout.js';
import { closeMenu } from './ui/menu.js';
import { openPlayingSheet } from './ui/playing.js';
import { inviteToPush } from './ui/push-invite.js';

const ROUTES = [
  { prefix: '#/admin', load: () => import('./pages/admin/index.js') },
  { prefix: '#/profile', load: () => import('./pages/profile/index.js') },
  { prefix: '#/game/', load: () => import('./pages/game/index.js') },
  { prefix: '#/group', load: () => import('./pages/group/index.js') },
  { prefix: '#/stats', load: () => import('./pages/stats/index.js') },
  { prefix: '#/games', load: () => import('./pages/games/index.js') },
];

let navigation = 0; // only the most recent navigation may touch the DOM
let currentPage = null;

const loadPage = (hash) => ROUTES.find((r) => hash.startsWith(r.prefix))?.load() ?? Promise.resolve(home);

function leaveCurrentPage() {
  closeMenu();
  currentPage?.dispose?.();
  currentPage = null;
}

function logout() {
  session.clear();
  stopPresence();
  leaveCurrentPage();
  showLogin(route);
}

// The link of the recovery email works with or without a session. The token is read once and taken
// out of the address bar, so it does not stay in the history.
function showRecovery() {
  const token = resetTokenFromHash(location.hash);
  history.replaceState(null, '', location.pathname + RESET_ROUTE);
  const leave = () => {
    history.replaceState(null, '', location.pathname);
    route();
  };
  showResetPassword(token, leave, () => showForgotPassword(leave));
}

async function route() {
  const id = ++navigation;
  const isCurrent = () => id === navigation;
  leaveCurrentPage();

  if (isResetRoute(location.hash)) return showRecovery();

  if (!session.getToken()) return showLogin(route);
  showLoading();

  try {
    const page = await loadPage(location.hash);
    const user = await api('/auth/active_user');
    if (!user || !isCurrent()) return;

    if (page.adminOnly && !user.is_admin) {
      // The API enforces this too; this is just UX. replaceState => no hashchange.
      history.replaceState(null, '', location.pathname);
      return route();
    }

    const avatarUrl = await loadAvatarUrl(user.username);
    if (!isCurrent()) return;

    const main = renderShell({ user, avatarUrl, active: page.active, mainClass: page.mainClass, onLogout: logout });
    currentPage = page;
    await page.render({ user, main, avatarUrl, isCurrent, onLogout: logout });
    if (location.hash === '#/playing' && isCurrent()) {
      // the shortcut of the installed app: the home page with the sheet open
      history.replaceState(null, '', location.pathname);
      openPlayingSheet(user.id);
    }
    inviteToPush().catch(() => {}); // optional: never blocks or breaks a page
  } catch (err) {
    console.error(err);
    if (!isCurrent()) return;
    session.clear();
    showLogin(route);
  }
}

setUnauthorizedHandler(() => {
  stopPresence();
  leaveCurrentPage();
  showLogin(route);
});

window.addEventListener('hashchange', () => {
  if (session.getToken() || isResetRoute(location.hash)) route();
});

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => navigator.serviceWorker.register('/sw.js').catch(console.warn));
}

route();
