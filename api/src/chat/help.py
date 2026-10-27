"""What the chat can tell about the app itself: how it works, where things are, what the rules are.

Each topic is a short summary of a page of the user guide (`docs/guia-usuario/`, `source`), written for the model to answer
from; the guide is the source of truth and is not shipped in the API's image, so these summaries are kept here. A test
checks that every source exists, and that whoever changes one of those pages knows to look here (see docs/desarrollo/
conventions.md). Nothing here is data of the group: that comes from the other tools.
"""
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class Topic:
    id: str
    title: str
    keywords: tuple[str, ...]  # without accents, lowercase; a query word matches if it contains one or is part of one
    source: str  # the guide's page, relative to docs/guia-usuario/
    text: str


TOPICS = (
    Topic(
        "primeros_pasos", "Entrar, moverse por la app e instalarla", ("entrar", "acceso", "login", "contrasena", "menu", "instalar", "pwa", "movil", "sesion", "bloquea"),
        "primeros-pasos.md",
        "Se entra con el email o el usuario y la contraseña. Si se olvida, «¿Has olvidado tu contraseña?» manda un enlace al correo "
        "(vale 1 hora) y, sin correo configurado, un administrador puede poner otra. Tras 5 intentos fallidos seguidos la cuenta se bloquea "
        "un rato; cambiar la contraseña cierra la sesión en todos los dispositivos, y la sesión dura unos 7 días mientras se use. "
        "El botón de arriba a la izquierda abre el menú lateral: Principal (Inicio, Actividad), Explorar (Juegos, Biblioteca del grupo con joyas ocultas, cementerio, rarezas y juegos sin tocar, Calendario, Logros, "
        "Jugadores, Estadísticas, aún en construcción), Tú (Mi perfil, Resumen, Deseados, Recomendados, Retos, Ajustes) y, solo para "
        "administradores, Administración. Es una PWA: se instala desde el menú del navegador (Android: «Instalar aplicación»; iPhone/iPad: "
        "compartir → «Añadir a pantalla de inicio», imprescindible para las notificaciones; ordenador: icono de instalar). Ya instalada, "
        "mantener pulsado el icono da atajos a Nuevo timer, Jugando ahora y Mi perfil.",
    ),
    Topic(
        "sesiones", "Timers y sesiones", ("timer", "sesion", "sesiones", "cronometro", "registrar", "manual", "jugar", "olvidado", "editar", "borrar", "plataforma"),
        "sesiones.md",
        "Una sesión es un rato jugando a un juego en una plataforma: es lo único que registra el jugador, y de ellas se calculan las horas, "
        "rankings, rachas y logros. Con timer: en Inicio, «Nuevo timer», elegir el juego del catálogo y la plataforma; al terminar, «Detener» "
        "(o «Cancelar» si no debe contar). Mientras corre, el grupo ve al jugador como «jugando ahora». Si se olvida, pasadas 4 horas (se puede "
        "cambiar en Perfil → Ajustes → Notificaciones) la app avisa una sola vez; un timer olvidado se cierra editando su hora de fin o "
        "pidiéndoselo a un administrador. Si el juego no está, «¿No está? Añadir nuevo juego» lo busca en RAWG y, si tampoco está, se puede "
        "crear a mano con el nombre. Sesión manual («+ Sesión manual» en Inicio): fin posterior al inicio y no en el futuro, como máximo 24 horas, "
        "solo de la temporada en curso, sin solaparse con otra sesión propia y sin timer en marcha. Las sesiones propias de esta temporada "
        "se corrigen o borran en Perfil → Resumen → Juegos → Sesiones; si el juego es otro, se borra y se añade de nuevo (un administrador sí puede cambiarlo).",
    ),
    Topic(
        "completar_puntuar", "Completar, puntuar y abandonar juegos", ("completar", "completado", "terminar", "puntuar", "nota", "puntuacion", "valorar", "abandonar", "biblioteca"),
        "sesiones.md",
        "El círculo junto a un juego (en Inicio o en el perfil) lo marca como completado: se confirma en una ventana con un toque y se avisa al grupo. "
        "Un juego se completa una vez por temporada y solo en la temporada en curso; después la fecha queda congelada. Justo después se ofrece "
        "puntuarlo. La nota va de 1 a 100, una por juego (da igual la plataforma o la temporada), se cambia cuando se quiera y las notas de los demás "
        "influyen un poco en las recomendaciones. «Abandonar» (Perfil → Resumen → Juegos) es una nota privada para uno mismo: es reversible, no se "
        "anuncia, no cambia los totales ni los logros y, si se vuelve a jugar, se reanuda solo.",
    ),
    Topic(
        "temporadas", "Temporadas", ("temporada", "temporadas", "ano", "enero", "cerrada", "historial", "total"),
        "preguntas-frecuentes.md",
        "Una temporada es un año natural. El 1 de enero empieza una nueva: las cifras, los rankings y los logros de temporada vuelven a cero, "
        "mientras que el historial y las temporadas anteriores se conservan y se consultan con las pastillas de temporada (y «Total» para todo el "
        "historial). Las temporadas cerradas quedan congeladas: no se pueden añadir ni cambiar sesiones ni completar juegos en ellas (solo un "
        "administrador).",
    ),
    Topic(
        "dias_y_rachas", "Días jugados y rachas", ("racha", "rachas", "dias", "dia", "seguidos", "10 minutos", "diez minutos"),
        "perfil.md",
        "Un día cuenta como jugado si se hizo una sesión de 10 minutos o más (las más cortas no cuentan para días ni rachas, aunque sus horas sí suman). "
        "La racha son los días seguidos jugando; la racha actual solo aparece en la temporada en curso y en el total, y la mejor racha es la más larga. "
        "Cada día a las 05:00 se anuncian al grupo las rachas perdidas del día anterior.",
    ),
    Topic(
        "logros", "Logros", ("logro", "logros", "desbloquear", "secreto", "secretos", "oculto", "especial", "lifetime", "progreso", "aura"),
        "logros.md",
        "Los logros se desbloquean solos al jugar y se anuncian al grupo. Los de temporada se consiguen una vez al año y cuentan solo lo jugado en esa "
        "temporada; los lifetime cuentan todo el historial y se consiguen una sola vez. En Menú → Logros, los que aún no se tienen aparecen atenuados y "
        "solo con el nombre: averiguar de qué van es parte del juego, así que no se explica cómo conseguirlos. Los que se acumulan (horas, días, juegos, "
        "completados, racha) muestran una barra de progreso. Los ocultos no enseñan nada hasta conseguirlos y, cuando alguien desbloquea uno, al grupo "
        "solo llega quién lo ha sacado («<nombre> ha desbloqueado un logro oculto»), no cuál es. Los especiales brillan con un aura plateada, dorada o morada según su dificultad. Un grupo de "
        "logros depende de cuándo y a qué se juega (tormenta, luna llena, cumpleaños…) y algunos necesitan la ciudad y la fecha de nacimiento en Ajustes. "
        "Los logros nuevos cuentan desde la temporada 2027 (no son retroactivos). Se reevalúan al parar un timer o cambiar sesiones; si falta alguno, un "
        "administrador puede recalcularlos.",
    ),
    Topic(
        "perfil_ajustes", "Perfil y ajustes", ("perfil", "ajustes", "foto", "ciudad", "nacimiento", "datos", "exportar", "descargar", "cifras", "biblioteca"),
        "perfil.md",
        "Mi perfil tiene Resumen (horas, días, juegos, completados, rachas y logros por temporada, más jugados, retos y la lista de juegos con sus botones), "
        "En la página de otro jugador, «Tu biblioteca y la de ese jugador» (juegos de los dos, solo tuyos y solo suyos), y en la página de un juego, tu ritmo frente al grupo y a HowLongToBeat y, si es de una saga, las entregas en orden con lo que tienes de cada una. Cada jugador puede apuntar el precio de sus juegos por plataforma (solo lo ve él; del grupo solo se enseña el coste medio por hora de un juego cuando al menos 3 jugadores lo han apuntado, nunca por jugador). Mis juegos (toda la biblioteca con filtros por estado: en curso, pausado, pendiente, completado, abandonado; una tarjeta «¿Qué juego sigo?» con los casi terminados, los olvidados y los cortos; y «Puntuar al azar») y Ajustes. En Ajustes: los datos propios (nombre, usuario, email, Telegram ID, "
        "ciudad y fecha de nacimiento; estas dos solo sirven para algunos logros secretos y las ven solo uno mismo y los administradores), la contraseña, las "
        "notificaciones y «Descargar mis datos», un .json con las sesiones, la biblioteca, las notas, la lista de deseados y los logros. La foto se cambia "
        "con «Cambiar foto» (PNG o JPG).",
    ),
    Topic(
        "grupo", "El grupo: jugadores, actividad, juegos y calendario", ("grupo", "jugadores", "actividad", "jugando", "ahora", "afinidad", "catalogo", "calendario", "lanzamiento", "juegos"),
        "grupo.md",
        "Principal y Explorar son del grupo entero: se ve lo que hacen los demás (nunca su email, Telegram ni ajustes). La barra superior muestra quién "
        "juega ahora (un timer de más de 6 horas se atenúa como «¿Un timer olvidado?»). Actividad es el muro del grupo (sesiones, juegos empezados y "
        "completados, notas y logros). Jugadores lista a los miembros con sus cifras, y en la página de otro jugador aparece la afinidad con uno mismo: "
        "juegos en común (50 %), notas parecidas (30 %) y tiempo en los mismos géneros (20 %); con menos de 3 juegos en común dice que hay pocos datos. "
        "Juegos es el catálogo compartido (buscar, ordenar, filtrar, añadir desde RAWG) y la página de cada juego tiene portada, géneros, el tiempo medio para "
        "completarlo (de HowLongToBeat), las cifras del grupo, la nota propia y quién lo tiene. Si Steam o RAWG lo conocen, bajo el título salen la nota de Metacritic, "
        "la clasificación por edades y la web oficial, y una tarjeta plegada «Multimedia» con la descripción en español, "
        "el tráiler (se carga al pulsarlo) y capturas; los juegos que ninguno conoce, como muchos de Nintendo, no la tienen. Calendario pone en un mes todos los juegos con fecha de "
        "lanzamiento.",
    ),
    Topic(
        "deseados", "Lista de deseados y lanzamientos", ("deseado", "deseados", "wishlist", "lanzamiento", "estreno", "salir", "proximos"),
        "descubrir.md",
        "Menú → Deseados es la lista de juegos que se quieren jugar, también los que aún no han salido, en dos mitades: Próximos lanzamientos (con cuenta "
        "atrás) y Quiero jugar (ya lanzados). Cada tarjeta dice qué otros jugadores quieren el mismo juego. Se añade con «Añadir juego» o con «Añadir a mi "
        "lista» en la página de un juego, y un juego sale de la lista solo cuando se empieza a jugar. Cada día se consulta la fecha de salida y el día antes de "
        "un lanzamiento el grupo recibe un aviso con quién lo espera.",
    ),
    Topic(
        "recomendados", "Recomendados", ("recomendado", "recomendados", "recomendacion", "recomendaciones", "sugerencia"),
        "descubrir.md",
        "Menú → Recomendados propone 12 juegos que tienen otros jugadores y uno nunca ha jugado. Se escogen al azar con más probabilidad para los que tienen "
        "más jugadores, completados y horas, los que encajan con los géneros que más se juegan y los mejor puntuados; cada visita u «Otras recomendaciones» "
        "puede dar unos distintos. Al completar un juego, el aviso al grupo también recomienda otro del mismo género.",
    ),
    Topic(
        "retos", "Retos", ("reto", "retos", "juego del mes", "tematico", "personal", "deuda", "genero"),
        "descubrir.md",
        "Menú → Retos reúne objetivos con fecha de inicio y fin. Del grupo (los lanza un administrador): Juego del mes (un juego, un mes, unas horas mínimas por "
        "jugador y un total entre todos) y Temático (una etiqueta de juegos, un mes, y jugar unas horas o completar un juego). Se puede dejar de participar y "
        "volver mientras no termine. Personales (los lanza cada jugador con «Nuevo reto»; sin avisos): Probar un género (jugar unas horas, 2 por defecto, o "
        "completar uno, en una semana, un mes o tres; solo cuentan juegos de ese género que no estuvieran ya en la biblioteca) y Bajar la deuda (un objetivo "
        "sobre la deuda, que es lo que falta para terminar los juegos empezados, en porcentaje o en número de juegos), Racha (días seguidos o distintos jugando), Sesiones largas (un número de sesiones de al menos X minutos), Variar de género (varios géneros distintos con unas horas en cada uno) y Cumplir deseados (empezar o completar juegos que ya estaban en la lista de deseados al lanzar el reto). También hay duelos: un jugador reta a otro a jugar más horas (en total o a un juego); empieza al lanzarlo, el retado puede rechazarlo durante 48 horas y gana quien más juegue (si empatan, los dos). Un reto del grupo puede ser además una competición, con medallas, o voluntario (hay que apuntarse con «Apuntarme»). Cualquier jugador puede proponer al grupo un juego del mes o un temático "
    "(«Proponer al grupo», hasta 3 a la vez): un administrador lo aprueba o lo rechaza con una nota, y el jugador ve el estado en «Tus propuestas». Algunos retos del grupo se lanzan solos cada mes (programados por "
    "un administrador). Avisos de retos: lo que te afecta (te retan a un duelo, te rechazan uno, contestan una propuesta tuya y cómo terminan tus retos, un mensaje al día) llega "
    "solo a ti por Telegram o push, según elijas en tu perfil; el recordatorio de «te quedan 2 días» viene desactivado hasta que lo actives; al grupo solo llegan los retos del grupo, nunca los personales ni los duelos. "
    "Cada reto dice al jugador cómo va "
        "(cumplido, va bien, por detrás del ritmo o, en los últimos días, lo que le falta; solo dentro de la app) y el Inicio tiene una tarjeta Mis "
        "retos con los que están en marcha. Los retos terminados quedan en Perfil → "
        "Resumen → Retos.",
    ),
    Topic(
        "resumen", "Resumen e historia (Wrapped)", ("resumen", "wrapped", "historia", "story", "mensual", "anual", "compartir"),
        "resumen.md",
        "Menú → Resumen es el «Wrapped» de un mes o una temporada, para uno mismo (pestaña Tú) y para el grupo (pestaña El grupo): horas frente al periodo "
        "anterior, puesto, sesiones, mejor racha, juego estrella, mejor día, compañero habitual, logro más raro, clasificación y juegos más jugados. Solo se "
        "pueden elegir meses y temporadas ya terminados; la temporada en curso está bloqueada hasta que un administrador la desbloquea o se anuncia (diciembre o "
        "enero). «Ver mi historia» lo convierte en pantallas como el resumen del año de una app de música, y cada pantalla se puede compartir como imagen. "
        "Del 1 al 5 de cada mes la app ofrece el resumen del mes que acaba de terminar.",
    ),
    Topic(
        "notificaciones", "Notificaciones, Telegram y avisos", ("notificacion", "notificaciones", "aviso", "avisos", "telegram", "push", "bot", "activate", "menu", "semanal"),
        "notificaciones.md",
        "Hay dos canales: Telegram (un grupo y un bot) y las notificaciones push del móvil o del navegador. Al grupo se avisa de logros (los secretos sin "
        "detalle), juegos completados o empezados, cambios en los rankings, rachas perdidas, los lanzamientos deseados (el día antes o un resumen cada domingo, según el administrador), el resumen y los retos. En "
        "privado: el resumen semanal (si el administrador lo activa), el timer olvidado, el juego deseado que sale hoy y los logros secretos propios. "
        "La campana de la barra superior abre Avisos, la bandeja de la app con lo dicho al grupo y a ti (se borra con la × o con Vaciar todo). Para vincular Telegram: tener un @usuario "
        "de Telegram, que un administrador ponga el mismo usuario en la app y escribir /activate en el grupo. El bot (/menu) consulta estadísticas, rankings y "
        "recomendados, y es de solo lectura. Push: instalar la PWA (en iPhone es obligatorio) y aceptar el permiso; en la tarjeta de dispositivos se elige "
        "cuáles reciben también los avisos del grupo. Qué se recibe y por qué canal se elige en Perfil → Ajustes → Notificaciones.",
    ),
    Topic(
        "privacidad", "Quién ve qué", ("privacidad", "ver", "datos", "privado", "email", "ocultar"),
        "preguntas-frecuentes.md",
        "El grupo ve las horas, juegos, notas, logros de cada jugador y si está jugando (esto último se puede ocultar). Nunca ve el email, el Telegram ni "
        "los ajustes de otro. La ciudad y la fecha de nacimiento solo las ven el propio jugador y los administradores. Cada jugador puede llevarse sus datos "
        "en un .json desde Perfil → Ajustes.",
    ),
    Topic(
        "chat", "Este asistente (el chat)", ("chat", "asistente", "bot", "preguntar", "conversacion", "limite"),
        "descubrir.md",
        "El botón redondo de abajo a la derecha abre este asistente, que responde solo sobre videojuegos y los datos del grupo. Ve lo mismo que ve el jugador "
        "que pregunta, no guarda las conversaciones (al recargar o cerrar sesión se empieza de cero; el botón ↺ también empieza una nueva) y propone tres "
        "preguntas al azar al empezar. Hay límites de preguntas por minuto, hora y día para cada jugador y para todo el grupo, que ajusta el administrador: "
        "la herramienta de límites dice cuáles son y cuántas preguntas quedan.",
    ),
)

STOP = {"como", "que", "para", "una", "uno", "los", "las", "del", "con", "por", "mis", "sus", "hay", "esta", "esto", "puedo", "funciona", "funcionan", "donde"}


def plain(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if not unicodedata.combining(c))


def index() -> list[dict]:
    """Every topic, for the model to choose from."""
    return [{"topic": t.id, "title": t.title} for t in TOPICS]


def find(query: str, limit: int = 2) -> list[Topic]:
    """The topics that best match the words of `query` (their id, title and keywords), best first; none if nothing does."""
    words = [w for w in plain(query).replace("¿", " ").replace("?", " ").split() if len(w) >= 3 and w not in STOP]
    scored = []
    for position, topic in enumerate(TOPICS):
        haystack = (plain(topic.id.replace("_", " ")), plain(topic.title), *topic.keywords)
        score = sum(1 for word in words for part in haystack if word in part or (len(part) >= 4 and part in word))
        if score:
            scored.append((-score, position, topic))
    return [topic for _, _, topic in sorted(scored)[:limit]]
