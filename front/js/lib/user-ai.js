// "Mi IA" (profile, Ajustes): the pure part of the player's own AI keys screen: the providers, who pays for each feature and how a model
// reads. The screen is pages/profile/ai.js. Everything comes from GET /users/{username}/ai and /ai/{provider}/models.
import { budgetLine } from './ai-budget.js';
import { money } from './ai-usage.js';

export const TIERS = {
  economico: 'económico',
  medio: 'precio medio',
  caro: 'caro',
  sin_precio: 'sin precio conocido',
};

// The providers a player can have a key for, in the order the screen shows them. `pattern` is what their keys look like (the API checks it
// again and then asks the provider, which spends nothing): OpenAI's `sk-` also starts the other two, so they are told apart by their prefix.
export const PROVIDERS = [
  {
    id: 'openai', name: 'OpenAI', placeholder: 'sk-…', pattern: /^sk-(?!ant-|or-)[A-Za-z0-9_-]{16,300}$/,
    url: 'https://platform.openai.com/api-keys', where: 'platform.openai.com',
    limit: 'Crea en platform.openai.com un proyecto solo para La Viciación con un límite de gasto mensual y usa una clave de ese proyecto.',
  },
  {
    id: 'anthropic', name: 'Anthropic (Claude)', placeholder: 'sk-ant-…', pattern: /^sk-ant-[A-Za-z0-9_-]{16,300}$/,
    url: 'https://platform.claude.com/settings/keys', where: 'platform.claude.com',
    limit: 'En la consola de Anthropic crea una clave solo para La Viciación (en su propio espacio de trabajo, con un límite de gasto mensual).',
  },
  {
    id: 'google', name: 'Google (Gemini)', placeholder: 'AIza…', pattern: /^AIza[A-Za-z0-9_-]{20,60}$/,
    url: 'https://aistudio.google.com/apikey', where: 'aistudio.google.com',
    limit: 'Una clave de Google AI Studio del plan gratuito no gasta nada, pero la búsqueda web de la guía necesita un plan de pago.',
  },
  {
    id: 'openrouter', name: 'OpenRouter', placeholder: 'sk-or-…', pattern: /^sk-or-[A-Za-z0-9_-]{16,300}$/,
    url: 'https://openrouter.ai/settings/keys', where: 'openrouter.ai',
    limit: 'En OpenRouter puedes poner a cada clave un límite de crédito: crea una solo para La Viciación. Los modelos se escriben proveedor/modelo.',
  },
];

export const providerName = (id) => PROVIDERS.find((p) => p.id === id)?.name ?? id;

export const FEATURES = [
  ['chat', 'El chat'],
  ['guide', 'La guía de cada juego'],
];

// What the chat and the guide do, for the player who is deciding whether to use them (Mi IA). It says what each one is for, what it
// costs in words of cost and, for the guide, what it adds over asking ChatGPT directly: its limits too, because a claim that cannot
// be checked is not a reason to spend. Plain text: the screen draws it with the html template.
export const ABOUT = {
  chat: {
    title: 'El chat',
    what: [
      'Responde sobre los datos del grupo: horas, rankings, rachas, logros, juegos, lista de deseados y cómo funciona la app.',
      'Ve lo mismo que ves tú en el grupo, nunca la biblioteca ni los datos privados de otra persona.',
      'No guarda la conversación: al recargar la página empiezas de cero.',
    ],
    cost: 'Cada pregunta hace unas pocas llamadas al modelo: con uno económico, una fracción de céntimo.',
  },
  guide: {
    title: 'La guía de cada juego',
    what: [
      'Te ayuda con un juego concreto: desatascarte, orientarte y darte consejos. La encuentras en la página de cada juego y en el botón «¿Atascado?» del timer.',
      'Tú eliges cuánta ayuda quieres: empujón (una dirección), pista (qué hacer) o solución (paso a paso, con destripes). No sube de nivel por su cuenta.',
      'Busca en internet y dice de dónde saca lo que cuenta; si no encuentra algo fiable, lo dice en lugar de inventarlo.',
    ],
    addsTitle: 'Qué aporta frente a preguntárselo directamente a ChatGPT',
    adds: [
      'Ya sabe de qué juego hablas, cuánto llevas, si lo has completado y quién del grupo lo terminó (a quién preguntar), sin que lo expliques cada vez.',
      'El nivel de destripes lo eliges tú antes de preguntar y se respeta.',
      'Viene preparada para buscar, citar la fuente y reconocer cuando no sabe, en vez de contestar de memoria con seguridad.',
      'Está a un toque desde el timer, con la partida en marcha, y la conversación se queda en la página de ese juego.',
    ],
    limit: 'No sabe más que ChatGPT ni sustituye a una guía completa: depende de lo que encuentre en la web, y lo importante conviene comprobarlo.',
    cost: 'Cada pregunta hace además búsquedas en internet, que se cobran aparte de los tokens (con OpenAI, del orden de un céntimo cada una): suele costar varias veces lo que una del chat.',
  },
};

