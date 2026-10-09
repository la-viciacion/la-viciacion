// How the admin panel's audit log reads: a Spanish sentence for each write and a compact view of its detail.
// Pure (no DOM), so it can be tested.

const ENTITY = {
  users: 'usuario',
  games: 'juego',
  platforms: 'plataforma',
  timers: 'sesión',
  library: 'entrada de biblioteca',
  scores: 'puntuación',
  achievements: 'logro',
  'user-achievements': 'logro concedido',
};

// Writes that are not "create/edit/delete a row", most specific first: [method, pattern of the path under /manage, sentence]
const ACTIONS = [
  ['POST', /^users\/\d+\/password$/, 'Cambió la contraseña de un usuario'],
  ['PUT', /^settings$/, 'Cambió los ajustes'],
  ['POST', /^settings\/push-keys$/, 'Generó las claves de los avisos en la app'],
  ['POST', /^settings\/test-/, 'Probó un ajuste'],
  ['POST', /^push\/announce$/, 'Envió un aviso en la app'],
  ['POST', /^telegram\/announce$/, 'Envió un aviso por Telegram'],
  ['POST', /^check-achievements$/, 'Pidió comprobar los logros'],
  ['POST', /^recalculate-achievements$/, 'Pidió recalcular todos los logros'],
  ['POST', /^rawg-sync\//, 'Usó la sincronización con RAWG'],
  ['POST', /^hltb-sync\//, 'Usó la sincronización de tiempos con HowLongToBeat'],
];

const VERB = { POST: 'Creó', PUT: 'Cambió', PATCH: 'Editó', DELETE: 'Borró' };

export const ENTITY_OPTIONS = Object.entries(ENTITY).map(([value, label]) => [value, label[0].toUpperCase() + label.slice(1)]);

/** "Editó sesión #12" for a row of the log. */
export function describe(entry) {
  const rest = String(entry.path || '').replace(/^.*?\/manage\//, '');
  for (const [method, pattern, sentence] of ACTIONS) {
    if (entry.method === method && pattern.test(rest)) return sentence;
  }
  const verb = VERB[entry.method] || entry.method;
  const what = ENTITY[entry.entity] || entry.entity || 'datos';
  return `${verb} ${what}${entry.entity_id ? ` #${entry.entity_id}` : ''}`;
}

/** The parts of the detail worth showing, as [title, text] pairs (empty when there is nothing to show). */
export function detailParts(entry) {
  const detail = entry.detail || {};
  const parts = [];
  if (detail.before) parts.push(['Antes', JSON.stringify(detail.before, null, 2)]);
  if (detail.body) parts.push(['Enviado', JSON.stringify(detail.body, null, 2)]);
  if (detail.query) parts.push(['Consulta', detail.query]);
  if (detail.truncated) parts.push(['Detalle (cortado)', detail.truncated]);
  return parts;
}
