// Structure of the side menu and of the bottom bar of a phone. Pure: no DOM, so it can be tested.
// Each item is { id, label, href, icon } (icon is the name of a function of ui/icons.js).

const SECTIONS = [
  { id: 'principal', label: 'Principal', items: [
    { id: 'home', label: 'Inicio', href: '#', icon: 'iconHome' },
    { id: 'activity', label: 'Actividad', href: '#/activity', icon: 'iconActivity' },
  ] },
  { id: 'group', label: 'Grupo', items: [
    { id: 'season', label: 'Temporada', href: '#/season', icon: 'iconClock' },
    { id: 'players', label: 'Jugadores', href: '#/players', icon: 'iconPerson' },
    { id: 'challenges', label: 'Retos', href: '#/challenges', icon: 'iconFlag' },
    { id: 'achievements', label: 'Logros', href: '#/achievements', icon: 'iconTrophy' },
  ] },
  { id: 'games', label: 'Juegos', items: [
    { id: 'games', label: 'Juegos', href: '#/games', icon: 'iconGamepad' },
    { id: 'library', label: 'Biblioteca', href: '#/library', icon: 'iconStar' },
    { id: 'calendar', label: 'Calendario', href: '#/calendar', icon: 'iconCalendar' },
  ] },
  { id: 'you', label: 'Tú', items: [
    { id: 'profile', label: 'Mi perfil', href: '#/profile/resumen', icon: 'iconProfile' },
    { id: 'wishlist', label: 'Deseados', href: '#/wishlist', icon: 'iconHeart' },
    { id: 'recommendations', label: 'Recomendados', href: '#/recommendations', icon: 'iconDice' },
  ] },
];

// What is not about the games nor the group: the last section of the menu ("Más"), scrolling with the rest.
const FOOT = [
  { id: 'settings', label: 'Ajustes', href: '#/profile/ajustes', icon: 'iconSettings' },
  { id: 'server', label: 'Servidor', href: '#/server', icon: 'iconServer' },
  { id: 'admin', label: 'Panel de administración', href: '#/admin', icon: 'iconShield', admin: true },
];

/** The sections of the menu: { label, items }. */
export const menuSections = () => SECTIONS.map(({ label, items }) => ({ label, items }));

/** The items of the last section of the menu for `user` (the administration only for an admin). */
export const menuFoot = (user) => FOOT.filter((item) => !item.admin || user?.is_admin);

/** Every page the menu reaches, in order (the search looks among them). */
export const menuPages = (user) => [...SECTIONS.flatMap((section) => section.items), ...menuFoot(user)];

// The tabs of the bottom bar of a phone: each leads to the main page of its section and is lit on any of them.
// The settings belong to "Tú" (they are a part of the profile); the server and the admin panel to none.
const TABS = [
  { id: 'principal', label: 'Inicio', href: '#', icon: 'iconHome' },
  { id: 'group', label: 'Grupo', href: '#/season', icon: 'iconPerson' },
  { id: 'games', label: 'Juegos', href: '#/games', icon: 'iconGamepad' },
  { id: 'you', label: 'Tú', href: '#/profile/resumen', icon: 'iconProfile' },
];

export const bottomTabs = () => TABS;

/** The id of the section (and so of the tab) a menu item belongs to; null for the ones of the foot. */
export function sectionOf(itemId) {
  if (itemId === 'settings') return 'you';
  return SECTIONS.find((section) => section.items.some((item) => item.id === itemId))?.id ?? null;
}

// The item a page address belongs to, longest prefix first so '#/profile/ajustes' is not just 'profile'.
const PAGES = [
  ['#/profile/ajustes', 'settings'],
  ['#/profile', 'profile'],
  ['#/admin', 'admin'],
  ['#/activity', 'activity'],
  ['#/season', 'season'],
  ['#/server', 'server'],
  ['#/games', 'games'],
  ['#/library', 'library'],
  ['#/wishlist', 'wishlist'],
  ['#/calendar', 'calendar'],
  ['#/challenges', 'challenges'],
  ['#/recommendations', 'recommendations'],
  ['#/achievements', 'achievements'],
  ['#/players', 'players'],
  ['#/player', 'players'],
  ['#/game', 'games'],
];

/** The id of the item to highlight for an address (null for the pages that have no item). */
export function activeItem(hash) {
  if (!hash || hash === '#' || hash === '#/') return 'home';
  return PAGES.find(([prefix]) => hash === prefix || hash.startsWith(`${prefix}/`))?.[1] ?? null;
}