/** What a model reads like in the list: its name, how much it weighs on the account and its price per million tokens. */
export function modelLabel(model) {
  const price = model.output_per_million == null
    ? ''
    : ` · ${money(model.input_per_million)} / ${money(model.output_per_million)} por millón`;
  return `${model.id} · ${TIERS[model.tier] ?? TIERS.sin_precio}${price}`;
}

// Where the cost of a feature goes for this player: the group's key comes first, while the group can pay for this player, and the
// player's own is what goes on after it (or the only one, if an admin set the feature that way). `fallback` is a question already
// going on with the player's own key because the group's cannot be used for them (their monthly share or their balance is spent).
function kindOf(feature) {
  if (feature.paid_by === 'user') return feature.blocked ? 'fallback' : 'own';
  if (feature.paid_by === 'group') return feature.mode === 'group_only' ? 'group_only' : 'group';
  return feature.locked ? 'locked' : 'needs';
}

/** Whether the player has a key of their own for any provider (`keys` of GET /users/{username}/ai). */
export const hasAnyKey = (keys) => Object.values(keys ?? {}).some((k) => k.has_key);

/** A short, quiet note on where the cost of the chat and the guide goes, from their states ({ available, needs_key, paid_by, mode,
 * blocked, locked }) and whether the player has a key of their own: it says what is true for this player now and nothing more. */
export function costNote({ chat, guide, keys }) {
  const hasKey = hasAnyKey(keys);
  const features = [
    { feature: chat, of: 'del chat', is: 'el chat', cap: 'El chat' },
    { feature: guide, of: 'de la guía', is: 'la guía', cap: 'La guía' },
  ];
  const notes = features.filter((f) => !f.feature.available).map((f) => `${f.cap}${f.is === 'la guía' ? ' de cada juego' : ''} no está disponible ahora mismo.`);
  const byKind = {};
  for (const f of features.filter((x) => x.feature.available)) (byKind[kindOf(f.feature)] ??= []).push(f);
  const subject = (list) => [list[0].cap, ...list.slice(1).map((f) => f.is)].join(' y '); // 'El chat y la guía'
  const after = hasKey ? 'después seguirá con tu clave, a tu cuenta del proveedor' : 'después necesitarás tu propia clave';
  for (const [kind, list] of Object.entries(byKind)) {
    const of = list.map((f) => f.of).join(' y ');
    if (kind === 'group_only') notes.push(`El coste ${of} lo cubre el grupo, tengas clave o no.`);
    else if (kind === 'group') notes.push(`El coste ${of} lo cubre el grupo mientras haya saldo; ${after}.`);
    else if (kind === 'own') notes.push(`El coste ${of} va a tu cuenta del proveedor de tu clave.`);
    else if (kind === 'fallback') notes.push(`Ya no puedes usar la clave del grupo: de momento el coste ${of} va a tu cuenta del proveedor de tu clave.`);
    else if (kind === 'locked') notes.push(`${subject(list)} ${list.length > 1 ? 'funcionan' : 'funciona'} con tu propia clave, que está bloqueada en esta sesión: escribe tu contraseña abajo.`);
    else if (list.length === 1 && list[0].is === 'la guía') notes.push('La guía de cada juego busca en internet y cuesta más: funciona con tu propia clave.');
    else notes.push(`${subject(list)} ${list.length > 1 ? 'funcionan' : 'funciona'} con tu propia clave.`);
  }
  return notes.join(' ');
}

/** What the player paid with their own key and what the group's key covered for them, from the usage's `by_source` (dollars). */
export function paidBy(data) {
  const cost = (name) => data.by_source.find((s) => s.name === name)?.cost ?? 0;
  return { own: cost('user'), group: cost('group') };
}

/** The line about the player's monthly share of the group's key, or none when they have no cap (0 is a cap: nothing of the group's key): what is spent of it and when it starts again. */
export function budgetLines(budget) {
  return budget.user.cap == null ? [] : [budgetLine('Tu parte de la IA del grupo este mes', budget.user, budget.resets_on)];
}

/** What a feature's state says when the player's cap or balance stops the group's key from answering them (else null). */
export function blockedText(state) {
  if (state.paid_by === 'user') return null; // the player's own key took over: the note above says so
  if (state.blocked === 'user') return 'Has gastado tu parte de la IA del grupo este mes.';
  if (state.blocked === 'user_off') return 'Un admin no te ha dado IA de la clave del grupo.';
  if (state.blocked === 'wallet') return 'No tienes saldo de IA del grupo.';
  return null;
}

/** The key as the player sees it: the last characters (only while their session is unlocked), never the key. */
export const keyText = (status) => (status.hint ? `Clave guardada, termina en …${status.hint}` : 'Clave guardada');

/** The key field's value looks like a key of `provider` (the API checks it for real with the provider). */
export const looksLikeKey = (provider, value) => Boolean(PROVIDERS.find((p) => p.id === provider)?.pattern.test(String(value).trim()));
