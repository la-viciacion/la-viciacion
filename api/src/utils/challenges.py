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
from . import streaks, themes

GROUP = "group"
USER = "user"
DUEL = "duel"

MAX_HOURS = 5000
MAX_TITLE = 120

AUTO = "auto"  # every active player takes part and may leave
OPT_IN = "opt_in"  # only who joins takes part
PARTICIPATIONS = (AUTO, OPT_IN)
# The group templates a player may propose and an admin may schedule: the ones whose options are the same every time
# (a month and, for the game of the month, a game)
GROUP_OPTIONS = ("game_id", "month", "starts_on", "ends_on", "min_hours_each", "min_hours_total", "theme", "tag", "mode", "min_games_total", "versus")
PROPOSABLE = ("game_of_month", "themed")


class ChallengeError(ValueError):
    """The options of a challenge are not valid (the message is shown to whoever launched it)."""


class ChallengeConflict(ChallengeError):
    """The challenge, proposal or schedule is valid but clashes with what already exists (an answer 409)."""


def clean_options(options: dict | None) -> dict:
    """Only the options a group template knows, whatever else was sent (a player's proposal and a schedule are stored)."""
    return {key: value for key, value in (options or {}).items() if key in GROUP_OPTIONS and value is not None}


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
    scope: str  # GROUP: launched by an admin for everybody; USER: by a player for themselves; DUEL: by a player against another
    build: Callable[[Session, dict, datetime.date, int | None], Built]  # (db, options, today, whoever launches it)
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


MAX_PERIOD_DAYS = 366


def _day(value, name: str) -> datetime.date:
    try:
        return datetime.date.fromisoformat(str(value))
    except ValueError:
        raise ChallengeError(f"{name} no es una fecha válida")


def group_period(options: dict, today: datetime.date) -> tuple[datetime.date, datetime.date]:
    """The period of a group challenge: free dates (`starts_on` and `ends_on`, both inclusive) or, without them, the
    whole `month`. It may begin in the future (the challenge is then upcoming and can be joined) or have begun already,
    but not be over."""
    if options.get("starts_on") or options.get("ends_on"):
        starts_on, ends_on = _day(options.get("starts_on"), "La fecha de inicio"), _day(options.get("ends_on"), "La fecha de fin")
        if ends_on < starts_on:
            raise ChallengeError("El reto no puede terminar antes de empezar")
        if (ends_on - starts_on).days + 1 > MAX_PERIOD_DAYS:
            raise ChallengeError(f"El reto no puede durar más de {MAX_PERIOD_DAYS} días")
        if ends_on < today:
            raise ChallengeError("Ese periodo ya ha pasado")
        return starts_on, ends_on
    starts_on, ends_on = month_period(options.get("month"))
    if ends_on < today:
        raise ChallengeError("Ese mes ya ha pasado")
    return starts_on, ends_on


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


def month_start(day: datetime.date) -> datetime.date:
    """The first day of the month of a day."""
    return day.replace(day=1)


def next_month(day: datetime.date) -> datetime.date:
    """The first day of the month after the one of `day`."""
    return (day.replace(day=1) + datetime.timedelta(days=31)).replace(day=1)


def months_between(first: datetime.date, later: datetime.date) -> int:
    """Whole months from the month of `first` to the month of `later` (negative if it is before)."""
    return (later.year - first.year) * 12 + later.month - first.month


