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
    # the notices of a group challenge: what is asked when it is launched, and the group's total reached
    summary: Callable[[models.Challenge], str] | None = None
    reached: Callable[[models.Challenge, dict], str] | None = None


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


# ── Probar un género ────────────────────────────────────────────

# How long a personal challenge lasts, counting the day it is launched
DURATIONS = {"week": 7, "month": 30, "quarter": 90}
DEFAULT_HOURS = 2


def split_genres(genres: str | None) -> list[str]:
    """`games.genres` is one comma separated string."""
    return [genre.strip() for genre in (genres or "").split(",") if genre.strip()]


def _available(db: Session, column) -> dict[str, tuple[str, int]]:
    """The words of a comma separated column of the games: {lower-cased: (as written, how many games have it)}."""
    found: dict[str, tuple[str, int]] = {}
    for (text,) in db.query(column).filter(column.isnot(None)):
        for word in {w.casefold(): w for w in split_genres(text)}.values():
            name, count = found.get(word.casefold(), (word, 0))
            found[word.casefold()] = (name, count + 1)
    return found


def available_genres(db: Session) -> dict[str, tuple[str, int]]:
    """The genres of the games in the database: {lower-cased: (name as written, how many games have it)}."""
    return _available(db, models.Game.genres)


def available_tags(db: Session) -> dict[str, tuple[str, int]]:
    """The tags of the games in the database (RAWG's: Horror, Singleplayer...), like `available_genres`."""
    return _available(db, models.Game.tags)


def build_new_genre(db: Session, options: dict, today: datetime.date) -> Built:
    """Options: genre (one that exists and has games), mode ("play" hours or "complete" one game), hours (play only,
    2 by default) and duration ("week", "month" or "quarter"; the period starts today)."""
    genres = available_genres(db)
    wanted = str(options.get("genre") or "").strip().casefold()
    if wanted not in genres:
        raise ChallengeError("Elige un género que exista")
    name = genres[wanted][0]
    mode = options.get("mode")
    if mode not in ("play", "complete"):
        raise ChallengeError("Elige si quieres jugar o completar")
    duration = options.get("duration") or "month"
    if duration not in DURATIONS:
        raise ChallengeError("Elige una duración: una semana, un mes o tres meses")
    params = {"genre": name, "mode": mode, "duration": duration}
    if mode == "play":
        params["hours"] = hours(DEFAULT_HOURS if options.get("hours") in (None, "") else options["hours"], "Las horas")
    return Built(
        title=f"Probar un género: {name}"[:MAX_TITLE],
        params=params,
        starts_on=today,
        ends_on=today + datetime.timedelta(days=DURATIONS[duration] - 1),
    )


def new_genre_result(user_id: int, name: str, mode: str, amount: int, target_hours: float | None) -> dict:
    """The progress of a "try a genre" from what the player did in new games of that genre (pure): the seconds
    played ("play") or the games completed ("complete")."""
    if mode == "play":
        target = round(target_hours * 3600)
        player = {"user_id": user_id, "name": name, "seconds": amount, "target_seconds": target, "done": amount >= target}
    else:
        player = {"user_id": user_id, "name": name, "count": amount, "target_count": 1, "done": amount >= 1}
    return {"players": [player] if user_id is not None else []}


