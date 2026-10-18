"""The notices of the recap of a month or a season: the group's one and each player's own (private).

The figures come from `crud/recap.py`; this module only words them and sends them."""
import datetime

from sqlalchemy.orm import Session

from ..config import Config
from ..crud import recap, users
from ..database import models
from . import actions, my_utils as utils
from .logger import LogManager

logger = LogManager().get_logger()
config = Config()

MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
SHORT_MONTHS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
MEDALS = ["🥇", "🥈", "🥉"]


def period_label(period: recap.Period) -> str:
    """"septiembre de 2026" or "la temporada 2026"."""
    if period.kind == "month":
        return f"{MONTHS[period.start.month - 1]} de {period.start.year}"
    return f"la temporada {period.start.year}"


def _short_date(day: datetime.date) -> str:
    return f"{day.day} {SHORT_MONTHS[day.month - 1]}"


def _link(period: recap.Period) -> str:
    """A line with the link to the story of the period (whoever opens it sees their own), or nothing when the public address is not set."""
    if not config.PUBLIC_URL:
        return ""
    return f"\n\n[Ver tu resumen en historias]({config.PUBLIC_URL}/#/story/{period.key})"


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def _change(now: int, before: int) -> str:
    return actions.signed_difference(int(now) - int(before), utils.format_duration)


def group_message(data: dict, period: recap.Period) -> str:
    """The recap of the group, for the group chat."""
    group = data["group"]
    lines = [f"📅 *Resumen de {period_label(period)}* 📅"]
    lines.append(
        f"El grupo ha jugado {utils.format_duration(group['seconds'])} ({_change(group['seconds'], group['previous_seconds'])}) "
        f"en {_plural(group['sessions'], 'sesión', 'sesiones')}."
    )
    podium = [
        f"{MEDALS[i]} {utils.escape_markdown(row['name'])} — {utils.format_duration(row['seconds'])}"
        for i, row in enumerate(group["ranking"][: len(MEDALS)])
    ]
    if podium:
        lines.append("\n".join(podium))
    if group["top_games"]:
        top = group["top_games"][0]
        lines.append(
            f"🎮 Juego del periodo: *{utils.escape_markdown(top.get('name') or top['game_id'])}* "
            f"({utils.format_duration(top['seconds'])}, {_plural(top['players'], 'jugador', 'jugadores')})."
        )
    if group["busiest_day"]:
        lines.append(f"🔥 Día más movido: {_short_date(group['busiest_day'])} ({utils.format_duration(group['busiest_day_seconds'])}).")
    if group["achievements"]:
        line = f"🏆 Logros conseguidos: {group['achievements']}."
        if group["rarest_achievement"]:
            line += f" El más raro: *{utils.escape_markdown(group['rarest_achievement']['title'])}*."
        lines.append(line)
    return "\n".join(lines) + _link(period)


def player_message(data: dict, period: recap.Period) -> str:
    """The recap of one player, for them alone."""
    player = data["player"]
    lines = [f"🎬 *Tu resumen de {period_label(period)}* 🎬"]
    hours = f"Horas: {utils.format_duration(player['seconds'])} ({_change(player['seconds'], player['previous_seconds'])})"
    lines.append(hours + (f" · puesto {player['position']}º" if player["position"] else ""))
    lines.append(f"Sesiones: {player['sessions']} · Días: {player['days']} · Juegos: {player['games']}")
    if player["star_game"]:
        star = player["star_game"]
        lines.append(f"⭐ Tu juego estrella: *{utils.escape_markdown(star.get('name') or star['id'])}* ({utils.format_duration(star['seconds'])}).")
    if player["best_day"]:
        lines.append(f"🔥 Tu mejor día: {_short_date(player['best_day'])} ({utils.format_duration(player['best_day_seconds'])}).")
    if player["best_streak"] > 1:
        lines.append(f"📆 Mejor racha: {_plural(player['best_streak'], 'día', 'días')} seguidos.")
    if player["playmate"]:
        mate = player["playmate"]
        lines.append(f"🤝 Con quien más has jugado: {utils.escape_markdown(mate['name'])} ({utils.format_duration(mate['seconds'])} juntos).")
    if player["games_started"] or player["games_completed"]:
        lines.append(f"Empezados: {player['games_started']} · Completados: {player['games_completed']}")
    if player["achievements"]:
        line = f"🏆 Logros: {player['achievements']}."
        if player["rarest_achievement"]:
            line += f" El más raro: *{utils.escape_markdown(player['rarest_achievement']['title'])}*."
        lines.append(line)
    return "\n".join(lines) + _link(period)


def previous_month(today: datetime.date) -> recap.Period:
    """The month that has just ended."""
    return recap.month_period(today.year, today.month).previous()


async def announce_recap(
    db: Session,
    period: recap.Period,
    group: bool = True,
    players: bool = True,
    only: models.User | None = None,
) -> dict:
    """Send the recap of the period: the group's to the group chat and, to each player who can be reached, their own.

    `only` limits the private ones to one user (an admin trying it on themself). A period in which nobody played
    sends nothing. The general notifications switch is respected by the senders. Returns what went out:
    {"empty": nobody played, "group": the group's was sent, "players": how many private ones}."""
    data = recap.build_recap(db, period)
    result = {"empty": data["group"]["seconds"] == 0, "group": False, "players": 0}
    if result["empty"]:
        return result
    if group:
        await utils.send_message(group_message(data, period), silent=False, ai_use="monthly_recap")
        result["group"] = True
    if players:
        for user in [only] if only is not None else users.get_users(db):
            if user.telegram_id is None and not actions.push_has_devices(user.id):
                continue
            own = recap.build_recap(db, period, user.id)
            if own["player"]["seconds"] == 0:
                continue
            await utils.send_message_to_user(user.telegram_id, player_message(own, period), user_id=user.id)
            result["players"] += 1
    return result


def describe(result: dict) -> str:
    """The result of `announce_recap` as the status of a job run."""
    if result["empty"]:
        return "nobody played"
    return f"{'group and ' if result['group'] else ''}{_plural(result['players'], 'user', 'users')}"
