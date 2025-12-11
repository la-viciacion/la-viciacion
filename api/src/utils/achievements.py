import datetime
from enum import Enum

from sqlalchemy import update
from sqlalchemy.orm import Session

from ..database import models
from . import my_utils as utils


class AchievementsElems(Enum):
    # Format -> KEY = {"title":"", "message":""}
    # Time day
    PLAYED_4_HOURS_DAY = {
        "title": "Media Jornada laboral",
        "message": "*"
        + "{}"
        + "*"
        + " está tanteando el terreno para ver cómo va eso de jugar durante un ratito al día (4 horas).",
    }
    PLAYED_8_HOURS_DAY = {
        "title": "Una jornada laboral",
        "message": "Las jornadas laborales de 8 horas deberían desaparecer, pero no las de jugar. "
        + "*"
        + "{}"
        + "*"
        + " acaba de invertir el tiempo máximo legal para una jornada de trabajo.",
    }
    PLAYED_12_HOURS_DAY = {
        "title": "Media jornada, 12 horas",
        "message": "Como decía 'El Rancio', media jornada son 12 horas, y ese es el tiempo que ha invertido "
        + "*"
        + "{}"
        + "* en un solo día. Mariscos Recio estaría orgulloso.",
    }
    PLAYED_16_HOURS_DAY = {
        "title": "No paro ni a cagar",
        "message": "De las 24h del día, 8 se deberían dedicar a dormir, y las otras 16 a hacer cosas. "
        + "*"
        + "{}"
        + "* ha decidido invertirlas a jugar. Lo de comer y hacer otras necesidades como asearse ya para otro día.",
    }

    # Time on game
    PLAYED_8_HOURS_GAME_DAY = {
        "title": "Mi trabajo es jugar",
        "message": "Lo de estar 8 horas trabajando no suele gustar, pero jugando ya es otra cosa. "
        + ""
        + "{}"
        + " acaba de jugar 8 horas (o más) a _"
        + "{}"
        + "_ en un mismo día.",
    }
    # PLAYED_8_HOURS_GAME_DAY_ONE_SESSION = {
    #     "title": "Mi trabajo es jugar (sin parar)",
    #     "message": "8 horas haciendo lo mismo suele llegar a aburrir, siempre que no sea jugar. "
    #     + ""
    #     + "{}"
    #     + " acaba de cascarse 8 horas seguidas (o más) jugando a _"
    #     + "{}"
    #     + "_; cualquiera diría que le está gustando.",
    # }
    PLAYED_100_HOURS_GAME = {
        "title": "Cualquiera diría que le gusta ese juego",
        "message": "Todo apunta a que a *"
        + "{}"
        + "* le ha enganchado _"
        + "{}"
        + "_, porque acaba de rebasar la barrera de las 100 horas invertidas en él.",
    }
    PLAYED_500_HOURS_GAME = {
        "title": "Una buena inversión",
        "message": "Si he pagado por un juego, es para jugarlo."
        + " Eso es lo que habrá pensado *"
        + "{}"
        + "*, que acaba de pasar las 500 horas jugadas a _"
        + "{}"
        + "_.",
    }
    PLAYED_1000_HOURS_GAME = {
        "title": "¿Para qué diversificar?",
        "message": "A *"
        + "{}"
        + "* lo único que le importa en esta vida es _"
        + "{}"
        + "_. 1000 horas (y seguro que subiendo). Mejor no preguntar.",
    }

    # Total time
    PLAYED_100_HOURS = {
        "title": "100 horas",
        "message": "{} ha acumulado un total de 100 horas de juego en lo que va de año.",
    }
    PLAYED_200_HOURS = {
        "title": "200 horas",
        "message": "{} ha acumulado un total de 200 horas de juego en lo que va de año.",
    }
    PLAYED_500_HOURS = {
        "title": "500 horas",
        "message": "{} ha acumulado un total de 500 horas de juego en lo que va de año.",
    }
    PLAYED_1000_HOURS = {
        "title": "1000 horas",
        "message": "{} ha acumulado un total de 1000 horas de juego en lo que va de año.",
    }

    # Session time
    PLAYED_LESS_5_MIN_SESSION = {
        "title": "Lo he abierto sin querer",
        "message": "Al parecer a *"
        + "{}"
        + "* no le ha convencido _"
        + "{}"
        + "_, ya que ha hecho una ridícula sesión de juego de 5 minutos (o menos).",
    }
    PLAYED_4_HOURS_SESSION = {
        "title": "Sesión de 4 horas",
        "message": "*{}"
        + "* acaba de jugar 4 horas seguidas (o más)"
        + " en un mismo día.",
    }
    PLAYED_8_HOURS_SESSION = {
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
        "title": "10 juegos jugados",
        "message": "*{}* acaba de empezar su juego número 10.",
    }
    PLAYED_42_GAMES = {
        "title": "La respuesta",
        "message": "*{}* ha jugado a la mágica cifra de 42 juegos."
        + " No sabemos si tendrá la respuesta al sentido de la vida, "
        + "al universo y todo lo demás, pero lo que seguro que tiene "
        + "es mucho tiempo libre.",
    }
    PLAYED_50_GAMES = {
        "title": "50 juegos jugados",
        "message": "*{}* acaba de empezar su juego número 50.",
    }
    PLAYED_100_GAMES = {
        "title": "100 juegos (jugados)",
        "message": "A 100 juegos acaba de jugar "
        + "*{}*. Estamos hablando de arrancar un nuevo"
        + " juego cada 3,65 días de media (si dejara de empezar juegos nuevos). Pensemos en ello.",
    }
    COMPLETED_42_GAMES = {
        "title": "La respuesta (de verdad)",
        "message": "Si empezar 42 juegos ya es todo un logro, no hablemos de acabar 42. "
        + "Ha quedado patente que a "
        + "*{}*"
        + " la vida más allá de la puerta de casa no le importa lo más mínimo.",
    }
    COMPLETED_100_GAMES = {
        "title": "100 juegos completados",
        "message": "*{}*"
        + " acaba de completar 100 juegos. No se me ocurre qué decir.",
    }
    PLAYED_5_GAMES_DAY = {
        "title": "Indecisión",
        "message": "Este. No, este. No, mejor este otro. AAAHHHRRRGGG, tengo demasiados juegos. "
        + "*{}*"
        + " no tiene ni idea de a qué jugar, y ya ha probado con 5 o más juegos en un solo día.",
    }
    PLAYED_10_GAMES_DAY = {
        "title": "Indecisión x2",
        "message": "AAAHHHRRRGGG, sigo sin saber a qué jugar."
        + "*{}*"
        + " ha acumulado tantos juegos en su biblioteca que salta de uno "
        + "a otro como pollo sin cabeza, y ya ha probado con 10 o más juegos en un solo día.",
    }

    # Total days
    PLAYED_7_DAYS = {
        "title": "7 días jugados",
        "message": "*{}* acumula un total de 7 días jugados en lo que va de año.",
    }
    PLAYED_15_DAYS = {
        "title": "15 días jugados",
        "message": "*{}* acumula un total de 15 días jugados en lo que va de año.",
    }
    PLAYED_30_DAYS = {
        "title": "30 días jugados",
        "message": "*{}* acumula un total de 30 días jugados en lo que va de año.",
    }
    PLAYED_60_DAYS = {
        "title": "60 días jugados",
        "message": "*{}* acumula un total de 60 días jugados en lo que va de año.",
    }
    PLAYED_100_DAYS = {
        "title": "100 días jugados",
        "message": "*{}* acumula un total de 100 días jugados en lo que va de año.",
    }
    PLAYED_200_DAYS = {
        "title": "200 días jugados",
        "message": "*{}* acumula un total de 200 días jugados en lo que va de año.",
    }
    PLAYED_300_DAYS = {
        "title": "300 días jugados",
        "message": "*{}* acumula un total de 300 días jugados en lo que va de año.",
    }
    PLAYED_365_DAYS = {
        "title": "365 días jugados",
        "message": "*{}* acumula un total de 365 días jugados en lo que va de año.",
    }

    # Streaks
    STREAK_7_DAYS = {
        "title": "Racha de 7 días",
        "message": "Pues resulta que "
        + "*{}*"
        + " lleva 1 semana jugando todos los días. "
        + "Podríamos decir que tiene pocas cosas mejores que hacer.",
    }
    STREAK_15_DAYS = {
        "title": "Racha de 15 días",
        "message": "Ya son 15 los días que lleva "
        + "*{}*"
        + " sin faltar ni uno a la sesión de juego de rigor. "
        + "A este paso habrá que ir pensando en empezar a regarlo.",
    }
    STREAK_30_DAYS = {
        "title": "Racha de 30 días",
        "message": "Poco más que añadir. "
        + "*{}*"
        + " acumula una racha de 30 días con una sesión de juego como mínimo. "
        + "Lo mejor será ir llamando al psiquiátrico.",
    }
    STREAK_60_DAYS = {
        "title": "Racha de 60 días",
        "message": "*{}*" + " acumula una racha de 60 días.",
    }
    STREAK_100_DAYS = {
        "title": "Racha de 100 días",
        "message": "*{}*" + " acumula una racha de 100 días.",
    }
    STREAK_200_DAYS = {
        "title": "Racha de 200 días",
        "message": "*{}*" + " acumula una racha de 200 días.",
    }
    STREAK_300_DAYS = {
        "title": "Racha de 300 días",
        "message": "*{}*" + " acumula una racha de 300 días.",
    }
    STREAK_365_DAYS = {
        "title": "Racha de 365 días",
        "message": "*{}*" + " acumula una racha de 365 días.",
    }

    # Others
    JUST_IN_TIME = {
        "title": "Justo a tiempo",
        "message": "*{}*"
        + " acaba de terminar "
        + "_{}_"
        + " exactamente en el tiempo medio según HLTB.",
    }

    HAPPY_NEW_YEAR = {
        "title": "Feliz año nuevo",
        "message": "*{}*"
        + " empieza el año jugando. Esperemos que haga alguna cosa más.",
    }

    TEAMWORK = {
        "title": "Trabajo en equipo (de 4+)",
        "message": "*{}*"
        + " han demostrado que el trabajo en equipo no es un mito."
        + " Por decisión propia o por casualidad, están jugando al mismo tiempo.",
    }

    EARLY_RISER = {
        "title": "Madrugador",
        "message": "*{}*"
        + " cree que a quien madruga, Dios le ayuda."
        + " O eso, o tiene muchas cosas por hacer y ha decidido que jugar antes de las 6 de la mañana era una buena opción.",
    }

    NOCTURNAL = {
        "title": "Plus por nocturnidad",
        "message": "*{}*"
        + " es un animal nocturno, y por eso empieza a jugar de madrugada (a partir de las 2)."
        + " Bueno, lo más seguro es que juegue a todas horas.",
    }
