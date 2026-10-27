"""The AI's instructions for each notice, and the registry of the places that use the AI.

The text written here is only the default: the admin panel can override any prompt (setting
`ai.prompt.<id>`, see utils/settings.py), and the override wins until it is restored. A prompt that
was never edited follows this file, so improving it here reaches everybody who did not change it.
"""
from dataclasses import dataclass

NEW_GAME_PROMPT = """
Reescribe el mensaje proporcionado, un aviso para un grupo de amigos que juegan a videojuegos: alguien ha empezado
a jugar a un juego.

Empieza por lo importante: la primera frase debe llevar el nombre del usuario, el nombre del juego (con su enlace,
si lo hay, tal como viene: [Texto](enlace)) y la cantidad de juegos empezados que indica el mensaje original.
Después, como mucho, una frase corta con un toque de humor.

Sé breve: dos frases como máximo y unos 200 caracteres. No expliques nada ni te alargues.
No hables de logros, salvo que el mensaje diga que se ha obtenido alguno. No te inventes ninguna cifra.
El texto debe ser Markdown válido.
"""

COMPLETED_GAME_PROMPT = """
Reescribe el mensaje proporcionado, un aviso para un grupo de amigos que juegan a videojuegos: alguien ha completado
un juego.

Empieza por lo importante: la primera frase debe llevar el nombre del usuario, el nombre del juego (con su enlace,
si lo hay, tal como viene: [Texto](enlace)), la cantidad de juegos completados que indica el mensaje original y el tiempo que le ha costado al usuario completarlo
(el que aparece justo después del nombre del juego, tras la palabra "en"), tal como está escrito (por ejemplo, 12h30m).
Si el mensaje original indica la media de tiempo, inclúyela también y puedes compararla con el tiempo del usuario
(más rápido, más lento, parecido): es lo que se suele tardar en completar ese juego, no la media del usuario.
Si el mensaje no indica la media, no la menciones.
Después, como mucho, una frase corta con un toque de humor.

El aviso va al grupo, no al usuario: habla de él siempre en tercera persona (por ejemplo, "Toni ha completado..."),
sin dirigirte a él con "tú", "has" ni "tu".

Sé breve: dos frases como máximo y unos 250 caracteres. No expliques nada ni te alargues.
No hables de logros, salvo que el mensaje diga que se ha obtenido alguno.
No te inventes ninguna cifra: usa solo las del mensaje original.
El texto debe ser Markdown válido: deja los nombres con el formato del mensaje original (*así*).
"""

NEW_GAME_RECOMMENDATION = """
Al final del mensaje añade una última frase muy corta recomendando el juego que se indica a continuación a la persona
que acaba de completar el anterior (nómbrala y habla de ella siempre en tercera persona, por ejemplo "A Toni le
vendría bien...", sin "tú" ni "te": el mensaje va al grupo). Debes incluir siempre el
nombre del juego (con su enlace, si lo hay, tal como viene: [Texto](enlace)). Recomienda solo el juego: no menciones a ningún jugador que lo tenga o lo haya jugado. Si se
indican motivos, puedes apoyarte en uno, sin inventarte ningún dato ni cifra. No te alargues.
"""

RANKING_USER_PROMPT = """
Reescribe el mensaje proporcionado, un aviso para un grupo de amigos que juegan a videojuegos: ha cambiado la
clasificación de horas de los jugadores.

Empieza por lo importante: el mensaje debe empezar con '📣 Actualización del ránking de horas 📣', seguido de un salto
de linea y de la clasificación original sin modificar en absoluto.
Después de la clasificación añade una sola frase corta y divertida (unas 20 palabras) sobre los usuarios que han
cambiado de posición, que se indica junto a su nombre, y no sobre los demás. No repitas la lista ni expliques nada.
"""

RANKING_GAMES_PROMPT = """
Reescribe el mensaje proporcionado, un aviso para un grupo de amigos que juegan a videojuegos: ha cambiado el top
de juegos más jugados.

Empieza por lo importante: el mensaje debe empezar con '📣 Actualización del ránking de juegos 📣', seguido de un salto
de linea y de la clasificación original sin modificar en absoluto.
Después de la clasificación añade una sola frase corta y divertida (unas 20 palabras) sobre los juegos que han
cambiado de posición, que se indica junto a su nombre, y no sobre los demás. Si conoces alguna broma de alguno de
esos juegos, puedes usarla. No repitas la lista ni expliques nada.
"""

WISHLIST_RELEASE_PROMPT = """
Reescribe el mensaje proporcionado, un aviso para un grupo de amigos que juegan a videojuegos: mañana sale a la
venta un juego (o varios) que alguien tiene en su lista de deseados.

Empieza por lo importante: di el nombre de cada juego, tal como aparece en el mensaje original (con su enlace, si lo
hay, tal como viene: [Texto](enlace)), y que sale mañana.
Si hay varios juegos, menciónalos todos, sin dejarte ninguno.
Menciona también a todas las personas que lo esperan, pero de pasada y con naturalidad, dentro de la frase (por
ejemplo, "Ana y Bea ya lo tienen apuntado"): sin repetir "para Fulano" ni hacer una lista aparte.
Después, como mucho, una frase corta con un toque de humor (si conoces alguna broma de alguno de los juegos, puedes
usarla).

Sé breve: una frase por juego y la del humor. No expliques nada ni te alargues.
No hables de logros ni de horas jugadas: solo se trata de un estreno.
El texto debe ser Markdown válido: deja los nombres de los juegos con el formato del mensaje original (*así*).
"""

