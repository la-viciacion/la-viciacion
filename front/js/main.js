// Entry point: hash router + session handling.
//
// A page module exports:
//   active      navbar item to highlight ('home' | 'profile' | 'admin')
//   mainClass   optional class for <main>
//   adminOnly   optional; non-admins are sent home
//   render({ user, main, avatarUrl, isCurrent })   fills <main>; isCurrent() turns false
//                                       once the user navigated elsewhere
//   dispose()   optional cleanup when leaving the page
import { api, loadAvatarUrl, session, setUnauthorizedHandler } from './lib/api.js';
import * as home from './pages/home/index.js';
import { showLogin } from './pages/login.js';
import { renderShell, showLoading } from './ui/layout.js';
import { inviteToPush } from './ui/push-invite.js';

const ROUTES = [
  { prefix: '#/admin', load: () => import('./pages/admin/index.js') },
  { prefix: '#/profile', load: () => import('./pages/profile/index.js') },
];

let navigation = 0; // only the most recent navigation may touch the DOM
let currentPage = null;

const loadPage = (hash) => ROUTES.find((r) => hash.startsWith(r.prefix))?.load() ?? Promise.resolve(home);

function leaveCurrentPage() {
  currentPage?.dispose?.();
  currentPage = null;
}

function logout() {
  session.clear();
  leaveCurrentPage();
  showLogin(route);
}

async function route() {
  const id = ++navigation;
  const isCurrent = () => id === navigation;
  leaveCurrentPage();

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
    await page.render({ user, main, avatarUrl, isCurrent });
    inviteToPush().catch(() => {}); // optional: never blocks or breaks a page
  } catch (err) {
    console.error(err);
    if (!isCurrent()) return;
    session.clear();
    showLogin(route);
  }
}

setUnauthorizedHandler(() => {
  leaveCurrentPage();
  showLogin(route);
});

window.addEventListener('hashchange', () => {
  if (session.getToken()) route();
});

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => navigator.serviceWorker.register('/sw.js').catch(console.warn));
}

route();
