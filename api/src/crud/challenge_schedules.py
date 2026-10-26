"""Group challenges that launch themselves every month. A schedule is a definition (a themed challenge, or a game of the
month whose game rotates along a list); `launch_due` makes the challenge of the running month, once. Which game it is
each month is worked out from the list and the position of the month, never stored."""
import datetime
import json

from sqlalchemy.orm import Session

from ..database import models
from ..utils import challenges
from ..utils.challenges import ChallengeError
from . import challenges as challenges_crud

MAX_GAMES = 24  # games in a rotation
MAX_LABEL = 80
SCHEDULABLE = challenges.PROPOSABLE


def month_text(month: datetime.date) -> str:
    return f"{month.year:04d}-{month.month:02d}"


def rotating_game(games: list[str], first_month: datetime.date, month: datetime.date) -> str:
    """The game of a month in a rotation that began in `first_month` (pure): the list in order, and round again."""
    return games[challenges.months_between(first_month, month) % len(games)]


def options_for(schedule: models.ChallengeSchedule, month: datetime.date) -> dict:
    """What the challenge of a month is launched with."""
    options = {**json.loads(schedule.options), "month": month_text(month)}
    if schedule.games:
        options["game_id"] = rotating_game(json.loads(schedule.games), schedule.first_month, month)
    return options


def _games(db: Session, kind: str, games) -> list[str] | None:
    """The rotation of a game of the month (distinct games that exist, in order); the other kinds have none."""
    if kind != "game_of_month":
        return None
    if not isinstance(games, list) or not games:
        raise ChallengeError("Elige al menos un juego para la rotación")
    ids = list(dict.fromkeys(str(game) for game in games))
    if len(ids) > MAX_GAMES:
        raise ChallengeError(f"La rotación admite como mucho {MAX_GAMES} juegos")
    found = {game_id for (game_id,) in db.query(models.Game.id).filter(models.Game.id.in_(ids))}
    missing = [game_id for game_id in ids if game_id not in found]
    if missing:
        raise ChallengeError("Hay juegos de la rotación que no existen")
    return ids


def _label(value) -> str:
    label = str(value or "").strip()
    if not label or len(label) > MAX_LABEL:
        raise ChallengeError(f"El nombre es obligatorio y no puede pasar de {MAX_LABEL} caracteres")
    return label


def _check(db: Session, kind: str, options: dict, games: list[str] | None, participation: str, today: datetime.date) -> None:
    """Try the challenge of the running month, as it would launch, so a schedule that cannot work is refused now."""
    if participation not in challenges.PARTICIPATIONS:
        raise ChallengeError("La participación debe ser de todos o voluntaria")
    launch = {**options, "month": month_text(challenges.month_start(today))}
    if games:
        launch["game_id"] = games[0]
    challenges.TEMPLATES[kind].build(db, launch, today, None)


def create(db: Session, admin: models.User, body: dict, today: datetime.date) -> models.ChallengeSchedule:
    """Define a schedule. `body`: label, kind, the options of the template (without month and game), games (a game of
    the month), participation, announce and start_now (the running month counts; otherwise it starts next month).
    Raises ChallengeError if it could not be launched."""
    kind = body.get("kind")
    if kind not in SCHEDULABLE:
        raise ChallengeError("Solo se pueden programar retos de juego del mes o temáticos")
    options = {key: value for key, value in challenges.clean_options(body).items() if key not in ("month", "game_id")}
    games = _games(db, kind, body.get("games"))
    participation = body.get("participation") or challenges.AUTO
    _check(db, kind, options, games, participation, today)
    first = challenges.month_start(today) if body.get("start_now") else challenges.next_month(today)
    schedule = models.ChallengeSchedule(
        label=_label(body.get("label")), kind=kind, options=json.dumps(options, ensure_ascii=False),
        games=json.dumps(games) if games else None, participation=participation, announce=bool(body.get("announce")),
        active=True, first_month=first, created_by=admin.id,
    )
    db.add(schedule)
    db.commit()
    return schedule


