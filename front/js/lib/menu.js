// Structure of the side menu. Pure: no DOM, so it can be tested. Each item is { id, label, href, icon, wip? }
// (icon is the name of a function of ui/icons.js); `logout` is not a link, the menu draws it apart at the foot.

/** The sections of the menu for `user`; an empty section (the admin one for a player) is left out. */
export function menuSections(user) {
  return [
    { label: 'Principal', items: [
      { id: 'home', label: 'Inicio', href: '#', icon: 'iconHome' },
      { id: 'activity', label: 'Actividad', href: '#/activity', icon: 'iconActivity' },
    ] },
    { label: 'Explorar', items: [
      { id: 'games', label: 'Juegos', href: '#/games', icon: 'iconGamepad' },
      { id: 'achievements', label: 'Logros', href: '#/achievements', icon: 'iconTrophy' },
      { id: 'players', label: 'Jugadores', href: '#/players', icon: 'iconPerson' },
      { id: 'stats', label: 'Estadísticas', href: '#/stats', icon: 'iconChart', wip: true },
    ] },
    { label: 'Tú', items: [
      { id: 'profile', label: 'Mi perfil', href: '#/profile/resumen', icon: 'iconProfile' },
      { id: 'settings', label: 'Ajustes', href: '#/profile/ajustes', icon: 'iconSettings' },
    ] },
    { label: 'Administración', items: user?.is_admin ? [
      { id: 'admin', label: 'Panel de administración', href: '#/admin', icon: 'iconShield' },
    ] : [] },
  ].filter((section) => section.items.length);
}

// The item a page address belongs to, longest prefix first so '#/profile/ajustes' is not just 'profile'.
const PAGES = [
  ['#/profile/ajustes', 'settings'],
  ['#/profile', 'profile'],
  ['#/admin', 'admin'],
  ['#/activity', 'activity'],
  ['#/stats', 'stats'],
  ['#/games', 'games'],
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
