from enum import Enum

# An achievement whose key ends like this has no season limit: it counts the whole history of a player and is
# earned once, not once a season (see crud/achievements.py). Nothing else says so: the name is the rule.
LIFETIME_SUFFIX = "_LIFETIME"


def is_lifetime(key: str) -> bool:
    return str(key).endswith(LIFETIME_SUFFIX)


# The season an achievement starts to count in when the code creates it: "since", which every definition has (a
# test fails if one does not). The first ones say 2023, the first season of the app, and count the history since the
# start; every one added from now on says 2027, so it is not retroactive (tests/test_achievement_checks.py pins the
# list of the 2023 ones). An admin can change it afterwards: the database is the truth.
def first_season(achievement) -> int:
    return achievement.value["since"]


class AchievementsElems(Enum):
    # Format -> KEY = {"since": season it starts to count in, "special": level 1-3 (optional), "secret": True (optional), "title": "", "description": "how it is earned, as the player reads it", "message": "the announcement"}
    # "special" (1 silver, 2 gold, 3 purple) and "secret" are how the achievement is created; an admin can change them afterwards.
    # Time day
    PLAYED_4_HOURS_DAY = {
        "since": 2023,
        "title": "Media Jornada laboral",
        "description": "Juega 4 horas en un mismo día.",
        "message": "*"
        + "{}"
        + "*"
        + " está tanteando el terreno para ver cómo va eso de jugar durante un ratito al día (4 horas).",
    }
    PLAYED_8_HOURS_DAY = {
        "since": 2023,
        "title": "Una jornada laboral",
        "description": "Juega 8 horas en un mismo día.",
        "message": "Las jornadas laborales de 8 horas deberían desaparecer, pero no las de jugar. "
        + "*"
        + "{}"
        + "*"
        + " acaba de invertir el tiempo máximo legal para una jornada de trabajo.",
    }
    PLAYED_12_HOURS_DAY = {
        "since": 2023,
        "special": 1,
        "secret": True,
        "title": "Media jornada, 12 horas",
        "description": "Juega 12 horas en un mismo día.",
        "message": "Como decía 'El Rancio', media jornada son 12 horas, y ese es el tiempo que ha invertido "
        + "*"
        + "{}"
        + "* en un solo día. Mariscos Recio estaría orgulloso.",
    }
    PLAYED_16_HOURS_DAY = {
        "since": 2023,
        "special": 2,
        "title": "No paro ni a cagar",
        "description": "Juega 16 horas en un mismo día.",
        "message": "De las 24h del día, 8 se deberían dedicar a dormir, y las otras 16 a hacer cosas. "
        + "*"
        + "{}"
        + "* ha decidido invertirlas a jugar. Lo de comer y hacer otras necesidades como asearse ya para otro día.",
    }

    # Time on game
    PLAYED_8_HOURS_GAME_DAY = {
        "since": 2023,
        "title": "Mi trabajo es jugar",
        "description": "Juega 8 horas o más al mismo juego en un mismo día.",
        "message": "Lo de estar 8 horas trabajando no suele gustar, pero jugando ya es otra cosa. "
        + "*"
        + "{}"
        + "* acaba de jugar 8 horas (o más) a _"
        + "{}"
        + "_ en un mismo día.",
    }
    PLAYED_100_HOURS_GAME = {
        "since": 2023,
        "special": 1,
        "title": "Cualquiera diría que le gusta ese juego",
        "description": "Llega a 100 horas jugadas a un mismo juego en la temporada.",
        "message": "Todo apunta a que a *"
        + "{}"
        + "* le ha enganchado _"
        + "{}"
        + "_, porque acaba de rebasar la barrera de las 100 horas invertidas en él.",
    }
    PLAYED_500_HOURS_GAME = {
        "since": 2023,
        "special": 2,
        "title": "Una buena inversión",
        "description": "Llega a 500 horas jugadas a un mismo juego en la temporada.",
        "message": "Si he pagado por un juego, es para jugarlo."
        + " Eso es lo que habrá pensado *"
        + "{}"
        + "*, que acaba de pasar las 500 horas jugadas a _"
        + "{}"
        + "_.",
    }
    PLAYED_1000_HOURS_GAME = {
        "since": 2023,
        "special": 3,
        "title": "¿Para qué diversificar?",
        "description": "Llega a 1000 horas jugadas a un mismo juego en la temporada.",
        "message": "A *"
        + "{}"
        + "* lo único que le importa en esta vida es _"
        + "{}"
        + "_. 1000 horas (y seguro que subiendo). Mejor no preguntar.",
    }

    # Total time
    PLAYED_100_HOURS = {
        "since": 2023,
        "title": "100 horas",
        "description": "Acumula 100 horas de juego en la temporada.",
        "message": "{} ha acumulado un total de 100 horas de juego en lo que va de año.",
    }
    PLAYED_200_HOURS = {
        "since": 2023,
        "title": "200 horas",
        "description": "Acumula 200 horas de juego en la temporada.",
        "message": "{} ha acumulado un total de 200 horas de juego en lo que va de año.",
    }
    PLAYED_500_HOURS = {
        "since": 2023,
        "special": 1,
        "title": "500 horas",
        "description": "Acumula 500 horas de juego en la temporada.",
        "message": "{} ha acumulado un total de 500 horas de juego en lo que va de año.",
    }
    PLAYED_1000_HOURS = {
        "since": 2023,
        "special": 2,
        "title": "1000 horas",
        "description": "Acumula 1000 horas de juego en la temporada.",
        "message": "{} ha acumulado un total de 1000 horas de juego en lo que va de año.",
    }

    # Session time
    PLAYED_LESS_5_MIN_SESSION = {
        "since": 2023,
        "title": "Lo he abierto sin querer",
        "description": "Haz una sesión de 5 minutos o menos.",
        "message": "Al parecer a *"
        + "{}"
        + "* no le ha convencido _"
        + "{}"
        + "_, ya que ha hecho una ridícula sesión de juego de 5 minutos (o menos).",
    }
    PLAYED_4_HOURS_SESSION = {
        "since": 2023,
        "secret": True,
        "title": "Sesión de 4 horas",
        "description": "Juega 4 horas seguidas o más en una sola sesión.",
        "message": "*{}"
        + "* acaba de jugar 4 horas seguidas (o más) a _"
        + "{}"
        + "_ en una sola sesión.",
    }
    PLAYED_8_HOURS_SESSION = {
        "since": 2023,
        "title": "Mi trabajo es jugar (sin parar)",
        "description": "Juega 8 horas seguidas o más en una sola sesión.",
        "message": "8 horas haciendo lo mismo suele llegar a aburrir, siempre que no sea jugar. "
        + "*"
        + "{}"
        + "* acaba de cascarse 8 horas seguidas (o más) jugando a _"
        + "{}"
        + "_; cualquiera diría que le está gustando.",
    }

    # Games
    PLAYED_10_GAMES = {
        "since": 2023,
        "title": "10 juegos jugados",
        "description": "Juega a 10 juegos distintos en la temporada.",
        "message": "*{}* acaba de empezar su juego número 10.",
    }
    PLAYED_42_GAMES = {
        "since": 2023,
        "special": 1,
        "title": "La respuesta",
        "description": "Juega a 42 juegos distintos en la temporada.",
        "message": "*{}* ha jugado a la mágica cifra de 42 juegos."
        + " No sabemos si tendrá la respuesta al sentido de la vida, "
        + "al universo y todo lo demás, pero lo que seguro que tiene "
        + "es mucho tiempo libre.",
    }
    PLAYED_50_GAMES = {
        "since": 2023,
        "special": 1,
        "title": "50 juegos jugados",
        "description": "Juega a 50 juegos distintos en la temporada.",
        "message": "*{}* acaba de empezar su juego número 50.",
    }
    PLAYED_100_GAMES = {
        "since": 2023,
        "special": 2,
        "title": "100 juegos (jugados)",
        "description": "Juega a 100 juegos distintos en la temporada.",
        "message": "A 100 juegos acaba de jugar "
        + "*{}*. Estamos hablando de arrancar un nuevo"
        + " juego cada 3,65 días de media (si dejara de empezar juegos nuevos). Pensemos en ello.",
    }
    COMPLETED_1_GAME = {
        "since": 2023,
        "title": "Primer juego completado",
        "description": "Completa tu primer juego de la temporada.",
        "message": "*{}* acaba de completar su primer juego del año. Y esto no ha hecho más que empezar.",
    }
    COMPLETED_5_GAMES = {
        "since": 2023,
        "title": "5 juegos completados",
        "description": "Completa 5 juegos en la temporada.",
        "message": "*{}* acaba de completar su juego número 5. Esto ya va en serio.",
    }
    COMPLETED_10_GAMES = {
        "since": 2023,
        "title": "10 juegos completados",
        "description": "Completa 10 juegos en la temporada.",
        "message": "*{}* ya lleva 10 juegos completados. Se nota que sabe terminar lo que empieza (a diferencia de otros).",
    }
    COMPLETED_25_GAMES = {
        "since": 2023,
        "special": 1,
        "title": "25 juegos completados",
        "description": "Completa 25 juegos en la temporada.",
        "message": "*{}* ha completado 25 juegos. A este ritmo, el año se le queda corto.",
    }
    COMPLETED_42_GAMES = {
        "since": 2023,
        "special": 2,
        "secret": True,
        "title": "La respuesta (de verdad)",
        "description": "Completa 42 juegos en la temporada.",
        "message": "Si empezar 42 juegos ya es todo un logro, no hablemos de acabar 42. "
        + "Ha quedado patente que a "
        + "*{}*"
        + " la vida más allá de la puerta de casa no le importa lo más mínimo.",
    }
    COMPLETED_100_GAMES = {
        "since": 2023,
        "special": 3,
        "title": "100 juegos completados",
        "description": "Completa 100 juegos en la temporada.",
        "message": "*{}*"
        + " acaba de completar 100 juegos. No se me ocurre qué decir.",
    }
    PLAYED_5_GAMES_DAY = {
        "since": 2023,
        "title": "Indecisión",
        "description": "Juega a 5 juegos distintos o más en un mismo día.",
        "message": "Este. No, este. No, mejor este otro. AAAHHHRRRGGG, tengo demasiados juegos. "
        + "*{}*"
        + " no tiene ni idea de a qué jugar, y ya ha probado con 5 o más juegos en un solo día.",
    }
    PLAYED_10_GAMES_DAY = {
        "since": 2023,
        "special": 1,
        "secret": True,
        "title": "Indecisión x2",
        "description": "Juega a 10 juegos distintos o más en un mismo día.",
        "message": "AAAHHHRRRGGG, sigo sin saber a qué jugar. "
        + "*{}*"
        + " ha acumulado tantos juegos en su biblioteca que salta de uno "
        + "a otro como pollo sin cabeza, y ya ha probado con 10 o más juegos en un solo día.",
    }

    # Total days
    PLAYED_7_DAYS = {
        "since": 2023,
        "title": "7 días jugados",
        "description": "Juega en 7 días distintos de la temporada.",
        "message": "*{}* acumula un total de 7 días jugados en lo que va de año.",
    }
    PLAYED_15_DAYS = {
        "since": 2023,
        "title": "15 días jugados",
        "description": "Juega en 15 días distintos de la temporada.",
        "message": "*{}* acumula un total de 15 días jugados en lo que va de año.",
    }
    PLAYED_30_DAYS = {
        "since": 2023,
        "title": "30 días jugados",
        "description": "Juega en 30 días distintos de la temporada.",
        "message": "*{}* acumula un total de 30 días jugados en lo que va de año.",
    }
    PLAYED_60_DAYS = {
        "since": 2023,
        "title": "60 días jugados",
        "description": "Juega en 60 días distintos de la temporada.",
        "message": "*{}* acumula un total de 60 días jugados en lo que va de año.",
    }
    PLAYED_100_DAYS = {
        "since": 2023,
        "title": "100 días jugados",
        "description": "Juega en 100 días distintos de la temporada.",
        "message": "*{}* acumula un total de 100 días jugados en lo que va de año.",
    }
    PLAYED_200_DAYS = {
        "since": 2023,
        "special": 1,
        "secret": True,
        "title": "200 días jugados",
        "description": "Juega en 200 días distintos de la temporada.",
        "message": "*{}* acumula un total de 200 días jugados en lo que va de año.",
    }
    PLAYED_300_DAYS = {
        "since": 2023,
        "special": 2,
        "secret": True,
        "title": "300 días jugados",
        "description": "Juega en 300 días distintos de la temporada.",
        "message": "*{}* acumula un total de 300 días jugados en lo que va de año.",
    }
    PLAYED_365_DAYS = {
        "since": 2023,
        "special": 3,
        "secret": True,
        "title": "365 días jugados",
        "description": "Juega en 365 días distintos de la temporada.",
        "message": "*{}* acumula un total de 365 días jugados en lo que va de año.",
    }

    # Streaks
    STREAK_7_DAYS = {
        "since": 2023,
        "title": "Racha de 7 días",
        "description": "Juega 7 días seguidos, con al menos una sesión cada día.",
        "message": "Pues resulta que "
        + "*{}*"
        + " lleva 1 semana jugando todos los días. "
        + "Podríamos decir que tiene pocas cosas mejores que hacer.",
    }
    STREAK_15_DAYS = {
        "since": 2023,
        "title": "Racha de 15 días",
        "description": "Juega 15 días seguidos, con al menos una sesión cada día.",
        "message": "Ya son 15 los días que lleva "
        + "*{}*"
        + " sin faltar ni uno a la sesión de juego de rigor. "
        + "A este paso habrá que ir pensando en empezar a regarlo.",
    }
    STREAK_30_DAYS = {
        "since": 2023,
        "title": "Racha de 30 días",
        "description": "Juega 30 días seguidos, con al menos una sesión cada día.",
        "message": "Poco más que añadir. "
        + "*{}*"
        + " acumula una racha de 30 días con una sesión de juego como mínimo. "
        + "Lo mejor será ir llamando al psiquiátrico.",
    }
    STREAK_60_DAYS = {
        "since": 2023,
        "title": "Racha de 60 días",
        "description": "Juega 60 días seguidos, con al menos una sesión cada día.",
        "message": "*{}*" + " acumula una racha de 60 días.",
    }
    STREAK_100_DAYS = {
        "since": 2023,
        "special": 1,
        "title": "Racha de 100 días",
        "description": "Juega 100 días seguidos, con al menos una sesión cada día.",
        "message": "*{}*" + " acumula una racha de 100 días.",
    }
    STREAK_200_DAYS = {
        "since": 2023,
        "special": 1,
        "title": "Racha de 200 días",
        "description": "Juega 200 días seguidos, con al menos una sesión cada día.",
        "message": "*{}*" + " acumula una racha de 200 días.",
    }
    STREAK_300_DAYS = {
        "since": 2023,
        "special": 2,
        "title": "Racha de 300 días",
        "description": "Juega 300 días seguidos, con al menos una sesión cada día.",
        "message": "*{}*" + " acumula una racha de 300 días.",
    }
    STREAK_365_DAYS = {
        "since": 2023,
        "special": 3,
        "title": "Racha de 365 días",
        "description": "Juega 365 días seguidos, con al menos una sesión cada día.",
        "message": "*{}*" + " acumula una racha de 365 días.",
    }

    # Others
    COMPLETED_IN_A_DAY = {
        "since": 2023,
        "secret": True,
        "title": "Del tirón",
        "description": "Empieza y completa un juego en un solo día.",
        "message": "*{}* ha empezado y terminado _{}_ en un solo día. Sin dormir, sin pausas y sin remordimientos.",
    }

    RELEASE_DAY = {
        "since": 2023,
        "special": 1,
        "title": "Lo estaba esperando",
        "description": "Juega a un juego el mismo día de su lanzamiento.",
        "message": "*{}* ha jugado a _{}_ el mismo día de su lanzamiento. Ni un minuto de espera.",
    }

    ALL_TOGETHER = {
        "since": 2023,
        "title": "Todos a una",
        "description": "Juega al mismo juego, con el temporizador en marcha, a la vez que otros 2 jugadores o más.",
        "message": "*{}* están jugando a la vez a _{}_. Como en los viejos tiempos de las LAN party.",
    }

    PRODIGAL_SON = {
        "since": 2023,
        "title": "El hijo pródigo",
        "description": "Vuelve a jugar tras 30 días o más sin hacerlo.",
        "message": "*{}* vuelve a jugar tras 30 días (o más) sin tocar un mando. Se le echaba de menos, aunque algunos ni lo habían notado.",
    }

    RESCUE_LIFETIME = {
        "since": 2027,
        "special": 2,
        "title": "Rescate",
        "description": "Completa un juego que llevaba 90 días o más sin tocar.",
        "message": "*{}* ha rescatado _{}_ del olvido: llevaba 90 días (o más) sin tocarlo y por fin lo ha terminado.",
    }

    FINISHING_TOUCH_LIFETIME = {
        "since": 2027,
        "special": 3,
        "title": "Remate",
        "description": "Completa un juego tras 90 días o más olvidado, cuando ya llevabas más del 80 % de su duración media.",
        "message": "*{}* ha rematado _{}_ tras 90 días (o más) olvidado, cuando ya llevaba más de un 80 % del juego. A un paso de la meta y aun así tardó en volver.",
    }

    WORK_WEEK = {
        "since": 2023,
        "special": 1,
        "title": "Semana laboral",
        "description": "Juega 40 horas en una semana, de lunes a domingo.",
        "message": "*{}* acaba de completar una semana laboral entera de 40 horas jugando. Sin vacaciones ni convenio.",
    }

    SAVED_BY_THE_BELL = {
        "since": 2023,
        "special": 1,
        "secret": True,
        "title": "Salvado por la campana",
        "description": "Estar jugando justo cuando cambia el año.",
        "message": "*{}* estaba jugando a _{}_ justo cuando cambió el año. Mientras otros se atragantaban con las uvas, él seguía con el mando en la mano.",
    }

    # No season limit: they count the whole history of a player and are earned once (the key ends in _LIFETIME)
    PLAYED_1000_HOURS_GAME_LIFETIME = {
        "since": 2023,
        "special": 2,
        "title": "Una relación seria",
        "description": "Suma 1000 horas a un mismo juego entre todas las temporadas.",
        "message": "*{}* lleva 1000 horas en total jugando a _{}_, sumando todas las temporadas. Esto ya no es un juego, es una relación.",
    }
    PLAYED_100_DAYS_LIFETIME = {
        "since": 2023,
        "title": "100 días jugados (en total)",
        "description": "Suma 100 días jugados entre todas las temporadas.",
        "message": "*{}* suma 100 días jugados en total, contando todas las temporadas. La costumbre ya va cogiendo forma.",
    }
    PLAYED_200_DAYS_LIFETIME = {
        "since": 2023,
        "title": "200 días jugados (en total)",
        "description": "Suma 200 días jugados entre todas las temporadas.",
        "message": "*{}* suma 200 días jugados en total, contando todas las temporadas. La costumbre ya es ley.",
    }
    PLAYED_500_DAYS_LIFETIME = {
        "since": 2023,
        "title": "500 días jugados (en total)",
        "description": "Suma 500 días jugados entre todas las temporadas.",
        "message": "*{}* suma 500 días jugados en total, contando todas las temporadas. Más de un año y pico de partidas.",
    }
    PLAYED_1000_DAYS_LIFETIME = {
        "since": 2023,
        "special": 1,
        "title": "1000 días jugados (en total)",
        "description": "Suma 1000 días jugados entre todas las temporadas.",
        "message": "*{}* suma 1000 días jugados en total, contando todas las temporadas. Casi tres años de su vida, con el mando en la mano.",
    }
    PLAYED_2000_DAYS_LIFETIME = {
        "since": 2023,
        "special": 2,
        "title": "2000 días jugados (en total)",
        "description": "Suma 2000 días jugados entre todas las temporadas.",
        "message": "*{}* suma 2000 días jugados en total, contando todas las temporadas. Más de cinco años de partidas. Ya es patrimonio del grupo.",
    }
    PLAYED_5000_DAYS_LIFETIME = {
        "since": 2023,
        "special": 3,
        "title": "5000 días jugados (en total)",
        "description": "Suma 5000 días jugados entre todas las temporadas.",
        "message": "*{}* suma 5000 días jugados en total, contando todas las temporadas. Casi catorce años jugando. Que alguien le dé las llaves de la ciudad.",
    }
    PLAYED_500_HOURS_LIFETIME = {
        "since": 2023,
        "title": "500 horas (en total)",
        "description": "Suma 500 horas de juego entre todas las temporadas.",
        "message": "*{}* acumula 500 horas de juego en total, sumando todas las temporadas. Y las que le quedan.",
    }
    PLAYED_1000_HOURS_LIFETIME = {
        "since": 2023,
        "title": "1000 horas (en total)",
        "description": "Suma 1000 horas de juego entre todas las temporadas.",
        "message": "*{}* acumula 1000 horas de juego en total, sumando todas las temporadas. Son más de 41 días seguidos sin parar.",
    }
    PLAYED_2000_HOURS_LIFETIME = {
        "since": 2023,
        "special": 1,
        "title": "2000 horas (en total)",
        "description": "Suma 2000 horas de juego entre todas las temporadas.",
        "message": "*{}* acumula 2000 horas de juego en total, sumando todas las temporadas. Casi tres meses seguidos, sin dormir.",
    }
    PLAYED_5000_HOURS_LIFETIME = {
        "since": 2023,
        "special": 2,
        "title": "5000 horas (en total)",
        "description": "Suma 5000 horas de juego entre todas las temporadas.",
        "message": "*{}* acumula 5000 horas de juego en total, sumando todas las temporadas. Casi siete meses seguidos. Que descanse alguien.",
    }
    PLAYED_10000_HOURS_LIFETIME = {
        "since": 2023,
        "special": 3,
        "title": "10000 horas (en total)",
        "description": "Suma 10000 horas de juego entre todas las temporadas.",
        "message": "*{}* acumula 10000 horas de juego en total, sumando todas las temporadas. Dicen que con 10.000 horas se llega a maestro. De qué, aún está por ver.",
    }
    PLAYED_100_GAMES_LIFETIME = {
        "since": 2023,
        "title": "100 juegos jugados (en total)",
        "description": "Juega a 100 juegos distintos entre todas las temporadas.",
        "message": "*{}* ha jugado a 100 juegos distintos en total, contando todas las temporadas. Y eso que solo cuenta los distintos.",
    }
    PLAYED_200_GAMES_LIFETIME = {
        "since": 2023,
        "title": "200 juegos jugados (en total)",
        "description": "Juega a 200 juegos distintos entre todas las temporadas.",
        "message": "*{}* ha jugado a 200 juegos distintos en total, contando todas las temporadas. Una biblioteca que ya pide estantería nueva.",
    }
    PLAYED_500_GAMES_LIFETIME = {
        "since": 2023,
        "special": 1,
        "title": "500 juegos jugados (en total)",
        "description": "Juega a 500 juegos distintos entre todas las temporadas.",
        "message": "*{}* ha jugado a 500 juegos distintos en total, contando todas las temporadas. Esto ya no es una biblioteca, es un museo.",
    }
    PLAYED_1000_GAMES_LIFETIME = {
        "since": 2023,
        "special": 2,
        "title": "1000 juegos jugados (en total)",
        "description": "Juega a 1000 juegos distintos entre todas las temporadas.",
        "message": "*{}* ha jugado a 1000 juegos distintos en total, contando todas las temporadas. Mil juegos distintos. Que le hagan un monumento.",
    }
    COMPLETED_100_GAMES_LIFETIME = {
        "since": 2023,
        "title": "100 juegos completados (en total)",
        "description": "Completa 100 juegos distintos entre todas las temporadas.",
        "message": "*{}* ha completado 100 juegos distintos en total, sumando todas las temporadas. Terminar lo que se empieza, convertido en estilo de vida.",
    }
    COMPLETED_200_GAMES_LIFETIME = {
        "since": 2023,
        "title": "200 juegos completados (en total)",
        "description": "Completa 200 juegos distintos entre todas las temporadas.",
        "message": "*{}* ha completado 200 juegos distintos en total, sumando todas las temporadas. Dos centenares de créditos finales.",
    }
    COMPLETED_500_GAMES_LIFETIME = {
        "since": 2023,
        "special": 2,
        "title": "500 juegos completados (en total)",
        "description": "Completa 500 juegos distintos entre todas las temporadas.",
        "message": "*{}* ha completado 500 juegos distintos en total, sumando todas las temporadas. Medio millar de finales. Alguien tiene mucho que contar.",
    }
    COMPLETED_1000_GAMES_LIFETIME = {
        "since": 2023,
        "special": 3,
        "title": "1000 juegos completados (en total)",
        "description": "Completa 1000 juegos distintos entre todas las temporadas.",
        "message": "*{}* ha completado 1000 juegos distintos en total, sumando todas las temporadas. Mil juegos terminados. Ya no queda nada por ver.",
    }

    # About the challenges: one counts once it is over and the player met their part (see docs/desarrollo/features.md). The
    # tiers count the group's challenges only: a personal one is chosen by the player, so it could be made as easy as wished
    CHALLENGES_1_LIFETIME = {
        "since": 2027,
        "title": "Reto superado",
        "description": "Cumple tu primer reto del grupo.",
        "message": "*{}* cumple su primer reto del grupo. Desde hoy ya no vale decir que no se puede.",
    }
    CHALLENGES_5_LIFETIME = {
        "since": 2027,
        "title": "Aficionado a los retos",
        "description": "Cumple 5 retos del grupo.",
        "message": "*{}* ya lleva 5 retos del grupo cumplidos. Esto empieza a ser un hábito.",
    }
    CHALLENGES_15_LIFETIME = {
        "since": 2027,
        "special": 1,
        "title": "Cazarretos",
        "description": "Cumple 15 retos del grupo.",
        "message": "*{}* suma 15 retos del grupo cumplidos. Si hay un reto del grupo, seguro que ya le ha echado el ojo.",
    }
    ALL_ROUNDER_LIFETIME = {
        "since": 2027,
        "special": 2,
        "title": "Todoterreno",
        "description": "Cumple al menos un reto de cada tipo personal.",
        "message": "*{}* ha cumplido al menos un reto de cada tipo personal. Ni el más raro se le resiste.",
    }
    TEAM_CHALLENGE_LIFETIME = {
        "since": 2027,
        "special": 1,
        "title": "Misión cumplida entre todos",
        "description": "Cumple tu parte de un reto del grupo y que el grupo alcance el total.",
        "message": "*{}* ha cumplido su parte y el grupo ha llegado al total de un reto de grupo. Así da gusto.",
    }

    # About the world outside the app: the weather, the calendar, the sky and the age of a game. All of them are hidden,
    # have no season limit and count from 2027 (see docs/desarrollo/features.md)
    STORM_LIFETIME = {
        "since": 2027,
        "special": 1,
        "secret": True,
        "title": "Jugando bajo la tormenta",
        "description": "Juega mientras fuera hay tormenta.",
        "message": "*{}* ha seguido jugando mientras fuera caía una tormenta. Que se vaya la luz, que ya volverá.",
    }
    HORROR_FOG_LIFETIME = {
        "since": 2027,
        "special": 2,
        "secret": True,
        "title": "Niebla en Silent Hill",
        "description": "Juega a un juego de terror mientras hay niebla.",
        "message": "*{}* ha jugado a _{}_ mientras la niebla cubría la ciudad. No se ve nada, pero ahí fuera tampoco.",
    }
    STAR_WARS_DAY_LIFETIME = {
        "since": 2027,
        "secret": True,
        "title": "Que la Fuerza te acompañe",
        "description": "Juega a un juego de Star Wars el 4 de mayo.",
        "message": "*{}* ha celebrado el 4 de mayo jugando a _{}_. May the Fourth be with you.",
    }
    MARIO_DAY_LIFETIME = {
        "since": 2027,
        "secret": True,
        "title": "Mario Day",
        "description": "Juega a un juego de Mario el 10 de marzo.",
        "message": "*{}* ha celebrado el 10 de marzo (MAR10) jugando a _{}_. ¡Wahoo!",
    }
    LEAP_DAY_LIFETIME = {
        "since": 2027,
        "special": 1,
        "secret": True,
        "title": "Un día que no existe",
        "description": "Juega un 29 de febrero.",
        "message": "*{}* ha jugado un 29 de febrero, un día que solo sale cada cuatro años. Lo ha aprovechado como se merece.",
    }
    BIRTHDAY_LIFETIME = {
        "since": 2027,
        "secret": True,
        "title": "Cumpleaños feliz",
        "description": "Juega el día de tu cumpleaños.",
        "message": "*{}* cumple años y lo celebra jugando, que es lo que de verdad le hace ilusión. ¡Felicidades!",
    }
    FULL_MOON_LIFETIME = {
        "since": 2027,
        "secret": True,
        "title": "Luna llena",
        "description": "Juega un día de luna llena.",
        "message": "*{}* ha jugado un día de luna llena. Sin hombres lobo a la vista, solo un mando y mucho tiempo.",
    }
    LUNAR_ECLIPSE_LIFETIME = {
        "since": 2027,
        "special": 3,
        "secret": True,
        "title": "Eclipse lunar",
        "description": "Juega durante la noche de un eclipse de luna visible desde tu ciudad.",
        "message": "*{}* ha jugado el día de un eclipse de luna. Mientras el cielo se oscurecía, la partida seguía.",
    }
    SOLAR_ECLIPSE_LIFETIME = {
        "since": 2027,
        "special": 3,
        "secret": True,
        "title": "Eclipse solar",
        "description": "Juega el día de un eclipse de sol visible desde tu ciudad.",
        "message": "*{}* ha jugado el día de un eclipse de sol. Con las persianas bajadas ya estaba, pero hoy había motivo.",
    }
    SPRING_EQUINOX_LIFETIME = {
        "since": 2027,
        "secret": True,
        "title": "Equinoccio de primavera",
        "description": "Juega el día del equinoccio de primavera.",
        "message": "*{}* ha jugado el día del equinoccio de primavera. Día y noche iguales de largos, pero las horas de juego nunca salen iguales.",
    }
    SUMMER_SOLSTICE_LIFETIME = {
        "since": 2027,
        "secret": True,
        "title": "Solsticio de verano",
        "description": "Juega el día del solsticio de verano.",
        "message": "*{}* ha jugado el día más largo del año, el del solsticio de verano. Más luz solar que desaprovechar.",
    }
    AUTUMN_EQUINOX_LIFETIME = {
        "since": 2027,
        "secret": True,
        "title": "Equinoccio de otoño",
        "description": "Juega el día del equinoccio de otoño.",
        "message": "*{}* ha jugado el día del equinoccio de otoño. Llegan las tardes de manta y mando.",
    }
    WINTER_SOLSTICE_LIFETIME = {
        "since": 2027,
        "secret": True,
        "title": "Solsticio de invierno",
        "description": "Juega el día del solsticio de invierno.",
        "message": "*{}* ha jugado la noche más larga del año, la del solsticio de invierno. Más oscuridad para jugar.",
    }
    BIRTH_YEAR_GAME_LIFETIME = {
        "since": 2027,
        "special": 1,
        "secret": True,
        "title": "De la misma quinta",
        "description": "Juega a un juego que salió el año en que naciste.",
        "message": "*{}* ha jugado a _{}_, que salió el mismo año en que nació. Dos veteranos de la misma quinta.",
    }
    ARCHAEOLOGIST_LIFETIME = {
        "since": 2027,
        "secret": True,
        "title": "Arqueólogo",
        "description": "Juega a un juego que tenga 25 años o más.",
        "message": "*{}* ha desenterrado _{}_, un juego con 25 años (o más) a sus espaldas. Con brocha, paciencia y un emulador.",
    }

    # The easter eggs of the app itself (see EASTER_EGGS): they cannot be worked out from the sessions, so the front
    # reports them when they happen and no recalculation touches them
    LOGO_BLAST_LIFETIME = {
        "since": 2027,
        "special": 1,
        "secret": True,
        "title": "Big Bang",
        "description": "Descubre un secreto de la casa.",
        "message": "*{}* ha descubierto un secreto de la casa, aunque no sabemos si ha sido por error.",
    }

    KONAMI_LIFETIME = {
        "since": 2027,
        "special": 2,
        "secret": True,
        "title": "Treinta vidas",
        "description": "Introduce un truco de los de antes.",
        "message": "*{}* se ha sacado un truco de los de antes, de los de boli y papel.",
    }

    JUST_IN_TIME = {
        "since": 2023,
        "special": 1,
        "secret": True,
        "title": "Justo a tiempo",
        "description": "Completa un juego en su tiempo medio según HowLongToBeat, con un margen que crece con su duración.",
        "message": "*{}*"
        + " acaba de terminar "
        + "_{}_"
        + " en el tiempo medio según HLTB (con un margen que crece con la duración del juego).",
    }

    HAPPY_NEW_YEAR = {
        "since": 2023,
        "secret": True,
        "title": "Feliz año nuevo",
        "description": "Juega el 1 de enero.",
        "message": "*{}*"
        + " empieza el año jugando. Esperemos que haga alguna cosa más.",
    }

    TEAMWORK = {
        "since": 2023,
        "special": 1,
        "title": "Trabajo en equipo (de 4+)",
        "description": "Ten un temporizador en marcha a la vez que otros 3 jugadores, aunque no sea el mismo juego.",
        "message": "*{}*"
        + " han demostrado que el trabajo en equipo no es un mito."
        + " Por decisión propia o por casualidad, están jugando al mismo tiempo.",
    }

    EARLY_RISER = {
        "since": 2023,
        "secret": True,
        "title": "Madrugador",
        "description": "Empieza a jugar entre las 5:00 y las 6:00.",
        "message": "*{}*"
        + " cree que a quien madruga, Dios le ayuda."
        + " O eso, o tiene muchas cosas por hacer y ha decidido que jugar antes de las 6 de la mañana era una buena opción.",
    }

    NOCTURNAL = {
        "since": 2023,
        "secret": True,
        "title": "Plus por nocturnidad",
        "description": "Empieza a jugar entre las 2:00 y las 5:00.",
        "message": "*{}*"
        + " es un animal nocturno, y por eso empieza a jugar de madrugada (a partir de las 2)."
        + " Bueno, lo más seguro es que juegue a todas horas.",
    }


# The easter eggs the front reports (POST /users/{username}/easter-egg/{name}) and the achievement each one unlocks
EASTER_EGGS = {
    "logo": AchievementsElems.LOGO_BLAST_LIFETIME,
    "konami": AchievementsElems.KONAMI_LIFETIME,
}