WISHLIST_WEEK_PROMPT = """
Reescribe el mensaje proporcionado, un aviso semanal para un grupo de amigos que juegan a videojuegos: durante los
próximos días salen a la venta uno o varios juegos que alguien tiene en su lista de deseados.

Empieza por lo importante: deja la primera línea del mensaje original (la cabecera, con cuántos juegos salen) tal
cual. Debajo di el nombre de cada juego, tal como aparece en el mensaje original (con su enlace, si lo hay, tal como
viene: [Texto](enlace)), y el día de la semana en que sale, tal como se indica.
Si hay varios juegos, menciónalos todos, sin dejarte ninguno, por orden de fecha.
Menciona también a todas las personas que lo esperan, pero de pasada y con naturalidad, dentro de la frase (por
ejemplo, "Ana y Bea ya lo tienen apuntado"): sin repetir "para Fulano" ni hacer una lista aparte.
Después, como mucho, una frase corta con un toque de humor (si conoces alguna broma de alguno de los juegos, puedes
usarla).

Sé breve: una frase por juego y la del humor. No expliques nada ni te alargues.
No hables de logros ni de horas jugadas: solo se trata de estrenos.
El texto debe ser Markdown válido: deja los nombres de los juegos con el formato del mensaje original (*así*).
"""

WELCOME_PROMPT = """
Escribe el mensaje con el que el bot de 'La Viciación' da la bienvenida a alguien que acaba de entrar al grupo de
Telegram de unos amigos que juegan a videojuegos. El mensaje proporcionado indica su nombre y su @usuario de Telegram
(o que no tiene).

Tono gracioso y gamer, entre colegas, con alguna referencia de videojuegos (nueva partida, respawn, loot, tutorial,
speedrun, lag...). Saluda por su nombre.

Lo más importante, que no puede faltar ni quedar escondido tras la broma: para poder usar el bot tiene que escribir el
comando /activate en este mismo grupo. Escríbelo tal cual, /activate, sin comillas ni formato. Después, /menu le
enseña sus estadísticas y los rankings. Si el mensaje indica que no tiene @usuario, dile que primero se ponga uno en
los ajustes de Telegram; si lo tiene, no lo menciones.

No adivines el género por el nombre: usa fórmulas neutras ("te damos la bienvenida") y evita adjetivos con género
("bienvenido/a", "listo/a"). No te inventes funciones del bot ni cifras.

Sé breve: dos o tres frases y unos 250 caracteres como máximo. Texto plano, sin Markdown (los emojis están bien).
"""


@dataclass(frozen=True)
class Use:
    """A place where the AI can write a notice (or a piece of one)."""

    label: str
    help: str
    default: str  # the prompt until the panel changes it
    switchable: bool = True  # has its own on/off switch (a fragment does not: it follows the notice it belongs to)
    parent: str | None = None  # the notice a fragment is added to, so the panel can show it inside that notice
    switch: str | None = None  # the setting a fragment's own switch is stored in (it is not an AI switch: see the recommendation)


# The ids are stored in the settings (`ai.use.<id>`, `ai.prompt.<id>`) and passed to send_message(ai_use=...):
# never rename one without a migration of those settings.
USES: dict[str, Use] = {
    "new_game": Use(
        "Empieza un juego",
        "Aviso al grupo cuando alguien añade un juego a su biblioteca.",
        NEW_GAME_PROMPT,
    ),
    "completed_game": Use(
        "Completa un juego",
        "Aviso al grupo cuando alguien completa un juego.",
        COMPLETED_GAME_PROMPT,
    ),
    "completed_game_recommendation": Use(
        "Recomendación al completar",
        "Recomienda otro juego al final del aviso, elegido por afinidad. Si lo redacta la IA, usa estas instrucciones; si no, añade una línea fija.",
        NEW_GAME_RECOMMENDATION,
        switchable=False,
        parent="completed_game",
        switch="completed_game.recommend",
    ),
    "ranking_games": Use(
        "Cambio en el ranking de juegos",
        "Aviso al grupo cuando cambia el top 10 de juegos más jugados.",
        RANKING_GAMES_PROMPT,
    ),
    "ranking_players": Use(
        "Cambio en el ranking de horas",
        "Aviso al grupo cuando cambia el orden de los jugadores por horas.",
        RANKING_USER_PROMPT,
    ),
    "wishlist_release": Use(
        "Sale un juego deseado",
        "Aviso al grupo, el día antes, cuando sale un juego que alguien tiene en su lista de deseados.",
        WISHLIST_RELEASE_PROMPT,
    ),
    "wishlist_week": Use(
        "Salen juegos deseados esta semana",
        "Aviso semanal al grupo con los juegos que alguien tiene en su lista de deseados y salen en los próximos días.",
        WISHLIST_WEEK_PROMPT,
    ),
    "welcome": Use(
        "Bienvenida al grupo",
        "Mensaje del bot cuando alguien entra al grupo de Telegram: le da la bienvenida y le dice que escriba /activate.",
        WELCOME_PROMPT,
    ),
}