def update(db: Session, schedule: models.ChallengeSchedule, body: dict, today: datetime.date) -> models.ChallengeSchedule:
    """Change the label, whether it is active, whether it announces, who takes part and, for a game of the month, the
    list of games (the rotation goes on from the month it is at, so changing the list changes the next game). The
    options of the template are not editable: define another schedule."""
    games = json.loads(schedule.games) if schedule.games else None
    if "games" in body and body["games"] is not None:
        games = _games(db, schedule.kind, body["games"])
    participation = body.get("participation") or schedule.participation
    if participation != schedule.participation or ("games" in body and body["games"] is not None):
        # only what decides the launch is tried again: pausing or renaming a schedule whose game was deleted must work
        _check(db, schedule.kind, json.loads(schedule.options), games, participation, today)
    if "label" in body and body["label"] is not None:
        schedule.label = _label(body["label"])
    for key in ("active", "announce"):
        if body.get(key) is not None:
            setattr(schedule, key, bool(body[key]))
    schedule.participation = participation
    schedule.games = json.dumps(games) if games else None
    db.commit()
    return schedule


def launch_due(db: Session, schedule: models.ChallengeSchedule, today: datetime.date) -> models.Challenge | None:
    """Launch the challenge of the running month if the schedule is active, has begun and has not done it yet; None
    otherwise. The month is marked done whatever happens (the reason is kept in `last_status`, and an equal challenge
    already launched by hand just means there is nothing to do), so a schedule that cannot launch does not try again
    every day: the admin sees why in the panel."""
    month = challenges.month_start(today)
    if not schedule.active or month < schedule.first_month or (schedule.last_month is not None and schedule.last_month >= month):
        return None
    creator = db.get(models.User, schedule.created_by) if schedule.created_by else None
    challenge = None
    try:
        challenge = challenges_crud.create(db, creator, schedule.kind, options_for(schedule, month), today, schedule.participation)
        status = f"Lanzado: {challenge.title}"
    except ChallengeError as e:
        status = str(e)
    schedule.last_month = month
    schedule.last_status = f"{month_text(month)}: {status}"[:255]
    db.commit()
    return challenge


def run_due(db: Session, today: datetime.date) -> list[tuple[models.ChallengeSchedule, models.Challenge]]:
    """Launch what is due today for every schedule; the ones that did launch a challenge."""
    launched = []
    for schedule in db.query(models.ChallengeSchedule).filter_by(active=True).order_by(models.ChallengeSchedule.id):
        challenge = launch_due(db, schedule, today)
        if challenge is not None:
            launched.append((schedule, challenge))
    return launched


def view(db: Session, schedule: models.ChallengeSchedule, today: datetime.date) -> dict:
    """A schedule as the panel shows it, with the game of the running month and of the next one."""
    games = json.loads(schedule.games) if schedule.games else None
    names = {game.id: game.name for game in db.query(models.Game).filter(models.Game.id.in_(games or []))}
    creator = db.get(models.User, schedule.created_by) if schedule.created_by else None
    month = challenges.month_start(today)
    return {
        "id": schedule.id,
        "label": schedule.label,
        "kind": schedule.kind,
        "kind_label": challenges.TEMPLATES[schedule.kind].label,
        "options": json.loads(schedule.options),
        "games": [{"id": game_id, "name": names.get(game_id, game_id)} for game_id in games] if games else None,
        "this_month": names.get(rotating_game(games, schedule.first_month, month)) if games and month >= schedule.first_month else None,
        "next_month": names.get(rotating_game(games, schedule.first_month, challenges.next_month(today))) if games else None,
        "participation": schedule.participation,
        "announce": bool(schedule.announce),
        "active": bool(schedule.active),
        "first_month": schedule.first_month,
        "last_month": schedule.last_month,
        "last_status": schedule.last_status,
        "created_by": creator.username if creator else None,
    }


def listing(db: Session, today: datetime.date) -> list[dict]:
    return [view(db, row, today) for row in db.query(models.ChallengeSchedule).order_by(models.ChallengeSchedule.id)]