def fingerprint(kind: str, built: Built, owner_user_id: int | None, participation: str = AUTO) -> str:
    """What makes two challenges the same: the template, its options, the period, whose it is and, when it is not the
    usual one, who takes part (an old challenge keeps the fingerprint it had)."""
    canonical = json.dumps(
        [kind, built.params, built.game_id, built.starts_on.isoformat(), built.ends_on.isoformat(), owner_user_id]
        + ([participation] if participation != AUTO else []),
        sort_keys=True, ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ── Juego del mes ───────────────────────────────────────────────


def _versus(options: dict) -> dict:
    """{"versus": True} when a group challenge is also a contest (who got furthest is ranked), nothing otherwise."""
    return {"versus": True} if options.get("versus") in (True, "true", 1) else {}


def build_game_of_month(db: Session, options: dict, today: datetime.date, user_id: int | None = None) -> Built:
    """Options: game_id, month ("YYYY-MM") or starts_on and ends_on, min_hours_each, min_hours_total."""
    game = db.get(models.Game, str(options.get("game_id") or ""))
    if game is None:
        raise ChallengeError("Elige un juego que exista")
    starts_on, ends_on = group_period(options, today)
    each = hours(options.get("min_hours_each"), "El mínimo por jugador")
    total = hours(options.get("min_hours_total"), "El mínimo total")
    if total < each:
        raise ChallengeError("El mínimo total no puede ser menor que el de cada jugador")
    return Built(
        title=f"Juego del mes: {game.name}"[:MAX_TITLE],
        params={"min_hours_each": each, "min_hours_total": total, **_versus(options)},
        starts_on=starts_on,
        ends_on=ends_on,
        game_id=game.id,
    )


def seconds_in_game(
    db: Session, user_ids: list[int], game_id: str, starts_on: datetime.date, ends_on: datetime.date, start: datetime.datetime | None = None
) -> dict[int, int]:
    """Seconds each user played a game in sessions that began within the period (finished ones only). `start` is the
    moment the period begins when it is not the first instant of `starts_on` (see `starts_at`)."""
    if not user_ids:
        return {}
    rows = (
        db.query(models.GameTimer.user_id, func.sum(models.GameTimer.duration_seconds))
        .filter(
            models.GameTimer.user_id.in_(user_ids),
            models.GameTimer.game_id == game_id,
            models.GameTimer.is_active == False,  # noqa: E712
            models.GameTimer.start_time >= (start or datetime.datetime.combine(starts_on, datetime.time.min)),
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
    names = names_of(db, participant_ids)
    played = seconds_in_game(db, participant_ids, challenge.game_id, challenge.starts_on, challenge.ends_on)
    return game_of_month_result(played, names, params["min_hours_each"], params["min_hours_total"])


def summary_game_of_month(challenge: models.Challenge) -> str:
    params = json.loads(challenge.params)
    return (
        f"Mínimo {hours_text(params['min_hours_each'])} h cada uno y {hours_text(params['min_hours_total'])} h entre todos, "
        f"del {spanish_date(challenge.starts_on)} al {spanish_date(challenge.ends_on)}."
        + (" Gana quien más juegue." if params.get("versus") else "")
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


def available_themes(db: Session) -> dict[str, tuple[str, int]]:
    """The themes (utils/themes.py) that have at least one game in the database: {lower-cased name: (name, how many games
    have any of its tags)}."""
    wanted = {name: {tag.casefold() for tag in tags} for name, tags in themes.THEMES.items()}
    counts = dict.fromkeys(themes.THEMES, 0)
    for (tags,) in db.query(models.Game.tags).filter(models.Game.tags.isnot(None), models.Game.tags != ""):
        owned = {tag.casefold() for tag in split_genres(tags)}
        for name, theme_tags in wanted.items():
            if owned & theme_tags:
                counts[name] += 1
    return {name.casefold(): (name, count) for name, count in counts.items() if count}


def themes_listing(db: Session) -> list[dict]:
    """What a form offers for a themed challenge: the themes with games, the one with the most games first."""
    return [{"theme": name, "games": count} for name, count in sorted(available_themes(db).values(), key=lambda item: (-item[1], item[0].casefold()))]


def build_new_genre(db: Session, options: dict, today: datetime.date, user_id: int | None = None) -> Built:
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
    after = played_after_launch(db, challenge, user_id)
    had_before = {
        game_id for game_id, started in db.query(models.UserGame.game_id, models.UserGame.started_date).filter(
            models.UserGame.user_id == user_id, models.UserGame.started_date <= challenge.starts_on
        )
        if started < challenge.starts_on or not counts_from_launch(challenge, started, game_id, after)
    }
    if params["mode"] == "play":
        rows = (
            db.query(models.GameTimer.game_id, models.Game.genres, func.sum(models.GameTimer.duration_seconds))
            .join(models.Game, models.Game.id == models.GameTimer.game_id)
            .filter(
                models.GameTimer.user_id == user_id,
                models.GameTimer.is_active == False,  # noqa: E712
                models.GameTimer.start_time >= starts_at(challenge),
                models.GameTimer.start_time < datetime.datetime.combine(challenge.ends_on + datetime.timedelta(days=1), datetime.time.min),
            )
            .group_by(models.GameTimer.game_id, models.Game.genres)
        )
        amount = sum(int(seconds or 0) for game_id, genres, seconds in rows if game_id not in had_before and in_genre(genres))
    else:
        rows = (
            db.query(models.UserGame.game_id, models.Game.genres, models.UserGame.completed_date)
            .join(models.Game, models.Game.id == models.UserGame.game_id)
            .filter(
                models.UserGame.user_id == user_id,
                models.UserGame.completed == 1,
                models.UserGame.completed_date >= challenge.starts_on,
                models.UserGame.completed_date <= challenge.ends_on,
            )
        )
        amount = len({
            game_id for game_id, genres, done_on in rows
            if game_id not in had_before and in_genre(genres) and counts_from_launch(challenge, done_on, game_id, after)
        })
    return new_genre_result(user_id, (user.name or user.username) if user else "", params["mode"], amount, params.get("hours"))


# ── Temático ────────────────────────────────────────────────────

MAX_GAMES = 500


def build_themed(db: Session, options: dict, today: datetime.date, user_id: int | None = None) -> Built:
    """Options: theme (one of utils/themes.py that has games), month ("YYYY-MM") or starts_on and ends_on, mode ("play"
    hours or "complete" a game), min_hours_each (play only) and, optionally, a total for the whole group: min_hours_total
    (play) or min_games_total (complete). Every game that has any of the tags of the theme counts, and the tags are
    written in the definition. `tag` (a single tag of the database) is what a theme was before: proposals and schedules
    made then still carry it and still launch."""
    if options.get("theme") not in (None, ""):
        found = available_themes(db).get(str(options["theme"]).strip().casefold())
        if found is None:
            raise ChallengeError("Elige una temática que exista")
        name = found[0]
        which: dict = {"theme": name, "tags": list(themes.THEMES[name])}
    else:
        tags = available_tags(db)
        wanted = str(options.get("tag") or "").strip().casefold()
        if wanted not in tags:
            raise ChallengeError("Elige una temática que exista")
        name = tags[wanted][0]
        which = {"tag": name}
    starts_on, ends_on = group_period(options, today)
    mode = options.get("mode")
    if mode not in ("play", "complete"):
        raise ChallengeError("Elige si hay que jugar o completar")
    params: dict = {**which, "mode": mode, **_versus(options)}
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


def themed_tags(params: dict) -> list[str]:
    """The tags a themed challenge counts a game for: those of its theme, or the single tag of an older one."""
    return params.get("tags") or [params["tag"]]


def themed_label(params: dict) -> str:
    """What a themed challenge is about, as the players read it."""
    return params.get("theme") or params["tag"]


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
    names = names_of(db, participant_ids)
    wanted = {tag.casefold() for tag in themed_tags(params)}
    has_tag = lambda tags: bool(wanted & {t.casefold() for t in split_genres(tags)})  # noqa: E731
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
        return f"Jugar al menos {hours_text(params['min_hours_each'])} h a juegos de {themed_label(params)}, cada uno{total}, {period}."
    total = f" (y {params['min_games_total']} entre todos)" if "min_games_total" in params else ""
    return f"Completar al menos un juego de {themed_label(params)}{total}, {period}."


def reached_themed(challenge: models.Challenge, progress: dict) -> str:
    params = json.loads(challenge.params)
    done = sum(1 for p in progress["players"] if p["done"])
    what = f"las {hours_text(params['min_hours_total'])} h" if params["mode"] == "play" else f"los {params['min_games_total']} juegos completados"
    return f"Entre todos habéis llegado a {what} de {themed_label(params)}. {done} de {len(progress['players'])} ya habéis cumplido vuestra parte."


# ── Bajar la deuda ──────────────────────────────────────────────


def _between(value, name: str, low: float, high: float) -> float:
    """A number within limits, to a tenth."""
    try:
        number = round(float(value), 1)
    except (ValueError, TypeError):
        raise ChallengeError(f"{name} no es un número")
    if not low <= number <= high:
        raise ChallengeError(f"{name} debe estar entre {low:g} y {high:g}")
    return number


def build_debt_reduction(db: Session, options: dict, today: datetime.date, user_id: int | None = None) -> Built:
    """Options: mode ("percent" of the debt the player has when it starts, or "games" of those to close), percent
    (1 to 100) or games (1 up to how many they have open), and duration ("week", "month" or "quarter"; it starts
    today). Only the games the player already had open count, so playing new ones neither helps nor hurts."""
    from ..crud import debt  # that module imports the ones that import this one

    mode = options.get("mode")
    if mode not in ("percent", "games"):
        raise ChallengeError("Elige si quieres saldar un porcentaje de la deuda o cerrar juegos")
    duration = options.get("duration") or "month"
    if duration not in DURATIONS:
        raise ChallengeError("Elige una duración: una semana, un mes o tres meses")
    open_games = debt.games_in_debt_at(db, user_id, today, datetime.datetime.now()) if user_id is not None else {}
    if not open_games:
        raise ChallengeError("No tienes juegos empezados y sin terminar: no hay deuda que saldar")
    params: dict = {"mode": mode, "duration": duration}
    if mode == "percent":
        if not any(open_games.values()):
            raise ChallengeError("Tus juegos empezados ya pasan de su tiempo medio: no te queda deuda que saldar")
        params["percent"] = _between(options.get("percent"), "El porcentaje", 1, 100)
        title = f"Bajar la deuda un {hours_text(params['percent'])} %"
    else:
        try:
            games = int(options.get("games"))
        except (ValueError, TypeError):
            raise ChallengeError("El número de juegos no es un número")
        if not 1 <= games <= len(open_games):
            raise ChallengeError(f"Tienes {len(open_games)} {'juego' if len(open_games) == 1 else 'juegos'} sin terminar: elige entre 1 y {len(open_games)}")
        params["games"] = games
        title = f"Cerrar {games} {'juego' if games == 1 else 'juegos'} de la deuda"
    return Built(title=title, params=params, starts_on=today, ends_on=today + datetime.timedelta(days=DURATIONS[duration] - 1))


def debt_reduction_result(user_id: int | None, name: str, params: dict, start_debt: dict[str, int], played: dict[str, int], completed: set[str]) -> dict:
    """The progress of a debt reduction (pure). `start_debt` is {game_id: seconds left} the player had when it began,
    `played` the seconds they played each of those games since and `completed` the ones they completed since.
    Percent: what was paid over what was owed, where a completed game pays all it had left and any other pays what
    was played, up to what it had left. Games: how many of them were completed. Abandoning pays nothing."""
    if user_id is None:
        return {"players": []}
    if params["mode"] == "percent":
        owed = sum(start_debt.values())
        paid = sum(left if game in completed else min(left, played.get(game, 0)) for game, left in start_debt.items())
        share = 100 * paid / owed if owed else 0.0
        player = {"user_id": user_id, "name": name, "percent": round(share, 1), "target_percent": params["percent"],
                  "paid_seconds": paid, "initial_seconds": owed, "done": owed > 0 and share >= params["percent"]}
    else:
        closed = len(completed & start_debt.keys())
        player = {"user_id": user_id, "name": name, "count": closed, "target_count": params["games"], "done": closed >= params["games"]}
    return {"players": [player]}


def progress_debt_reduction(db: Session, challenge: models.Challenge, participant_ids: list[int]) -> dict:
    from ..crud import debt  # that module imports the ones that import this one

    if not participant_ids:
        return {"players": []}
    user_id = participant_ids[0]
    user = db.get(models.User, user_id)
    start_debt = debt.games_in_debt_at(db, user_id, challenge.starts_on, starts_at(challenge))
    after = played_after_launch(db, challenge, user_id)
    window_start = starts_at(challenge)
    window_end = datetime.datetime.combine(challenge.ends_on + datetime.timedelta(days=1), datetime.time.min)
    played = {
        game_id: int(seconds or 0)  # MariaDB returns SUM() as Decimal
        for game_id, seconds in db.query(models.GameTimer.game_id, func.sum(models.GameTimer.duration_seconds))
        .filter(
            models.GameTimer.user_id == user_id,
            models.GameTimer.game_id.in_(list(start_debt)),
            models.GameTimer.is_active == False,  # noqa: E712
            models.GameTimer.start_time >= window_start,
            models.GameTimer.start_time < window_end,
        )
        .group_by(models.GameTimer.game_id)
    } if start_debt else {}
    completed = {
        game_id for game_id, done_on in db.query(models.UserGame.game_id, models.UserGame.completed_date).filter(
            models.UserGame.user_id == user_id,
            models.UserGame.completed == 1,
            models.UserGame.completed_date >= challenge.starts_on,
            models.UserGame.completed_date <= challenge.ends_on,
        )
        if counts_from_launch(challenge, done_on, game_id, after)
    } & set(start_debt)
    return debt_reduction_result(user_id, (user.name or user.username) if user else "", json.loads(challenge.params), start_debt, played, completed)


# ── Racha, sesiones largas, variedad y deseados (personal) ──────
# The count parts of these carry a `unit` (days, sessions, genres; games when it has none) that the front names.

def _duration(options: dict) -> tuple[str, int]:
    """The duration a personal challenge was asked for and how many days it covers."""
    duration = options.get("duration") or "month"
    if duration not in DURATIONS:
        raise ChallengeError("Elige una duración: una semana, un mes o tres meses")
    return duration, DURATIONS[duration]


def _whole(value, name: str, low: int, high: int) -> int:
    """A whole number within limits."""
    try:
        number = int(value)
        if isinstance(value, bool) or number != float(value):
            raise ValueError
    except (ValueError, TypeError):
        raise ChallengeError(f"{name} no es un número entero")
    if not low <= number <= high:
        raise ChallengeError(f"{name} debe estar entre {low} y {high}")
    return number


def starts_at(challenge: models.Challenge) -> datetime.datetime:
    """The moment a challenge begins to count: the first instant of its first day, except for a personal one or a duel,
    which count from the moment they were launched (what the player did earlier that day is not part of it)."""
    first = datetime.datetime.combine(challenge.starts_on, datetime.time.min)
    if challenge.scope == GROUP or challenge.created_at is None:
        return first
    return max(first, challenge.created_at)


def played_after_launch(db: Session, challenge: models.Challenge, user_id: int) -> set[str] | None:
    """The games the player has a session of that began after a personal challenge was launched, or None when the
    challenge counts its whole first day (a group one). A game started or completed is only a date, so on the day a
    personal challenge was launched it counts only if the player played it since: that is how it is told from what
    they did before. See `counts_from_launch`."""
    if challenge.scope == GROUP or challenge.created_at is None:
        return None
    return {
        game_id for (game_id,) in db.query(models.GameTimer.game_id).filter(
            models.GameTimer.user_id == user_id, models.GameTimer.start_time >= starts_at(challenge)
        ).distinct()
    }


def counts_from_launch(challenge: models.Challenge, day: datetime.date | None, game_id: str, after: set[str] | None) -> bool:
    """Whether a game started or completed on `day` (a date, with no hour) counts for the challenge: every day after the
    one it began does, and that day only when the game was played since the launch (`after`, from `played_after_launch`)."""
    if day is None or after is None or day != challenge.starts_on:
        return True
    return game_id in after


def _window(challenge: models.Challenge) -> tuple[datetime.datetime, datetime.datetime]:
    """The period as moments: from the moment it begins to count (`starts_at`) to the first one after its last day."""
    return (
        starts_at(challenge),
        datetime.datetime.combine(challenge.ends_on + datetime.timedelta(days=1), datetime.time.min),
    )


def names_of(db: Session, user_ids) -> dict[int, str]:
    """{user id: the name they go by} for those ids."""
    rows = db.query(models.User.id, models.User.username, models.User.name).filter(models.User.id.in_(list(user_ids)))
    return {user_id: name or username for user_id, username, name in rows}


def _player(db: Session, user_id: int) -> str:
    user = db.get(models.User, user_id)
    return (user.name or user.username) if user else ""


def _count_part(user_id: int, name: str, count: int, target: int, unit: str) -> dict:
    return {"players": [{"user_id": user_id, "name": name, "count": count, "target_count": target, "unit": unit, "done": count >= target}]}


def build_streak(db: Session, options: dict, today: datetime.date, user_id: int | None = None) -> Built:
    """Options: mode ("consecutive": a run of days in a row, or "days": different days), days (2 up to the length of
    the period) and duration ("week", "month" or "quarter"; it starts today). A played day is the one of the
    streaks and the achievements (a session of 10 minutes or more)."""
    mode = options.get("mode")
    if mode not in ("consecutive", "days"):
        raise ChallengeError("Elige si quieres jugar días seguidos o días distintos")
    duration, length = _duration(options)
    days = _whole(options.get("days"), "Los días", 2, length)
    return Built(
        title=f"Racha de {days} días" if mode == "consecutive" else f"Jugar {days} días distintos",
        params={"mode": mode, "days": days, "duration": duration},
        starts_on=today,
        ends_on=today + datetime.timedelta(days=length - 1),
    )


def streak_result(user_id: int, name: str, mode: str, target: int, played_days: list[datetime.date], last_day: datetime.date) -> dict:
    """The progress of a streak challenge from the days played within its period (pure, oldest first): the longest
    run of days in a row ("consecutive") or how many days there are ("days")."""
    count = streaks.streak_summary(played_days, last_day, last_day.year)[1] if mode == "consecutive" else len(played_days)
    return _count_part(user_id, name, count, target, "days")


def progress_streak(db: Session, challenge: models.Challenge, participant_ids: list[int]) -> dict:
    from ..crud import time_entries  # that module imports the ones that import this one

    if not participant_ids:
        return {"players": []}
    user_id = participant_ids[0]
    params = json.loads(challenge.params)
    within = time_entries.played_days_between(db, user_id, challenge.starts_on, challenge.ends_on, starts_at(challenge))
    return streak_result(user_id, _player(db, user_id), params["mode"], params["days"], within, challenge.ends_on)


def build_long_sessions(db: Session, options: dict, today: datetime.date, user_id: int | None = None) -> Built:
    """Options: sessions (how many, 1 to 100), minutes (each lasts at least that, 15 to 600) and duration."""
    duration, length = _duration(options)
    count = _whole(options.get("sessions"), "Las sesiones", 1, 100)
    minutes = _whole(options.get("minutes"), "Los minutos", 15, 600)
    return Built(
        title=f"{count} {'sesión' if count == 1 else 'sesiones'} de {minutes} min o más",
        params={"sessions": count, "minutes": minutes, "duration": duration},
        starts_on=today,
        ends_on=today + datetime.timedelta(days=length - 1),
    )


def progress_long_sessions(db: Session, challenge: models.Challenge, participant_ids: list[int]) -> dict:
    if not participant_ids:
        return {"players": []}
    user_id = participant_ids[0]
    params = json.loads(challenge.params)
    start, end = _window(challenge)
    count = (
        db.query(func.count(models.GameTimer.id))
        .filter(
            models.GameTimer.user_id == user_id,
            models.GameTimer.is_active == False,  # noqa: E712
            models.GameTimer.duration_seconds >= params["minutes"] * 60,
            models.GameTimer.start_time >= start,
            models.GameTimer.start_time < end,
        )
        .scalar()
    )
    return _count_part(user_id, _player(db, user_id), int(count or 0), params["sessions"], "sessions")


def build_variety(db: Session, options: dict, today: datetime.date, user_id: int | None = None) -> Built:
    """Options: genres (how many different ones, 2 to 10 and no more than the database has), hours (at least that
    many in each, 1 by default) and duration. The time of a game counts in each of its genres."""
    duration, length = _duration(options)
    existing = len(available_genres(db))
    if existing < 2:
        raise ChallengeError("Todavía no hay géneros suficientes en la base de datos")
    count = _whole(options.get("genres"), "Los géneros", 2, min(10, existing))
    each = hours(1 if options.get("hours") in (None, "") else options["hours"], "Las horas de cada género")
    return Built(
        title=f"Variar de género: {count} géneros",
        params={"genres": count, "hours": each, "duration": duration},
        starts_on=today,
        ends_on=today + datetime.timedelta(days=length - 1),
    )


def genres_reached(seconds_by_genres: list[tuple[str | None, int]], minimum_seconds: int) -> int:
    """How many genres got at least `minimum_seconds` (pure): the rows are the seconds played in games with that
    comma separated list of genres, and a game's time counts in each of its genres."""
    per_genre: dict[str, int] = {}
    for genres, seconds in seconds_by_genres:
        for genre in {g.casefold() for g in split_genres(genres)}:
            per_genre[genre] = per_genre.get(genre, 0) + seconds
    return sum(1 for seconds in per_genre.values() if seconds >= minimum_seconds)


def progress_variety(db: Session, challenge: models.Challenge, participant_ids: list[int]) -> dict:
    if not participant_ids:
        return {"players": []}
    user_id = participant_ids[0]
    params = json.loads(challenge.params)
    start, end = _window(challenge)
    rows = (
        db.query(models.Game.genres, func.sum(models.GameTimer.duration_seconds))
        .join(models.Game, models.Game.id == models.GameTimer.game_id)
        .filter(
            models.GameTimer.user_id == user_id,
            models.GameTimer.is_active == False,  # noqa: E712
            models.GameTimer.start_time >= start,
            models.GameTimer.start_time < end,
        )
        .group_by(models.Game.genres)
    )
    seconds = [(genres, int(total or 0)) for genres, total in rows]  # MariaDB returns SUM() as Decimal
    return _count_part(user_id, _player(db, user_id), genres_reached(seconds, round(params["hours"] * 3600)), params["genres"], "genres")


def wishes_at(db: Session, user_id: int, day: datetime.date, at: datetime.datetime | None = None, after: set[str] | None = None) -> set[str]:
    """The games a player was waiting to play on a day: those on their wishlist by then (added that day or before)
    that were not in their library yet. With `at` (the moment a personal challenge was launched on `day`) they are the
    wishes added by then, and a game started that day was already in the library only if it has not been played since
    (`after`, from `played_after_launch`)."""
    started = db.query(models.UserGame.game_id, models.UserGame.started_date).filter(
        models.UserGame.user_id == user_id, models.UserGame.started_date <= day
    )
    had = {game_id for game_id, on in started if on < day or after is None or game_id not in after}
    added = models.UserWishlist.added_at <= at if at is not None else models.UserWishlist.added_at < datetime.datetime.combine(day + datetime.timedelta(days=1), datetime.time.min)
    rows = db.query(models.UserWishlist.game_id).filter(models.UserWishlist.user_id == user_id, added)
    return {game_id for (game_id,) in rows if game_id not in had}


def build_wishlist(db: Session, options: dict, today: datetime.date, user_id: int | None = None) -> Built:
    """Options: mode ("start" playing or "complete"), games (1 up to the wishes they have pending) and duration.
    Only the games they were already waiting to play the day it begins count."""
    mode = options.get("mode")
    if mode not in ("start", "complete"):
        raise ChallengeError("Elige si quieres empezar o completar tus deseados")
    duration, length = _duration(options)
    pending = len(wishes_at(db, user_id, today, datetime.datetime.now())) if user_id is not None else 0
    if not pending:
        raise ChallengeError("No tienes deseados pendientes: añade juegos a tu lista de deseados primero")
    games = _whole(options.get("games"), "Los juegos", 1, pending)
    verb = "Empezar" if mode == "start" else "Completar"
    return Built(
        title=f"{verb} {games} {'deseado' if games == 1 else 'deseados'}",
        params={"mode": mode, "games": games, "duration": duration},
        starts_on=today,
        ends_on=today + datetime.timedelta(days=length - 1),
    )


def progress_wishlist(db: Session, challenge: models.Challenge, participant_ids: list[int]) -> dict:
    """The wishes the player had the day it began (`wishes_at`) that they have started (the `started_date`
    of the entry) or completed (its `completed_date`) within the period. A wish they remove from the list afterwards
    stops counting, like any figure derived from what is there."""
    if not participant_ids:
        return {"players": []}
    user_id = participant_ids[0]
    params = json.loads(challenge.params)
    after = played_after_launch(db, challenge, user_id)
    wished = wishes_at(db, user_id, challenge.starts_on, starts_at(challenge), after)
    found = set()
    if wished:
        rows = db.query(models.UserGame.game_id, models.UserGame.started_date, models.UserGame.completed_date).filter(
            models.UserGame.user_id == user_id, models.UserGame.game_id.in_(wished)
        )
        if params["mode"] == "start":
            rows = rows.filter(models.UserGame.started_date >= challenge.starts_on, models.UserGame.started_date <= challenge.ends_on)
        else:
            rows = rows.filter(models.UserGame.completed == 1, models.UserGame.completed_date >= challenge.starts_on, models.UserGame.completed_date <= challenge.ends_on)
        found = {
            game_id for game_id, started, done_on in rows
            if counts_from_launch(challenge, started if params["mode"] == "start" else done_on, game_id, after)
        }
    return _count_part(user_id, _player(db, user_id), len(found), params["games"], "games")


# ── Versus: who got further ─────────────────────────────────────


def part_value(part: dict) -> float:
    """What a part has reached, whatever it counts (seconds, games or a share of the debt)."""
    return part.get("seconds", part.get("count", part.get("percent", 0)))


def rank_players(players: list[dict]) -> list[dict]:
    """Give each part a `position` (1 is the best; those with the same amount share it) and a `winner` flag (first and
    with something done), in place and in the order they come (pure). It is what a versus challenge shows: it ranks
    what each one has reached, so it can be read while the challenge runs and is final when it ends."""
    values = sorted({part_value(p) for p in players}, reverse=True)
    for part in players:
        part["position"] = values.index(part_value(part)) + 1
        part["winner"] = part["position"] == 1 and part_value(part) > 0
    return players


# ── Duelo (1 vs 1) ──────────────────────────────────────────────

DECLINE_HOURS = 48  # how long the challenged player has to decline it, counting from its launch


def _opponent(db: Session, options: dict, user_id: int | None) -> int:
    try:
        opponent_id = int(options.get("opponent_id"))
    except (ValueError, TypeError):
        raise ChallengeError("Elige a quién retar")
    if opponent_id == user_id:
        raise ChallengeError("No puedes retarte a ti mismo")
    opponent = db.get(models.User, opponent_id)
    if opponent is None or not opponent.is_active or opponent.username == models.GOD_USERNAME:
        raise ChallengeError("Elige a un jugador activo")
    return opponent_id


def build_duel_hours(db: Session, options: dict, today: datetime.date, user_id: int | None = None) -> Built:
    """Options: opponent_id (another active player) and duration ("week", "month" or "quarter"; it starts today).
    Whoever plays more hours, of any game, in sessions that began within the period wins."""
    duration, length = _duration(options)
    return Built(
        title="Duelo de horas",
        params={"opponent_id": _opponent(db, options, user_id), "duration": duration},
        starts_on=today,
        ends_on=today + datetime.timedelta(days=length - 1),
    )


def build_duel_game(db: Session, options: dict, today: datetime.date, user_id: int | None = None) -> Built:
    """Like `build_duel_hours` (plus game_id: a game of the catalogue), but only the hours of that game count."""
    duration, length = _duration(options)
    game = db.get(models.Game, str(options.get("game_id") or ""))
    if game is None:
        raise ChallengeError("Elige un juego que exista")
    return Built(
        title=f"Duelo en {game.name}"[:MAX_TITLE],
        params={"opponent_id": _opponent(db, options, user_id), "duration": duration},
        starts_on=today,
        ends_on=today + datetime.timedelta(days=length - 1),
        game_id=game.id,
    )


def build_duel_completed(db: Session, options: dict, today: datetime.date, user_id: int | None = None) -> Built:
    """Like `build_duel_hours`, but whoever completes more games within the period wins."""
    duration, length = _duration(options)
    return Built(
        title="Duelo de completados",
        params={"opponent_id": _opponent(db, options, user_id), "duration": duration},
        starts_on=today,
        ends_on=today + datetime.timedelta(days=length - 1),
    )


def duel_result(names: dict[int, str], amounts: dict[int, int], counted: bool = False) -> dict:
    """The progress of a duel from what each of the two reached (pure): the seconds they played or, if `counted`, the
    games they completed. Each part carries the leader's amount as its target, so the bar shows how far behind it is;
    whoever reaches more wins and a tie with something done is won by both."""
    leader = max(amounts.values(), default=0)
    key = "count" if counted else "seconds"
    players = [
        {"user_id": user_id, "name": name, key: amounts.get(user_id, 0), f"target_{key}": leader, "versus": True, **({"unit": "games"} if counted else {})}
        for user_id, name in names.items()
    ]
    rank_players(players)
    for part in players:
        part["done"] = part["winner"]
    players.sort(key=lambda p: (p["position"], p["name"].lower()))
    return {"players": players}


def progress_duel(db: Session, challenge: models.Challenge, participant_ids: list[int]) -> dict:
    names = names_of(db, participant_ids)
    if challenge.game_id:
        played = seconds_in_game(db, participant_ids, challenge.game_id, challenge.starts_on, challenge.ends_on, starts_at(challenge))
    else:
        played = seconds_of_players(db, participant_ids, *_window(challenge))
    return duel_result(names, played)


def completed_games(db: Session, challenge: models.Challenge, user_id: int, among: set[str] | None = None) -> dict[str, datetime.date]:
    """{game_id: the day the player completed it first} for the games completed within the challenge's period (those
    in `among`, if given), counting a completion on the launch day only when the game was played since (see
    `counts_from_launch`)."""
    after = played_after_launch(db, challenge, user_id)
    rows = db.query(models.UserGame.game_id, models.UserGame.completed_date).filter(
        models.UserGame.user_id == user_id,
        models.UserGame.completed == 1,
        models.UserGame.completed_date >= challenge.starts_on,
        models.UserGame.completed_date <= challenge.ends_on,
    )
    found: dict[str, datetime.date] = {}
    for game_id, done_on in rows:
        if (among is None or game_id in among) and counts_from_launch(challenge, done_on, game_id, after):
            found[game_id] = min(done_on, found.get(game_id, done_on))
    return found


def progress_duel_completed(db: Session, challenge: models.Challenge, participant_ids: list[int]) -> dict:
    names = names_of(db, participant_ids)
    return duel_result(names, {user_id: len(completed_games(db, challenge, user_id)) for user_id in participant_ids}, counted=True)


# ── Horas entre todos (grupo) ───────────────────────────────────


def seconds_of_players(db: Session, user_ids: list[int], start: datetime.datetime, end: datetime.datetime) -> dict[int, int]:
    """Seconds each user played, of any game, in finished sessions that began within [start, end)."""
    if not user_ids:
        return {}
    rows = (
        db.query(models.GameTimer.user_id, func.sum(models.GameTimer.duration_seconds))
        .filter(
            models.GameTimer.user_id.in_(user_ids),
            models.GameTimer.is_active == False,  # noqa: E712
            models.GameTimer.start_time >= start,
            models.GameTimer.start_time < end,
        )
        .group_by(models.GameTimer.user_id)
    )
    return {user_id: int(seconds or 0) for user_id, seconds in rows}  # MariaDB returns SUM() as Decimal


def build_group_hours(db: Session, options: dict, today: datetime.date, user_id: int | None = None) -> Built:
    """Options: month ("YYYY-MM") or starts_on and ends_on, and min_hours_total: the hours the whole group has to play
    between everybody, of any game. Nobody has a minimum of their own."""
    starts_on, ends_on = group_period(options, today)
    total = hours(options.get("min_hours_total"), "El total")
    return Built(
        title=f"Sumar {hours_text(total)} h entre todos",
        params={"min_hours_total": total, **_versus(options)},
        starts_on=starts_on,
        ends_on=ends_on,
    )


def group_hours_result(played: dict[int, int], names: dict[int, str], total_hours: float) -> dict:
    """The progress of "hours between everybody" from what each participant played (pure). A part is the share each one
    put in (its bar is against the group's total); a player meets theirs when the group reaches the total and they
    put something in, so being there without playing is not enough."""
    target = round(total_hours * 3600)
    seconds = sum(played.get(user_id, 0) for user_id in names)
    reached = bool(names) and seconds >= target
    players = [
        {"user_id": user_id, "name": name, "seconds": played.get(user_id, 0), "target_seconds": target, "contribution": True,
         "done": reached and played.get(user_id, 0) > 0}
        for user_id, name in names.items()
    ]
    players.sort(key=lambda p: (-p["seconds"], p["name"].lower()))
    return {"players": players, "total_seconds": seconds, "total_target_seconds": target, "total_done": reached}


def progress_group_hours(db: Session, challenge: models.Challenge, participant_ids: list[int]) -> dict:
    played = seconds_of_players(db, participant_ids, *_window(challenge))
    return group_hours_result(played, names_of(db, participant_ids), json.loads(challenge.params)["min_hours_total"])


def summary_group_hours(challenge: models.Challenge) -> str:
    params = json.loads(challenge.params)
    return (
        f"Jugar {hours_text(params['min_hours_total'])} h entre todos, a lo que sea, del {spanish_date(challenge.starts_on)} al {spanish_date(challenge.ends_on)}."
        + (" Gana quien más juegue." if params.get("versus") else "")
    )


def reached_group_hours(challenge: models.Challenge, progress: dict) -> str:
    contributed = sum(1 for p in progress["players"] if p["seconds"] > 0)
    return f"Entre todos habéis llegado a las {hours_text(json.loads(challenge.params)['min_hours_total'])} h. Han aportado {contributed} de {len(progress['players'])}."


# ── Terminar lo empezado y Terminar antes de empezar (personal) ─


def open_games_for(db: Session, challenge: models.Challenge, user_id: int) -> set[str]:
    """The games the player had started and not finished or abandoned when the challenge began (`debt.open_games_at`)."""
    from ..crud import debt  # that module imports the ones that import this one

    return debt.open_games_at(db, user_id, challenge.starts_on, starts_at(challenge))


def build_finish_backlog(db: Session, options: dict, today: datetime.date, user_id: int | None = None) -> Built:
    """Options: games (1 up to how many the player has started and not finished) and duration. Completing one of
    those games counts; the games started afterwards do not."""
    from ..crud import debt  # that module imports the ones that import this one

    duration, length = _duration(options)
    open_games = len(debt.open_games_at(db, user_id, today, datetime.datetime.now())) if user_id is not None else 0
    if not open_games:
        raise ChallengeError("No tienes juegos empezados y sin terminar")
    games = _whole(options.get("games"), "Los juegos", 1, open_games)
    return Built(
        title=f"Terminar {games} {'juego empezado' if games == 1 else 'juegos empezados'}",
        params={"games": games, "duration": duration},
        starts_on=today,
        ends_on=today + datetime.timedelta(days=length - 1),
    )


def progress_finish_backlog(db: Session, challenge: models.Challenge, participant_ids: list[int]) -> dict:
    if not participant_ids:
        return {"players": []}
    user_id = participant_ids[0]
    done = completed_games(db, challenge, user_id, open_games_for(db, challenge, user_id))
    return _count_part(user_id, _player(db, user_id), len(done), json.loads(challenge.params)["games"], "games")


def build_finish_first(db: Session, options: dict, today: datetime.date, user_id: int | None = None) -> Built:
    """Options: duration. The player must have a game started and not finished: they win by completing one of the
    games they have open before starting any new game, and lose the moment they start a new one first."""
    from ..crud import debt  # that module imports the ones that import this one

    duration, length = _duration(options)
    if user_id is None or not debt.open_games_at(db, user_id, today, datetime.datetime.now()):
        raise ChallengeError("No tienes juegos empezados y sin terminar: no hay nada que terminar antes de empezar otro")
    return Built(
        title="Terminar antes de empezar otro",
        params={"duration": duration},
        starts_on=today,
        ends_on=today + datetime.timedelta(days=length - 1),
    )


def finish_first_result(user_id: int, name: str, completed_on: list[datetime.date], started_on: list[datetime.date]) -> dict:
    """The progress of "finish before starting" (pure) from the days the player completed a game they had open and
    the days they started a new one, both within the period. They win with the first completion unless a new game was
    started on an earlier day; if one was, they have lost, and completing a game afterwards does not undo it. Only the
    day is known, so on the same day the completion comes first (the benefit of the doubt)."""
    first_completed = min(completed_on, default=None)
    first_started = min(started_on, default=None)
    failed = first_started is not None and (first_completed is None or first_started < first_completed)
    done = first_completed is not None and not failed
    return {"players": [{"user_id": user_id, "name": name, "count": int(done), "target_count": 1, "unit": "games", "done": done, "failed": failed}]}


def progress_finish_first(db: Session, challenge: models.Challenge, participant_ids: list[int]) -> dict:
    """A new game is one the player started within the period (the `started_date` of an entry) that they did not have
    in their library before it: a game they already had, in another season or on another platform, is not new."""
    if not participant_ids:
        return {"players": []}
    user_id = participant_ids[0]
    after = played_after_launch(db, challenge, user_id)
    entries = db.query(models.UserGame.game_id, models.UserGame.started_date).filter(
        models.UserGame.user_id == user_id, models.UserGame.started_date <= challenge.ends_on
    ).all()
    is_new = lambda game_id, on: on >= challenge.starts_on and counts_from_launch(challenge, on, game_id, after)  # noqa: E731
    had_before = {game_id for game_id, on in entries if not is_new(game_id, on)}
    started_on = [on for game_id, on in entries if is_new(game_id, on) and game_id not in had_before]
    completed = completed_games(db, challenge, user_id, open_games_for(db, challenge, user_id))
    return finish_first_result(user_id, _player(db, user_id), list(completed.values()), started_on)


TEMPLATES: dict[str, Template] = {
    "game_of_month": Template("Juego del mes", GROUP, build_game_of_month, progress_game_of_month, summary_game_of_month, reached_game_of_month),
    "themed": Template("Temático", GROUP, build_themed, progress_themed, summary_themed, reached_themed),
    "group_hours": Template("Horas entre todos", GROUP, build_group_hours, progress_group_hours, summary_group_hours, reached_group_hours),
    "finish_backlog": Template("Terminar lo empezado", USER, build_finish_backlog, progress_finish_backlog),
    "finish_first": Template("Terminar antes de empezar", USER, build_finish_first, progress_finish_first),
    "new_genre": Template("Probar un género", USER, build_new_genre, progress_new_genre),
    "debt_reduction": Template("Bajar la deuda", USER, build_debt_reduction, progress_debt_reduction),
    "streak": Template("Racha", USER, build_streak, progress_streak),
    "long_sessions": Template("Sesiones largas", USER, build_long_sessions, progress_long_sessions),
    "variety": Template("Variar de género", USER, build_variety, progress_variety),
    "wishlist": Template("Cumplir deseados", USER, build_wishlist, progress_wishlist),
    "duel_hours": Template("Duelo de horas", DUEL, build_duel_hours, progress_duel),
    "duel_game": Template("Duelo en un juego", DUEL, build_duel_game, progress_duel),
    "duel_completed": Template("Duelo de completados", DUEL, build_duel_completed, progress_duel_completed),
}
