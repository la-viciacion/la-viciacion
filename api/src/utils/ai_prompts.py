"""The AI's instructions for each notice, and the registry of the places that use the AI.

The text written here is only the default: the admin panel can override any prompt (setting
`ai.prompt.<id>`, see utils/settings.py), and the override wins until it is restored. A prompt that
was never edited follows this file, so improving it here reaches everybody who did not change it.
"""
from dataclasses import dataclass

NEW_GAME_PROMPT = """
Tu función es crear una frase divertida, partiendo del mensaje proporcionado.
Este mensaje indica que alguien ha empezado a jugar a un nuevo juego.

No puedes hacer referencia a logros a menos que explícitamente se indique que se ha obtenido
algún logro.

El mensaje debe estar preparado para poder ser interpretado en formato Markdown.
Debes incluir siempre el nombre del usuario.
Debes incluir siempre el nombre del juego.
Debes incluir siempre, si lo hay, el enlace proporcionado, manteniendo el formato del mensaje original ([Texto](enlace)).
Debes incluir siempre la cantidad de juegos empezados indicado en el mensaje original.
"""

COMPLETED_GAME_PROMPT = """
Tu función es crear una frase divertida, partiendo del mensaje proporcionado.
Este mensaje indica que alguien ha completado un juego.

El mensaje se envía al grupo, no al usuario: habla de él siempre en tercera persona (por ejemplo, "Toni ha
completado..."), sin dirigirte a él con "tú", "has" ni "tu".

No puedes hacer referencia a logros a menos que explícitamente se indique que se ha obtenido
algún logro.

El mensaje debe estar preparado para poder ser interpretado en formato Markdown.
Debes incluir siempre el nombre del usuario.
Debes incluir siempre el nombre del juego.
Debes incluir siempre la cantidad de juegos completados indicado en el mensaje original.
Debes incluir siempre el tiempo que le ha costado al usuario completar el juego (el que aparece justo después del
nombre del juego, tras la palabra "en"), tal como está escrito en el mensaje original (por ejemplo, 12h30m).
Si el mensaje original indica la media de tiempo, debes incluirla también, y puedes compararla con el tiempo del
usuario (más rápido, más lento, parecido). Esta media no es la media del usuario, sino la que se suele tardar en
completar ese juego. Si el mensaje no indica la media, no la menciones.
No te inventes ninguna cifra: usa solo las del mensaje original.
"""

NEW_GAME_RECOMMENDATION = """
Al final del mensaje, añade una frase corta y divertida sugiriendo que el usuario pruebe el juego que se indica
a continuación, hablando de él en tercera persona (el mensaje va al grupo) y diciendo que lo tiene o lo ha
jugado la persona indicada. Debes incluir siempre el nombre del juego y el de esa persona.
"""

RANKING_USER_PROMPT = """
Tu función es crear una frase divertida basándote
en la clasificación proporcionada por el usuario, teniendo en cuenta que la temática debe ser de videojuegos.

En esta clasificación habrá una lista de usuarios, indicando junto a su nombre si ha habido algún
cambio de posición. En ese caso, debes crear la frase únicamente teniendo en cuenta los usuarios
que han sufrido algún cambio.

Debes empezar el mensaje con '📣 Actualización del ránking de horas 📣', seguido de un salto de linea,
a continuación debes añadir tu frase, y debes incluir al final del mensaje
la clasificación original sin modificar en absoluto.
"""

RANKING_GAMES_PROMPT = """
Tu función es crear una frase divertida basándote
en la clasificación proporcionada por el usuario, teniendo en cuenta que la temática debe ser de videojuegos.

En esta clasificación habrá una lista de juegos, indicando junto a su nombre si ha habido algún
cambio de posición. En ese caso, debes crear la frase únicamente teniendo en cuenta los juegos
que han sufrido algún cambio. Si conoces alguna broma relacionada con algunos de los juegos implicados, puedes incluirla.

Debes empezar el mensaje con '📣 Actualización del ránking de juegos 📣', seguido de un salto de linea,
a continuación debes añadir tu frase, y debes incluir al final del mensaje
la clasificación original sin modificar en absoluto.
"""

WISHLIST_RELEASE_PROMPT = """
Tu función es crear una frase divertida, partiendo del mensaje proporcionado.
Este mensaje avisa al grupo de que mañana sale a la venta un juego (o varios) que alguien tiene en su
lista de deseados.

No puedes hacer referencia a logros ni a horas jugadas: solo se trata de un estreno.

El mensaje debe estar preparado para poder ser interpretado en formato Markdown.
Debes incluir siempre el nombre de cada juego, tal como aparece en el mensaje original.
Debes incluir siempre el nombre de todas las personas que lo esperan, y dejar claro que es mañana cuando sale.
Si hay varios juegos, menciónalos todos, sin dejarte ninguno.
Si conoces alguna broma relacionada con alguno de los juegos, puedes incluirla.
"""


@dataclass(frozen=True)
class Use:
    """A place where the AI can write a notice (or a piece of one)."""

    label: str
    help: str
    default: str  # the prompt until the panel changes it
    switchable: bool = True  # has its own on/off switch (a fragment does not: it follows the notice it belongs to)


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
        "Se añade a las instrucciones anteriores cuando hay otro juego que recomendar (sin interruptor propio).",
        NEW_GAME_RECOMMENDATION,
        switchable=False,
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
}
