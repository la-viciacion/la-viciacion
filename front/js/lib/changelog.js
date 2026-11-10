// The changelog the players read (#/changelog). It is written by hand and is NOT the GitHub release notes: those list
// every commit; this lists only what a player notices while using the app, and several small releases share one entry.
//
// What never goes here (tests/changelog.test.js guards the obvious words): anything about the admin panel, secrets or
// keys, how an achievement is unlocked, easter eggs, the inner workings of the app or its infrastructure. If it does
// not change what a player sees or does, it is not an entry.
//
// To add a release: put a new entry FIRST, with the number of the newest release it covers (`version`) and its date.
// While a group of releases is still small, extend the newest entry (move its `version` and `date`) instead of adding
// another one; open a new entry when a release brings something worth its own title.
// Item kinds: 'new' (something that was not there), 'better' (something that was already there and now is nicer or
// easier), 'fix' (something that did not work and now does).

// The published user guide (the MkDocs site of the repository, only its player pages)
export const DOCS_URL = 'https://la-viciacion.github.io/la-viciacion/guia-usuario/';

export const KINDS = {
  new: 'Nuevo',
  better: 'Mejora',
  fix: 'Arreglo',
};

export const CHANGELOG = [
  {
    version: '2.40', date: '2026-11-10',
    title: 'Novedades y tus ids de jugador',
    items: [
      ['new', 'Novedades: una página que cuenta lo que va cambiando en la app, con un enlace a la documentación completa. Se abre pulsando la versión al pie del menú.'],
      ['new', 'Puedes añadir tus ids de Nintendo, Xbox, PlayStation, Steam y Discord en Perfil → Ajustes, y el grupo los ve en tu página de jugador, con un toque para copiarlos.'],
    ],
  },
  {
    version: '2.39', date: '2026-11-10',
    title: 'Temporada y perfil',
    items: [
      ['new', 'Temporada: en Explorar, los rankings de la temporada en curso dibujados como podios.'],
      ['new', 'Puedes retrasar la hora de inicio de un timer en marcha sin pararlo.'],
      ['better', 'En el perfil, tus juegos se pueden plegar y la lista de juegos cortos se entiende mejor.'],
      ['better', 'Iconos de ayuda junto a los apartados que necesitan una explicación.'],
      ['new', 'Servidor: una página abierta a todos con el estado de la máquina y lo que cuesta mantener la app, mes a mes.'],
      ['better', 'El menú Explorar tiene un orden nuevo y «Biblioteca» se llama ahora así, sin «del grupo».'],
      ['better', 'La página de logros y el perfil están más pulidos.'],
    ],
  },
  {
    version: '2.34', date: '2026-11-03',
    title: 'Nuevos datos de juegos y retos más flexibles',
    items: [
      ['new', 'Las fichas de los juegos usan una fuente de datos nueva, más completa, y enseñan la nota de los usuarios.'],
      ['new', 'La ficha de un juego separa lo que dice el mundo de lo vuestro, en una sección «En el grupo».'],
      ['new', 'Una barra y una tarjeta te invitan a completar tu perfil.'],
      ['new', 'Los retos del grupo pueden durar un mes, una semana o unas fechas libres.'],
      ['better', 'En Inicio, tus retos son un único bloque compacto con los dos que más atención piden.'],
      ['fix', 'Si el servicio de datos de juegos falla, la búsqueda lo dice en vez de mostrar «sin resultados».'],
    ],
  },
  {
    version: '2.30', date: '2026-10-31',
    title: 'Más retos y un calendario más útil',
    items: [
      ['new', 'Retos para terminar los juegos que tienes empezados, para sumar horas entre todos y un duelo de juegos completados.'],
      ['new', 'Los retos temáticos parten de temáticas ya preparadas.'],
      ['new', 'Encuestas en el grupo de Telegram para votar, y en algunas puedes añadir tus propias opciones.'],
      ['new', 'En el calendario de lanzamientos, al pulsar un día se abre la lista de sus juegos.'],
      ['fix', 'El calendario resalta el día de hoy.'],
    ],
  },
  {
    version: '2.23', date: '2026-10-27',
    title: 'La ficha del juego, la biblioteca y los lanzamientos',
    items: [
      ['new', 'La ficha de un juego enseña su descripción, desarrollador, plataformas y multimedia, y los juegos nombrados en la app enlazan a ella.'],
      ['new', 'Biblioteca con estados (en curso, pausado, pendiente…), tu ritmo frente al del grupo, la biblioteca del grupo, sagas y precios.'],
      ['new', 'Los DLC y las expansiones se marcan como tales y enlazan a su juego base.'],
      ['new', 'Desde la tarjeta del timer puedes continuar con el último juego que jugaste.'],
      ['new', 'Avisos de los lanzamientos de tu lista de deseados: al grupo (la víspera, el mismo día o un resumen semanal) y a ti, el día de salida.'],
      ['new', 'Retos ampliados: duelos entre jugadores, retos a partir de plantillas y propuestas de retos para el grupo.'],
      ['better', 'Un juego jugado en varias plataformas en una temporada sale en una sola fila de la biblioteca.'],
      ['better', 'Los botones de las filas del timer son más grandes y las plataformas salen por orden alfabético.'],
      ['better', 'Los ajustes del perfil se reparten en grupos y la página de jugadores enseña solo a los activos, salvo que quieras ver a todos.'],
      ['better', 'Los apartados plegables tienen un botón con etiqueta.'],
      ['better', 'Un deseo se queda en tu lista cuando ya tienes el juego, con una etiqueta que lo dice.'],
      ['fix', 'Las fechas de sesiones de otros años enseñan el año.'],
      ['fix', 'Los enlaces de los avisos de la app se ven como texto y el aviso de juego empezado abre la ficha del juego.'],
    ],
  },
  {
    version: '2.14', date: '2026-10-21',
    title: 'Bandeja de avisos y asistente',
    items: [
      ['new', 'Una bandeja dentro de la app guarda tus avisos.'],
      ['new', 'Un asistente en un botón flotante contesta sobre juegos y sobre los datos del grupo, y explica cómo funciona la app.'],
      ['fix', 'El asistente se mantiene a la vista cuando se abre el teclado del móvil.'],
    ],
  },
  {
    version: '2.8', date: '2026-10-19',
    title: 'Tu resumen',
    items: [
      ['new', 'Resumen mensual en forma de historias, para ver tu mes de un vistazo y compartirlo.'],
      ['new', 'Resumen anual, con un único aviso cuando está listo.'],
      ['better', 'Imágenes nuevas y renovadas en los logros.'],
      ['fix', 'El resumen se detiene en el mes anterior al que está en curso.'],
    ],
  },
  {
    version: '2.4', date: '2026-10-15',
    title: 'Calendario de lanzamientos, afinidad y retos',
    items: [
      ['new', 'Calendario de lanzamientos de los juegos que espera el grupo, con una lista del mes al lado.'],
      ['new', 'En la página de otro jugador, la afinidad que tenéis y los juegos que compartís.'],
      ['new', 'Clasificación de la deuda (lo que te falta para terminar lo que has empezado) en las consultas de Telegram.'],
      ['new', 'Retos: el juego del mes, probar un género, bajar la deuda y retos temáticos del grupo.'],
      ['new', 'Se añaden logros nuevos.'],
      ['new', 'En tu perfil, «Mis juegos» con filtros y un botón para puntuar juegos al azar.'],
      ['better', 'Perfil y paneles más anchos, con casillas de cifras más compactas.'],
      ['fix', 'Actividad ordena los eventos por la hora a la que pasaron.'],
      ['fix', 'El tiempo de un juego completado suma todas las sesiones desde la vez anterior que lo completaste.'],
    ],
  },
  {
    version: '2.1', date: '2026-10-08',
    title: 'La versión 2.0',
    items: [
      ['new', 'Puntúa los juegos de 1 a 100; las notas de los demás influyen en tus recomendaciones.'],
      ['new', 'Jugando ahora: la barra de arriba enseña quién está jugando, y agrupa a quienes juegan lo mismo.'],
      ['new', 'Página de cada juego con quién del grupo lo juega, sus horas y sus notas.'],
      ['new', 'Página de actividad del grupo.'],
      ['new', 'Menú lateral con las secciones de la app.'],
      ['new', 'Logros: una página con el catálogo y quién tiene cada uno, y logros nuevos.'],
      ['new', 'Si un juego no aparece en la búsqueda, puedes crearlo tú a mano; también cuando el servicio de datos de juegos no responde.'],
      ['new', 'Juegos: el catálogo entero con búsqueda, filtros y orden.'],
      ['new', 'Jugadores: la lista del grupo y el perfil público de cada uno.'],
      ['new', 'Deseados: tu lista de deseos y los próximos lanzamientos.'],
      ['new', 'Puedes marcar un juego como abandonado desde la lista y retomarlo después.'],
      ['new', 'Atajos de la app instalada y su nombre correcto, «La Viciación».'],
      ['new', 'Un mensaje de prueba comprueba desde el perfil que tu Telegram está bien vinculado.'],
      ['new', 'Eliges por canal si quieres el aviso de un timer olvidado.'],
      ['better', 'En tu perfil, los juegos se filtran por temporada.'],
      ['better', 'La app carga bastante más rápido.'],
      ['better', 'Completar un juego es una sola pulsación.'],
      ['better', 'Los jugadores que ya no juegan se siguen viendo por la app.'],
      ['better', 'Las sesiones manuales piden confirmación y no se pueden añadir con un timer en marcha.'],
    ],
  },
];

/** The items of an entry grouped by kind, in the order of KINDS, leaving out the kinds with none. */
export function groups(entry) {
  return Object.keys(KINDS)
    .map((kind) => ({ kind, label: KINDS[kind], items: entry.items.filter(([k]) => k === kind).map(([, text]) => text) }))
    .filter((group) => group.items.length);
}