def progress_new_genre(db: Session, challenge: models.Challenge, participant_ids: list[int]) -> dict:
    """Only games of the genre the player did not have in their library before the challenge began count: a game
    that was already there is not something new to try."""
    if not participant_ids:
        return {"players": []}
    params = json.loads(challenge.params)
    user_id = participant_ids[0]
    user = db.get(models.User, user_id)
    genre = params["genre"].casefold()
    in_genre = lambda genres: genre in {g.casefold() for g in split_genres(genres)}  # noqa: E731
    had_before = {
        game_id for (game_id,) in db.query(models.UserGame.game_id).filter(models.UserGame.user_id == user_id, models.UserGame.started_date < challenge.starts_on)
    }
    if params["mode"] == "play":
        rows = (
            db.query(models.GameTimer.game_id, models.Game.genres, func.sum(models.GameTimer.duration_seconds))
            .join(models.Game, models.Game.id == models.GameTimer.game_id)
            .filter(
                models.GameTimer.user_id == user_id,
                models.GameTimer.is_active == False,  # noqa: E712
                models.GameTimer.start_time >= datetime.datetime.combine(challenge.starts_on, datetime.time.min),
                models.GameTimer.start_time < datetime.datetime.combine(challenge.ends_on + datetime.timedelta(days=1), datetime.time.min),
            )
            .group_by(models.GameTimer.game_id, models.Game.genres)
        )
        amount = sum(int(seconds or 0) for game_id, genres, seconds in rows if game_id not in had_before and in_genre(genres))
    else:
        rows = (
            db.query(models.UserGame.game_id, models.Game.genres)
            .join(models.Game, models.Game.id == models.UserGame.game_id)
            .filter(
                models.UserGame.user_id == user_id,
                models.UserGame.completed == 1,
                models.UserGame.completed_date >= challenge.starts_on,
                models.UserGame.completed_date <= challenge.ends_on,
            )
        )
        amount = len({game_id for game_id, genres in rows if game_id not in had_before and in_genre(genres)})
    return new_genre_result(user_id, (user.name or user.username) if user else "", params["mode"], amount, params.get("hours"))


# ── Temático ────────────────────────────────────────────────────

MAX_GAMES = 500


def build_themed(db: Session, options: dict, today: datetime.date) -> Built:
    """Options: tag (one that exists and has games), month ("YYYY-MM"), mode ("play" hours or "complete" a game),
    min_hours_each (play only) and, optionally, a total for the whole group: min_hours_total (play) or
    min_games_total (complete). Every game that has the tag counts."""
    tags = available_tags(db)
    wanted = str(options.get("tag") or "").strip().casefold()
    if wanted not in tags:
        raise ChallengeError("Elige una temática que exista")
    name = tags[wanted][0]
    starts_on, ends_on = month_period(options.get("month"))
    if ends_on < today:
        raise ChallengeError("Ese mes ya ha pasado")
    mode = options.get("mode")
    if mode not in ("play", "complete"):
        raise ChallengeError("Elige si hay que jugar o completar")
    params: dict = {"tag": name, "mode": mode}
    if mode == "play":
        each = hours(options.get("min_hours_each"), "El mínimo por jugador")
        params["min_hours_each"] = each
        if options.get("min_hours_total") not in (None, ""):
            total = hours(options["min_hours_total"], "El mínimo total")
            if total < each:
                raise ChallengeError("El mínimo total no puede ser menor que el de cada jugador")
            params["min_hours_total"] = total
    elif options.get("min_games_total") not in (None, ""):
        try:
            games = int(options["min_games_total"])
        except (ValueError, TypeError):
            raise ChallengeError("El total de juegos no es un número")
        if not 1 <= games <= MAX_GAMES:
            raise ChallengeError(f"El total de juegos debe estar entre 1 y {MAX_GAMES}")
        params["min_games_total"] = games
    return Built(title=f"Temático: {name}"[:MAX_TITLE], params=params, starts_on=starts_on, ends_on=ends_on)


def themed_result(names: dict[int, str], mode: str, amounts: dict[int, int], params: dict) -> dict:
    """The progress of a themed challenge from what each participant did in games with the tag (pure): seconds
    played ("play") or games completed ("complete"). The group's total is there only if the challenge has one."""
    if mode == "play":
        each = round(params["min_hours_each"] * 3600)
        players = [
            {"user_id": u, "name": n, "seconds": amounts.get(u, 0), "target_seconds": each, "done": amounts.get(u, 0) >= each}
            for u, n in names.items()
        ]
        players.sort(key=lambda p: (-p["seconds"], p["name"].lower()))
        result = {"players": players}
        if "min_hours_total" in params:
            target, seconds = round(params["min_hours_total"] * 3600), sum(p["seconds"] for p in players)
            result.update(total_seconds=seconds, total_target_seconds=target, total_done=bool(players) and seconds >= target)
    else:
        players = [
            {"user_id": u, "name": n, "count": amounts.get(u, 0), "target_count": 1, "done": amounts.get(u, 0) >= 1}
            for u, n in names.items()
        ]
        players.sort(key=lambda p: (-p["count"], p["name"].lower()))
        result = {"players": players}
        if "min_games_total" in params:
            count, target = sum(p["count"] for p in players), params["min_games_total"]
            result.update(total_count=count, total_target_count=target, total_done=bool(players) and count >= target)
    return result


