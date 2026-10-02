// Structure and addresses of the admin panel. Pure: no DOM, so it can be tested.
// The sidebar lists SECTIONS; a section with several tabs shows them under its title.
// Every tab id is a key of ENTITIES (entities.js) and its address is #/admin/<id>.

export const HOME = 'home';

export const SECTIONS = [
  { label: 'Inicio', tabs: [HOME] },
  { label: 'Gestión de datos', tabs: ['users', 'games', 'platforms', 'timers', 'library', 'achievements', 'awards'] },
  { label: 'Notificaciones', tabs: ['notifications', 'announce'] },
  { label: 'Sistema', tabs: ['system'] },
];

export const TAB_IDS = SECTIONS.flatMap((section) => section.tabs);

export const sectionOf = (tab) => SECTIONS.find((section) => section.tabs.includes(tab));

export const hashFor = (tab) => (tab === HOME ? '#/admin' : `#/admin/${tab}`);

/** The tab an address points at; anything unknown (or no tab) is the home page. */
export function tabFromHash(hash, valid = TAB_IDS) {
  const match = /^#\/admin\/([a-z]+)\/?$/.exec(hash);
  return match && valid.includes(match[1]) ? match[1] : HOME;
}
