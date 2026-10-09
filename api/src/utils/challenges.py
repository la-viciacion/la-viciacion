"""Challenges: the templates written in code and what is derived from a challenge's definition.

A challenge is data (`models.Challenge`): a template (`kind`), its options (`params`), a period and who it is for. Code
is written once per template, not once per challenge. Progress and completion are never stored: they are worked out
from the sessions and the library when asked (AGENTS.md rule 2). Only the definition, who opted out and the fact that
the group was told its total was reached are stored.

A template says who may launch it (`scope`), checks and normalizes the options it is given (`build`) and works out the
progress of the participants (`progress`). Adding a template is adding an entry to `TEMPLATES`.
"""
import datetime
import hashlib
import json
from dataclasses import dataclass
from typing import Callable

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import models

GROUP = "group"
USER = "user"

MAX_HOURS = 5000
MAX_TITLE = 120


class ChallengeError(ValueError):
    """The options of a challenge are not valid (the message is shown to whoever launched it)."""


@dataclass
class Built:
    """A challenge ready to be stored."""

    title: str
    params: dict
    starts_on: datetime.date
    ends_on: datetime.date
    game_id: str | None = None


@dataclass
class Template:
    label: str
    scope: str  # GROUP: launched by an admin for everybody; USER: by a player for themselves
    build: Callable[[Session, dict, datetime.date], Built]
    progress: Callable[[Session, models.Challenge, list[int]], dict]
    summary: Callable[[models.Challenge], str]  # what is asked, for the notice that launches it
    reached: Callable[[models.Challenge, dict], str]  # the notice when the group's total is reached


# ── period and numbers ──────────────────────────────────────────


def month_period(month) -> tuple[datetime.date, datetime.date]:
    """First and last day of a month "YYYY-MM"."""
    try:
        year, number = (int(part) for part in str(month).split("-"))
        first = datetime.date(year, number, 1)
    except (ValueError, TypeError):
        raise ChallengeError("El mes no es válido")
    following = datetime.date(year + (number == 12), number % 12 + 1, 1)
    return first, following - datetime.timedelta(days=1)


def hours(value, name: str, minimum: float = 0.5) -> float:
    """A number of hours (half an hour at least, a tenth at most of precision)."""
    try:
        number = round(float(value), 1)
    except (ValueError, TypeError):
        raise ChallengeError(f"{name} no es un número")
    if not minimum <= number <= MAX_HOURS:
        raise ChallengeError(f"{name} debe estar entre {minimum:g} y {MAX_HOURS} horas")
    return number


MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def spanish_date(day: datetime.date) -> str:
    """2026-10-31 -> "31 de octubre"."""
    return f"{day.day} de {MONTHS[day.month - 1]}"


def hours_text(value: float) -> str:
    """5.0 -> "5", 2.5 -> "2,5" """
    return f"{value:g}".replace(".", ",")


def status_of(challenge: models.Challenge, today: datetime.date) -> str:
    """'upcoming', 'active' or 'finished', from its period."""
    if today < challenge.starts_on:
        return "upcoming"
    return "active" if today <= challenge.ends_on else "finished"


def fingerprint(kind: str, built: Built, owner_user_id: int | None) -> str:
    """What makes two challenges the same: the template, its options, the period and whose it is."""
    canonical = json.dumps(
        [kind, built.params, built.game_id, built.starts_on.isoformat(), built.ends_on.isoformat(), owner_user_id],
        sort_keys=True, ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ── Juego del mes ───────────────────────────────────────────────


def build_game_of_month(db: Session, options: dict, today: datetime.date) -> Built:
    """Options: game_id, month ("YYYY-MM"), min_hours_each, min_hours_total."""
    game = db.get(models.Game, str(options.get("game_id") or ""))
    if game is None:
        raise ChallengeError("Elige un juego que exista")
    starts_on, ends_on = month_period(options.get("month"))
    if ends_on < today:
        raise ChallengeError("Ese mes ya ha pasado")
    each = hours(options.get("min_hours_each"), "El mínimo por jugador")
    total = hours(options.get("min_hours_total"), "El mínimo total")
    if total < each:
        raise ChallengeError("El mínimo total no puede ser menor que el de cada jugador")
    return Built(
        title=f"Juego del mes: {game.name}"[:MAX_TITLE],
        params={"min_hours_each": each, "min_hours_total": total},
        starts_on=starts_on,
        ends_on=ends_on,
        game_id=game.id,
    )


def seconds_in_game(db: Session, user_ids: list[int], game_id: str, starts_on: datetime.date, ends_on: datetime.date) -> dict[int, int]:
    """Seconds each user played a game in sessions that began within the period (finished ones only)."""
    if not user_ids:
        return {}
    rows = (
        db.query(models.GameTimer.user_id, func.sum(models.GameTimer.duration_seconds))
        .filter(
            models.GameTimer.user_id.in_(user_ids),
            models.GameTimer.game_id == game_id,
            models.GameTimer.is_active == False,  # noqa: E712
            models.GameTimer.start_time >= datetime.datetime.combine(starts_on, datetime.time.min),
            models.GameTimer.start_time < datetime.datetime.combine(ends_on + datetime.timedelta(days=1), datetime.time.min),
        )
        .group_by(models.GameTimer.user_id)
    )
    return {user_id: int(seconds or 0) for user_id, seconds in rows}  # MariaDB returns SUM() as Decimal


def game_of_month_result(played: dict[int, int], names: dict[int, str], each_hours: float, total_hours: float) -> dict:
    """The progress of a game of the month from what each participant played (pure)."""
    each, total = round(each_hours * 3600), round(total_hours * 3600)
    players = [
        {"user_id": user_id, "name": names[user_id], "seconds": played.get(user_id, 0), "target_seconds": each,
         "done": played.get(user_id, 0) >= each}
        for user_id in names
    ]
    players.sort(key=lambda p: (-p["seconds"], p["name"].lower()))
    seconds = sum(p["seconds"] for p in players)
    return {
        "players": players,
        "total_seconds": seconds,
        "total_target_seconds": total,
        "total_done": bool(players) and seconds >= total,
    }


def progress_game_of_month(db: Session, challenge: models.Challenge, participant_ids: list[int]) -> dict:
    params = json.loads(challenge.params)
    names = {
        user_id: name or username
        for user_id, username, name in db.query(models.User.id, models.User.username, models.User.name).filter(models.User.id.in_(participant_ids))
    }
    played = seconds_in_game(db, participant_ids, challenge.game_id, challenge.starts_on, challenge.ends_on)
    return game_of_month_result(played, names, params["min_hours_each"], params["min_hours_total"])


def summary_game_of_month(challenge: models.Challenge) -> str:
    params = json.loads(challenge.params)
    return (
        f"Mínimo {hours_text(params['min_hours_each'])} h cada uno y {hours_text(params['min_hours_total'])} h entre todos, "
        f"del {spanish_date(challenge.starts_on)} al {spanish_date(challenge.ends_on)}."
    )


def reached_game_of_month(challenge: models.Challenge, progress: dict) -> str:
    done = sum(1 for p in progress["players"] if p["done"])
    return (
        f"Entre todos habéis llegado a las {hours_text(json.loads(challenge.params)['min_hours_total'])} h. "
        f"{done} de {len(progress['players'])} ya habéis cumplido vuestro mínimo."
    )


TEMPLATES: dict[str, Template] = {
    "game_of_month": Template("Juego del mes", GROUP, build_game_of_month, progress_game_of_month, summary_game_of_month, reached_game_of_month),
}