def progress_themed(db: Session, challenge: models.Challenge, participant_ids: list[int]) -> dict:
    params = json.loads(challenge.params)
    names = {
        user_id: name or username
        for user_id, username, name in db.query(models.User.id, models.User.username, models.User.name).filter(models.User.id.in_(participant_ids))
    }
    tag = params["tag"].casefold()
    has_tag = lambda tags: tag in {t.casefold() for t in split_genres(tags)}  # noqa: E731
    amounts: dict[int, int] = {}
    if participant_ids and params["mode"] == "play":
        rows = (
            db.query(models.GameTimer.user_id, models.Game.tags, func.sum(models.GameTimer.duration_seconds))
            .join(models.Game, models.Game.id == models.GameTimer.game_id)
            .filter(
                models.GameTimer.user_id.in_(participant_ids),
                models.GameTimer.is_active == False,  # noqa: E712
                models.GameTimer.start_time >= datetime.datetime.combine(challenge.starts_on, datetime.time.min),
                models.GameTimer.start_time < datetime.datetime.combine(challenge.ends_on + datetime.timedelta(days=1), datetime.time.min),
            )
            .group_by(models.GameTimer.user_id, models.Game.tags)
        )
        for user_id, tags, seconds in rows:
            if has_tag(tags):
                amounts[user_id] = amounts.get(user_id, 0) + int(seconds or 0)  # MariaDB returns SUM() as Decimal
    elif participant_ids:
        rows = (
            db.query(models.UserGame.user_id, models.UserGame.game_id, models.Game.tags)
            .join(models.Game, models.Game.id == models.UserGame.game_id)
            .filter(
                models.UserGame.user_id.in_(participant_ids),
                models.UserGame.completed == 1,
                models.UserGame.completed_date >= challenge.starts_on,
                models.UserGame.completed_date <= challenge.ends_on,
            )
        )
        done: dict[int, set] = {}
        for user_id, game_id, tags in rows:
            if has_tag(tags):
                done.setdefault(user_id, set()).add(game_id)
        amounts = {user_id: len(games) for user_id, games in done.items()}
    return themed_result(names, params["mode"], amounts, params)


def summary_themed(challenge: models.Challenge) -> str:
    params = json.loads(challenge.params)
    period = f"del {spanish_date(challenge.starts_on)} al {spanish_date(challenge.ends_on)}"
    if params["mode"] == "play":
        total = f" y {hours_text(params['min_hours_total'])} h entre todos" if "min_hours_total" in params else ""
        return f"Jugar al menos {hours_text(params['min_hours_each'])} h a juegos de {params['tag']}, cada uno{total}, {period}."
    total = f" (y {params['min_games_total']} entre todos)" if "min_games_total" in params else ""
    return f"Completar al menos un juego de {params['tag']}{total}, {period}."


def reached_themed(challenge: models.Challenge, progress: dict) -> str:
    params = json.loads(challenge.params)
    done = sum(1 for p in progress["players"] if p["done"])
    what = f"las {hours_text(params['min_hours_total'])} h" if params["mode"] == "play" else f"los {params['min_games_total']} juegos completados"
    return f"Entre todos habéis llegado a {what} de {params['tag']}. {done} de {len(progress['players'])} ya habéis cumplido vuestra parte."


TEMPLATES: dict[str, Template] = {
    "game_of_month": Template("Juego del mes", GROUP, build_game_of_month, progress_game_of_month, summary_game_of_month, reached_game_of_month),
    "themed": Template("Temático", GROUP, build_themed, progress_themed, summary_themed, reached_themed),
    "new_genre": Template("Probar un género", USER, build_new_genre, progress_new_genre),
}
