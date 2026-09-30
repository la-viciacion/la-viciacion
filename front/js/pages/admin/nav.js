// Sidebar structure and addresses of the admin panel. Pure: no DOM, so it can be tested.
// Every id is a key of ENTITIES (entities.js); the address of a section is #/admin/<id>.

export const HOME = 'home';

export const GROUPS = [
  { label: null, items: [HOME] },
  { label: 'Personas', items: ['users'] },
  { label: 'Contenido', items: ['games', 'platforms'] },
  { label: 'Actividad', items: ['timers', 'library'] },
  { label: 'Logros', items: ['achievements', 'awards'] },
  { label: 'Comunicación', items: ['announce', 'telegram', 'push'] },
  { label: 'Sistema', items: ['ai', 'mail'] },
];

export const hashFor = (tab) => (tab === HOME ? '#/admin' : `#/admin/${tab}`);

/** The section an address points at; anything unknown (or no section) is the home page. */
export function tabFromHash(hash, valid) {
  const match = /^#\/admin\/([a-z]+)\/?$/.exec(hash);
  return match && valid.includes(match[1]) ? match[1] : HOME;
}
