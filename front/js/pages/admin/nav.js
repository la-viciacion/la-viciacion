// Structure and addresses of the admin panel. Pure: no DOM, so it can be tested.
// The sidebar lists SECTIONS; a section with several tabs shows them under its title.
// Every tab id is a key of ENTITIES (entities.js) and its address is #/admin/<id> (an entity that is a `companion` of another has no tab).

export const HOME = 'home';

export const SECTIONS = [
  { label: 'Inicio', tabs: [HOME] },
  { label: 'Catálogo', tabs: ['games', 'platforms', 'achievements'] },
  { label: 'Jugadores', tabs: ['users', 'timers', 'library', 'scores', 'awards'] },
  { label: 'Comunidad', tabs: ['challenges', 'proposals', 'polls', 'announce'] },
  { label: 'Notificaciones', tabs: ['sends', 'channels', 'recap'] },
  { label: 'IA', tabs: ['ai', 'chat', 'ailimits', 'aiusage'] },
  { label: 'Sistema', tabs: ['costs', 'backup', 'audit'] },
];

// Tabs that no longer exist and the one that took their content, so an old link or bookmark still lands somewhere useful.
export const MOVED = { services: 'channels' };

export const TAB_IDS = SECTIONS.flatMap((section) => section.tabs);

export const sectionOf = (tab) => SECTIONS.find((section) => section.tabs.includes(tab));

export const hashFor = (tab) => (tab === HOME ? '#/admin' : `#/admin/${tab}`);

/** The tab an address points at; a tab that was folded into another goes to that one, anything unknown (or no tab) is the home page. */
export function tabFromHash(hash, valid = TAB_IDS) {
  const match = /^#\/admin\/([a-z]+)\/?$/.exec(hash);
  const id = match && (MOVED[match[1]] ?? match[1]);
  return id && valid.includes(id) ? id : HOME;
}
