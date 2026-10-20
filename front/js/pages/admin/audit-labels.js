// How the admin panel's audit log reads: a Spanish sentence for each write and a compact view of its detail.
// Pure (no DOM), so it can be tested.

const ENTITY = {
  users: 'usuario',
  games: 'juego',
  platforms: 'plataforma',
  timers: 'sesión',
  library: 'entrada de biblioteca',
  scores: 'puntuación',
  challenges: 'reto',
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

// Security events (rows with an `event`): the sentence, or a function of the entry when the detail changes it
const EVENTS = {
  login: 'Inició sesión',
  login_failed: (e) => (e.detail?.locked ? 'Intento de acceso fallido (cuenta bloqueada unos minutos)' : 'Intento de acceso fallido'),
  login_disabled: 'Intentó entrar con la cuenta desactivada',
  password_changed: 'Cambió su contraseña',
  password_change_failed: 'Falló al cambiar su contraseña (la actual no era correcta)',
  recovery_requested: (e) => (e.detail?.sent ? 'Pidió recuperar la contraseña (enlace enviado)' : 'Pidió recuperar la contraseña (sin enlace: la cuenta no existe, no tiene correo o ya pidió varios)'),
  password_reset: 'Eligió una contraseña nueva con el enlace de recuperación',
  password_reset_failed: 'Usó un enlace de recuperación que no vale',
  profile_updated: (e) => `Cambió ${Object.keys(e.detail?.changed || {}).map((k) => (k === 'telegram_id' ? 'el id de Telegram' : 'el email')).join(' y ')}${e.detail?.account && e.detail.account !== e.username ? ` de ${e.detail.account}` : ''}`,
  admin_denied: 'Intentó usar el panel de administración sin ser admin',
};

const VERB = { POST: 'Creó', PUT: 'Cambió', PATCH: 'Editó', DELETE: 'Borró' };

export const ENTITY_OPTIONS = Object.entries(ENTITY).map(([value, label]) => [value, label[0].toUpperCase() + label.slice(1)]);

/** "Editó sesión #12" for a row of the log. */
export function describe(entry) {
  if (entry.event) {
    const sentence = EVENTS[entry.event];
    return typeof sentence === 'function' ? sentence(entry) : sentence || entry.event;
  }
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
  if (entry.event) {
    const rest = Object.fromEntries(Object.entries(detail).filter(([key]) => !['before', 'body', 'query', 'truncated'].includes(key)));
    if (Object.keys(rest).length) parts.push(['Datos', JSON.stringify(rest, null, 2)]);
  }
  const origin = [entry.ip, entry.user_agent].filter(Boolean).join(' · ');
  if (origin) parts.push(['Desde', origin]);
  return parts;
}
