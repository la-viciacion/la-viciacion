// Entry point: hash router + session handling.
//
// A page module exports:
//   active      navbar item to highlight ('home' | 'profile' | 'admin')
//   mainClass   optional class for <main>
//   adminOnly   optional; non-admins are sent home
//   render({ user, main, isCurrent, onLogout })   fills <main>; isCurrent() turns false
//                                       once the user navigated elsewhere; onLogout ends the session
//   dispose()   optional cleanup when leaving the page
import { api, renewSessionIfDue, session, setUnauthorizedHandler } from './lib/api.js';
import { RESET_ROUTE, isResetRoute, resetTokenFromHash } from './lib/recovery.js';
import * as home from './pages/home/index.js';
import { showLogin } from './pages/auth/login.js';
import { showForgotPassword, showResetPassword } from './pages/auth/recover.js';
import { stopPresence } from './lib/presence.js';
import { renderShell, showLoadError, showLoading } from './ui/layout.js';
import { closeMenu } from './ui/menu.js';
import { openPlayingSheet } from './ui/playing.js';
import { inviteToPush } from './ui/push-invite.js';

const ROUTES = [
  { prefix: '#/admin', load: () => import('./pages/admin/index.js') },
  { prefix: '#/profile', load: () => import('./pages/profile/index.js') },
  { prefix: '#/game/', load: () => import('./pages/game/index.js') },
  { prefix: '#/activity', load: () => import('./pages/activity/index.js') },
  { prefix: '#/recap', load: () => import('./pages/recap/index.js') },
  { prefix: '#/stats', load: () => import('./pages/stats/index.js') },
  { prefix: '#/games', load: () => import('./pages/games/index.js') },
  { prefix: '#/recommendations', load: () => import('./pages/recommendations/index.js') },
  { prefix: '#/challenges', load: () => import('./pages/challenges/index.js') },
  { prefix: '#/calendar', load: () => import('./pages/calendar/index.js') },
  { prefix: '#/wishlist', load: () => import('./pages/wishlist/index.js') },
  { prefix: '#/achievements', load: () => import('./pages/achievements/index.js') },
  { prefix: '#/players', load: () => import('./pages/players/index.js') },
  { prefix: '#/player/', load: () => import('./pages/player/index.js') },
];

let navigation = 0; // only the most recent navigation may touch the DOM
let currentPage = null;
let knownUser = null; // the logged-in user, kept between screens and refreshed behind them

const loadPage = (hash) => ROUTES.find((r) => hash.startsWith(r.prefix))?.load() ?? Promise.resolve(home);

function leaveCurrentPage() {
  closeMenu();
  currentPage?.dispose?.();
  currentPage = null;
}

function endSession() {
  session.clear();
  knownUser = null;
  stopPresence();
  leaveCurrentPage();
}

function logout() {
  endSession();
  showLogin(route);
}

// The first screen waits for the user; the next ones show the one already known while it is asked again, so
// changing screens costs no round trip. A session that ended meanwhile still ends at that answer: a 401 shows the
// login (api.js) and a disabled account (400) is logged out.
function currentUser() {
  const asking = api('/auth/active_user').then((user) => {
    if (user) knownUser = user;
    return user;
  });
  if (!knownUser) return asking;
  asking.catch((err) => { if (err.status === 400) logout(); });
  return Promise.resolve(knownUser);
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
  if (!knownUser) showLoading();

  let page;
  let user;
  try {
    // the page's code and the user travel together: nothing waits for the other
    [page, user] = await Promise.all([loadPage(location.hash), currentUser()]);
  } catch (err) {
    if (!isCurrent() || !session.getToken()) return;
    // a disabled account (400) has no session left; anything else (no connection, a 5xx) is passing
    if (err.status === 400) return logout();
    console.error(err);
    return showLoadError({ onRetry: route, onLogout: logout });
  }
  if (!user || !isCurrent()) return;

  if (page.adminOnly && !user.is_admin) {
    // The API enforces this too; this is just UX. replaceState => no hashchange.
    history.replaceState(null, '', location.pathname);
    return route();
  }

  const main = renderShell({ user, active: page.active, mainClass: page.mainClass, onLogout: logout });
  currentPage = page;
  renewSessionIfDue();
  try {
    await page.render({ user, main, isCurrent, onLogout: logout });
  } catch (err) {
    // a 401 already showed the login; any other failure stays on this screen, in the session
    if (!isCurrent() || !session.getToken()) return;
    console.error(err);
    return showLoadError({ container: main, onRetry: route, onLogout: logout });
  }
  if (location.hash === '#/playing' && isCurrent()) {
    // the shortcut of the installed app: the home page with the sheet open
    history.replaceState(null, '', location.pathname);
    openPlayingSheet(user.id);
  }
  inviteToPush().catch(() => {}); // optional: never blocks or breaks a page
}

setUnauthorizedHandler(() => {
  endSession();
  showLogin(route);
});

window.addEventListener('hashchange', () => {
  if (session.getToken() || isResetRoute(location.hash)) route();
});

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => navigator.serviceWorker.register('/sw.js').catch(console.warn));
}

route();
