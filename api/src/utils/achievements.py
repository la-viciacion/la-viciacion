import datetime
from enum import Enum

from sqlalchemy import update
from sqlalchemy.orm import Session

from ..database import models
from . import my_utils as utils


# An achievement whose key ends like this has no season limit: it counts the whole history of a player and is
# earned once, not once a season (see crud/achievements.py). Nothing else says so: the name is the rule.
LIFETIME_SUFFIX = "_LIFETIME"


def is_lifetime(key: str) -> bool:
    return str(key).endswith(LIFETIME_SUFFIX)


# The season an achievement starts to count in when the code creates it: "since", which every definition has (a
# test fails if one does not). Every one says 2023, the first season of the app: the ones added later are
# retroactive and count the history since the start. An admin can change it afterwards: the database is the truth.
def first_season(achievement) -> int:
    return achievement.value["since"]


class AchievementsElems(Enum):
    # Format -> KEY = {"since": season it starts to count in, "special": level 1-3 (optional), "secret": True (optional), "title": "", "message": ""}
    # "special" (1 silver, 2 gold, 3 purple) and "secret" are how the achievement is created; an admin can change them afterwards.
    # Time day
    PLAYED_4_HOURS_DAY = {
        "since": 2023,
        "title": "Media Jornada laboral",
        "message": "*"
        + "{}"
        + "*"
        + " está tanteando el terreno para ver cómo va eso de jugar durante un ratito al día (4 horas).",
    }
    PLAYED_8_HOURS_DAY = {
        "since": 2023,
        "title": "Una jornada laboral",
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
        "message": "Como decía 'El Rancio', media jornada son 12 horas, y ese es el tiempo que ha invertido "
        + "*"
        + "{}"
        + "* en un solo día. Mariscos Recio estaría orgulloso.",
    }
    PLAYED_16_HOURS_DAY = {
        "since": 2023,
        "special": 2,
        "title": "No paro ni a cagar",
        "message": "De las 24h del día, 8 se deberían dedicar a dormir, y las otras 16 a hacer cosas. "
        + "*"
        + "{}"
        + "* ha decidido invertirlas a jugar. Lo de comer y hacer otras necesidades como asearse ya para otro día.",
    }

    # Time on game
    PLAYED_8_HOURS_GAME_DAY = {
        "since": 2023,
        "title": "Mi trabajo es jugar",
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
        "message": "{} ha acumulado un total de 100 horas de juego en lo que va de año.",
    }
    PLAYED_200_HOURS = {
        "since": 2023,
        "title": "200 horas",
        "message": "{} ha acumulado un total de 200 horas de juego en lo que va de año.",
    }
    PLAYED_500_HOURS = {
        "since": 2023,
        "special": 1,
        "title": "500 horas",
        "message": "{} ha acumulado un total de 500 horas de juego en lo que va de año.",
    }
    PLAYED_1000_HOURS = {
        "since": 2023,
        "special": 2,
        "title": "1000 horas",
        "message": "{} ha acumulado un total de 1000 horas de juego en lo que va de año.",
    }

    # Session time
    PLAYED_LESS_5_MIN_SESSION = {
        "since": 2023,
        "title": "Lo he abierto sin querer",
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
        "message": "*{}"
        + "* acaba de jugar 4 horas seguidas (o más) a _"
        + "{}"
        + "_ en una sola sesión.",
    }
    PLAYED_8_HOURS_SESSION = {
        "since": 2023,
        "title": "Mi trabajo es jugar (sin parar)",
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
        "message": "*{}* acaba de empezar su juego número 10.",
    }
    PLAYED_42_GAMES = {
        "since": 2023,
        "special": 1,
        "title": "La respuesta",
        "message": "*{}* ha jugado a la mágica cifra de 42 juegos."
        + " No sabemos si tendrá la respuesta al sentido de la vida, "
        + "al universo y todo lo demás, pero lo que seguro que tiene "
        + "es mucho tiempo libre.",
    }
    PLAYED_50_GAMES = {
        "since": 2023,
        "special": 1,
        "title": "50 juegos jugados",
        "message": "*{}* acaba de empezar su juego número 50.",
    }
    PLAYED_100_GAMES = {
        "since": 2023,
        "special": 2,
        "title": "100 juegos (jugados)",
        "message": "A 100 juegos acaba de jugar "
        + "*{}*. Estamos hablando de arrancar un nuevo"
        + " juego cada 3,65 días de media (si dejara de empezar juegos nuevos). Pensemos en ello.",
    }
    COMPLETED_1_GAME = {
        "since": 2023,
        "title": "Primer juego completado",
        "message": "*{}* acaba de completar su primer juego del año. Y esto no ha hecho más que empezar.",
    }
    COMPLETED_5_GAMES = {
        "since": 2023,
        "title": "5 juegos completados",
        "message": "*{}* acaba de completar su juego número 5. Esto ya va en serio.",
    }
    COMPLETED_10_GAMES = {
        "since": 2023,
        "title": "10 juegos completados",
        "message": "*{}* ya lleva 10 juegos completados. Se nota que sabe terminar lo que empieza (a diferencia de otros).",
    }
    COMPLETED_25_GAMES = {
        "since": 2023,
        "special": 1,
        "title": "25 juegos completados",
        "message": "*{}* ha completado 25 juegos. A este ritmo, el año se le queda corto.",
    }
    COMPLETED_42_GAMES = {
        "since": 2023,
        "special": 2,
        "secret": True,
        "title": "La respuesta (de verdad)",
        "message": "Si empezar 42 juegos ya es todo un logro, no hablemos de acabar 42. "
        + "Ha quedado patente que a "
        + "*{}*"
        + " la vida más allá de la puerta de casa no le importa lo más mínimo.",
    }
    COMPLETED_100_GAMES = {
        "since": 2023,
        "special": 3,
        "title": "100 juegos completados",
        "message": "*{}*"
        + " acaba de completar 100 juegos. No se me ocurre qué decir.",
    }
    PLAYED_5_GAMES_DAY = {
        "since": 2023,
        "title": "Indecisión",
        "message": "Este. No, este. No, mejor este otro. AAAHHHRRRGGG, tengo demasiados juegos. "
        + "*{}*"
        + " no tiene ni idea de a qué jugar, y ya ha probado con 5 o más juegos en un solo día.",
    }
    PLAYED_10_GAMES_DAY = {
        "since": 2023,
        "special": 1,
        "secret": True,
        "title": "Indecisión x2",
        "message": "AAAHHHRRRGGG, sigo sin saber a qué jugar. "
        + "*{}*"
        + " ha acumulado tantos juegos en su biblioteca que salta de uno "
        + "a otro como pollo sin cabeza, y ya ha probado con 10 o más juegos en un solo día.",
    }

    # Total days
    PLAYED_7_DAYS = {
        "since": 2023,
        "title": "7 días jugados",
        "message": "*{}* acumula un total de 7 días jugados en lo que va de año.",
    }
    PLAYED_15_DAYS = {
        "since": 2023,
        "title": "15 días jugados",
        "message": "*{}* acumula un total de 15 días jugados en lo que va de año.",
    }
    PLAYED_30_DAYS = {
        "since": 2023,
        "title": "30 días jugados",
        "message": "*{}* acumula un total de 30 días jugados en lo que va de año.",
    }
    PLAYED_60_DAYS = {
        "since": 2023,
        "title": "60 días jugados",
        "message": "*{}* acumula un total de 60 días jugados en lo que va de año.",
    }
    PLAYED_100_DAYS = {
        "since": 2023,
        "title": "100 días jugados",
        "message": "*{}* acumula un total de 100 días jugados en lo que va de año.",
    }
    PLAYED_200_DAYS = {
        "since": 2023,
        "special": 1,
        "secret": True,
        "title": "200 días jugados",
        "message": "*{}* acumula un total de 200 días jugados en lo que va de año.",
    }
    PLAYED_300_DAYS = {
        "since": 2023,
        "special": 2,
        "secret": True,
        "title": "300 días jugados",
        "message": "*{}* acumula un total de 300 días jugados en lo que va de año.",
    }
    PLAYED_365_DAYS = {
        "since": 2023,
        "special": 3,
        "secret": True,
        "title": "365 días jugados",
        "message": "*{}* acumula un total de 365 días jugados en lo que va de año.",
    }

    # Streaks
    STREAK_7_DAYS = {
        "since": 2023,
        "title": "Racha de 7 días",
        "message": "Pues resulta que "
        + "*{}*"
        + " lleva 1 semana jugando todos los días. "
        + "Podríamos decir que tiene pocas cosas mejores que hacer.",
    }
    STREAK_15_DAYS = {
        "since": 2023,
        "title": "Racha de 15 días",
        "message": "Ya son 15 los días que lleva "
        + "*{}*"
        + " sin faltar ni uno a la sesión de juego de rigor. "
        + "A este paso habrá que ir pensando en empezar a regarlo.",
    }
    STREAK_30_DAYS = {
        "since": 2023,
        "title": "Racha de 30 días",
        "message": "Poco más que añadir. "
        + "*{}*"
        + " acumula una racha de 30 días con una sesión de juego como mínimo. "
        + "Lo mejor será ir llamando al psiquiátrico.",
    }
    STREAK_60_DAYS = {
        "since": 2023,
        "title": "Racha de 60 días",
        "message": "*{}*" + " acumula una racha de 60 días.",
    }
    STREAK_100_DAYS = {
        "since": 2023,
        "special": 1,
        "title": "Racha de 100 días",
        "message": "*{}*" + " acumula una racha de 100 días.",
    }
    STREAK_200_DAYS = {
        "since": 2023,
        "special": 1,
        "title": "Racha de 200 días",
        "message": "*{}*" + " acumula una racha de 200 días.",
    }
    STREAK_300_DAYS = {
        "since": 2023,
        "special": 2,
        "title": "Racha de 300 días",
        "message": "*{}*" + " acumula una racha de 300 días.",
    }
    STREAK_365_DAYS = {
        "since": 2023,
        "special": 3,
        "title": "Racha de 365 días",
        "message": "*{}*" + " acumula una racha de 365 días.",
    }

    # Others
    COMPLETED_IN_A_DAY = {
        "since": 2023,
        "secret": True,
        "title": "Del tirón",
        "message": "*{}* ha empezado y terminado _{}_ en un solo día. Sin dormir, sin pausas y sin remordimientos.",
    }

    RELEASE_DAY = {
        "since": 2023,
        "special": 1,
        "title": "Lo estaba esperando",
        "message": "*{}* ha jugado a _{}_ el mismo día de su lanzamiento. Ni un minuto de espera.",
    }

    ALL_TOGETHER = {
        "since": 2023,
        "title": "Todos a una",
        "message": "*{}* están jugando a la vez a _{}_. Como en los viejos tiempos de las LAN party.",
    }

    PRODIGAL_SON = {
        "since": 2023,
        "title": "El hijo pródigo",
        "message": "*{}* vuelve a jugar tras 30 días (o más) sin tocar un mando. Se le echaba de menos, aunque algunos ni lo habían notado.",
    }

    RESCUE = {
        "since": 2023,
        "special": 2,
        "title": "Rescate",
        "message": "*{}* ha rescatado _{}_ del olvido: llevaba 90 días (o más) sin tocarlo y por fin lo ha terminado.",
    }

    FINISHING_TOUCH = {
        "since": 2023,
        "special": 3,
        "title": "Remate",
        "message": "*{}* ha rematado _{}_ tras 90 días (o más) olvidado, cuando ya llevaba más de un 80 % del juego. A un paso de la meta y aun así tardó en volver.",
    }

    WORK_WEEK = {
        "since": 2023,
        "special": 1,
        "title": "Semana laboral",
        "message": "*{}* acaba de completar una semana laboral entera de 40 horas jugando. Sin vacaciones ni convenio.",
    }

    SAVED_BY_THE_BELL = {
        "since": 2023,
        "special": 1,
        "secret": True,
        "title": "Salvado por la campana",
        "message": "*{}* estaba jugando a _{}_ justo cuando cambió el año. Mientras otros se atragantaban con las uvas, él seguía con el mando en la mano.",
    }

    # No season limit: they count the whole history of a player and are earned once (the key ends in _LIFETIME)
    PLAYED_1000_HOURS_GAME_LIFETIME = {
        "since": 2023,
        "special": 2,
        "title": "Una relación seria",
        "message": "*{}* lleva 1000 horas en total jugando a _{}_, sumando todas las temporadas. Esto ya no es un juego, es una relación.",
    }
    PLAYED_100_DAYS_LIFETIME = {
        "since": 2023,
        "title": "100 días jugados (en total)",
        "message": "*{}* suma 100 días jugados en total, contando todas las temporadas. La costumbre ya va cogiendo forma.",
    }
    PLAYED_200_DAYS_LIFETIME = {
        "since": 2023,
        "title": "200 días jugados (en total)",
        "message": "*{}* suma 200 días jugados en total, contando todas las temporadas. La costumbre ya es ley.",
    }
    PLAYED_500_DAYS_LIFETIME = {
        "since": 2023,
        "title": "500 días jugados (en total)",
        "message": "*{}* suma 500 días jugados en total, contando todas las temporadas. Más de un año y pico de partidas.",
    }
    PLAYED_1000_DAYS_LIFETIME = {
        "since": 2023,
        "special": 1,
        "title": "1000 días jugados (en total)",
        "message": "*{}* suma 1000 días jugados en total, contando todas las temporadas. Casi tres años de su vida, con el mando en la mano.",
    }
    PLAYED_2000_DAYS_LIFETIME = {
        "since": 2023,
        "special": 2,
        "title": "2000 días jugados (en total)",
        "message": "*{}* suma 2000 días jugados en total, contando todas las temporadas. Más de cinco años de partidas. Ya es patrimonio del grupo.",
    }
    PLAYED_5000_DAYS_LIFETIME = {
        "since": 2023,
        "special": 3,
        "title": "5000 días jugados (en total)",
        "message": "*{}* suma 5000 días jugados en total, contando todas las temporadas. Casi catorce años jugando. Que alguien le dé las llaves de la ciudad.",
    }
    PLAYED_500_HOURS_LIFETIME = {
        "since": 2023,
        "title": "500 horas (en total)",
        "message": "*{}* acumula 500 horas de juego en total, sumando todas las temporadas. Y las que le quedan.",
    }
    PLAYED_1000_HOURS_LIFETIME = {
        "since": 2023,
        "title": "1000 horas (en total)",
        "message": "*{}* acumula 1000 horas de juego en total, sumando todas las temporadas. Son más de 41 días seguidos sin parar.",
    }
    PLAYED_2000_HOURS_LIFETIME = {
        "since": 2023,
        "special": 1,
        "title": "2000 horas (en total)",
        "message": "*{}* acumula 2000 horas de juego en total, sumando todas las temporadas. Casi tres meses seguidos, sin dormir.",
    }
    PLAYED_5000_HOURS_LIFETIME = {
        "since": 2023,
        "special": 2,
        "title": "5000 horas (en total)",
        "message": "*{}* acumula 5000 horas de juego en total, sumando todas las temporadas. Casi siete meses seguidos. Que descanse alguien.",
    }
    PLAYED_10000_HOURS_LIFETIME = {
        "since": 2023,
        "special": 3,
        "title": "10000 horas (en total)",
        "message": "*{}* acumula 10000 horas de juego en total, sumando todas las temporadas. Dicen que con 10.000 horas se llega a maestro. De qué, aún está por ver.",
    }
    PLAYED_100_GAMES_LIFETIME = {
        "since": 2023,
        "title": "100 juegos jugados (en total)",
        "message": "*{}* ha jugado a 100 juegos distintos en total, contando todas las temporadas. Y eso que solo cuenta los distintos.",
    }
    PLAYED_200_GAMES_LIFETIME = {
        "since": 2023,
        "title": "200 juegos jugados (en total)",
        "message": "*{}* ha jugado a 200 juegos distintos en total, contando todas las temporadas. Una biblioteca que ya pide estantería nueva.",
    }
    PLAYED_500_GAMES_LIFETIME = {
        "since": 2023,
        "special": 1,
        "title": "500 juegos jugados (en total)",
        "message": "*{}* ha jugado a 500 juegos distintos en total, contando todas las temporadas. Esto ya no es una biblioteca, es un museo.",
    }
    PLAYED_1000_GAMES_LIFETIME = {
        "since": 2023,
        "special": 2,
        "title": "1000 juegos jugados (en total)",
        "message": "*{}* ha jugado a 1000 juegos distintos en total, contando todas las temporadas. Mil juegos distintos. Que le hagan un monumento.",
    }
    COMPLETED_100_GAMES_LIFETIME = {
        "since": 2023,
        "title": "100 juegos completados (en total)",
        "message": "*{}* ha completado 100 juegos distintos en total, sumando todas las temporadas. Terminar lo que se empieza, convertido en estilo de vida.",
    }
    COMPLETED_200_GAMES_LIFETIME = {
        "since": 2023,
        "title": "200 juegos completados (en total)",
        "message": "*{}* ha completado 200 juegos distintos en total, sumando todas las temporadas. Dos centenares de créditos finales.",
    }
    COMPLETED_500_GAMES_LIFETIME = {
        "since": 2023,
        "special": 2,
        "title": "500 juegos completados (en total)",
        "message": "*{}* ha completado 500 juegos distintos en total, sumando todas las temporadas. Medio millar de finales. Alguien tiene mucho que contar.",
    }
    COMPLETED_1000_GAMES_LIFETIME = {
        "since": 2023,
        "special": 3,
        "title": "1000 juegos completados (en total)",
        "message": "*{}* ha completado 1000 juegos distintos en total, sumando todas las temporadas. Mil juegos terminados. Ya no queda nada por ver.",
    }

    # About the world outside the app: the weather, the calendar, the sky and the age of a game. All of them are hidden,
    # have no season limit and count from 2027 (see docs/features.md)
    STORM_LIFETIME = {
        "since": 2027,
        "special": 1,
        "secret": True,
        "title": "Jugando bajo la tormenta",
        "message": "*{}* ha seguido jugando mientras fuera caía una tormenta. Que se vaya la luz, que ya volverá.",
    }
    HORROR_FOG_LIFETIME = {
        "since": 2027,
        "special": 2,
        "secret": True,
        "title": "Niebla en Silent Hill",
        "message": "*{}* ha jugado a _{}_ mientras la niebla cubría la ciudad. No se ve nada, pero ahí fuera tampoco.",
    }
    STAR_WARS_DAY_LIFETIME = {
        "since": 2027,
        "secret": True,
        "title": "Que la Fuerza te acompañe",
        "message": "*{}* ha celebrado el 4 de mayo jugando a _{}_. May the Fourth be with you.",
    }
    MARIO_DAY_LIFETIME = {
        "since": 2027,
        "secret": True,
        "title": "Mario Day",
        "message": "*{}* ha celebrado el 10 de marzo (MAR10) jugando a _{}_. ¡Wahoo!",
    }
    LEAP_DAY_LIFETIME = {
        "since": 2027,
        "special": 1,
        "secret": True,
        "title": "Un día que no existe",
        "message": "*{}* ha jugado un 29 de febrero, un día que solo sale cada cuatro años. Lo ha aprovechado como se merece.",
    }
    BIRTHDAY_LIFETIME = {
        "since": 2027,
        "secret": True,
        "title": "Cumpleaños feliz",
        "message": "*{}* cumple años y lo celebra jugando, que es lo que de verdad le hace ilusión. ¡Felicidades!",
    }
    FULL_MOON_LIFETIME = {
        "since": 2027,
        "secret": True,
        "title": "Luna llena",
        "message": "*{}* ha jugado un día de luna llena. Sin hombres lobo a la vista, solo un mando y mucho tiempo.",
    }
    LUNAR_ECLIPSE_LIFETIME = {
        "since": 2027,
        "special": 3,
        "secret": True,
        "title": "Eclipse lunar",
        "message": "*{}* ha jugado el día de un eclipse de luna. Mientras el cielo se oscurecía, la partida seguía.",
    }
    SOLAR_ECLIPSE_LIFETIME = {
        "since": 2027,
        "special": 3,
        "secret": True,
        "title": "Eclipse solar",
        "message": "*{}* ha jugado el día de un eclipse de sol. Con las persianas bajadas ya estaba, pero hoy había motivo.",
    }
    SPRING_EQUINOX_LIFETIME = {
        "since": 2027,
        "secret": True,
        "title": "Equinoccio de primavera",
        "message": "*{}* ha jugado el día del equinoccio de primavera. Día y noche iguales de largos, pero las horas de juego nunca salen iguales.",
    }
    SUMMER_SOLSTICE_LIFETIME = {
        "since": 2027,
        "secret": True,
        "title": "Solsticio de verano",
        "message": "*{}* ha jugado el día más largo del año, el del solsticio de verano. Más luz solar que desaprovechar.",
    }
    AUTUMN_EQUINOX_LIFETIME = {
        "since": 2027,
        "secret": True,
        "title": "Equinoccio de otoño",
        "message": "*{}* ha jugado el día del equinoccio de otoño. Llegan las tardes de manta y mando.",
    }
    WINTER_SOLSTICE_LIFETIME = {
        "since": 2027,
        "secret": True,
        "title": "Solsticio de invierno",
        "message": "*{}* ha jugado la noche más larga del año, la del solsticio de invierno. Más oscuridad para jugar.",
    }
    BIRTH_YEAR_GAME_LIFETIME = {
        "since": 2027,
        "special": 1,
        "secret": True,
        "title": "De la misma quinta",
        "message": "*{}* ha jugado a _{}_, que salió el mismo año en que nació. Dos veteranos de la misma quinta.",
    }
    ARCHAEOLOGIST_LIFETIME = {
        "since": 2027,
        "secret": True,
        "title": "Arqueólogo",
        "message": "*{}* ha desenterrado _{}_, un juego con 25 años (o más) a sus espaldas. Con brocha, paciencia y un emulador.",
    }

    JUST_IN_TIME = {
        "since": 2023,
        "special": 1,
        "secret": True,
        "title": "Justo a tiempo",
        "message": "*{}*"
        + " acaba de terminar "
        + "_{}_"
        + " en el tiempo medio según HLTB (con un margen del 5 %).",
    }

    HAPPY_NEW_YEAR = {
        "since": 2023,
        "secret": True,
        "title": "Feliz año nuevo",
        "message": "*{}*"
        + " empieza el año jugando. Esperemos que haga alguna cosa más.",
    }

    TEAMWORK = {
        "since": 2023,
        "special": 1,
        "secret": True,
        "title": "Trabajo en equipo (de 4+)",
        "message": "*{}*"
        + " han demostrado que el trabajo en equipo no es un mito."
        + " Por decisión propia o por casualidad, están jugando al mismo tiempo.",
    }

    EARLY_RISER = {
        "since": 2023,
        "secret": True,
        "title": "Madrugador",
        "message": "*{}*"
        + " cree que a quien madruga, Dios le ayuda."
        + " O eso, o tiene muchas cosas por hacer y ha decidido que jugar antes de las 6 de la mañana era una buena opción.",
    }

    NOCTURNAL = {
        "since": 2023,
        "secret": True,
        "title": "Plus por nocturnidad",
        "message": "*{}*"
        + " es un animal nocturno, y por eso empieza a jugar de madrugada (a partir de las 2)."
        + " Bueno, lo más seguro es que juegue a todas horas.",
    }
