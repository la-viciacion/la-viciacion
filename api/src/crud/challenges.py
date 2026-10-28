"""Challenges (utils/challenges.py has the templates): create them, who takes part, what each one looks like with its
progress, and the history of a player. Only the definition and the opt-outs are stored; progress is derived."""
import datetime
import json

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import models
from ..utils import challenges
from ..utils.challenges import AUTO, DECLINE_HOURS, DUEL, GROUP, OPT_IN, PARTICIPATIONS, TEMPLATES, USER, ChallengeConflict, ChallengeError, rank_players


def create(
    db: Session, creator: models.User | None, kind: str, options: dict, today: datetime.date, participation: str = AUTO
) -> models.Challenge:
    """Launch a challenge. A group one belongs to nobody, a personal one to `creator` (a group one may have no creator:
    a schedule whose admin was deleted launches it). Who may launch which is checked by the caller. `participation` is
    for a group one only: every active player ("auto") or only those who join ("opt_in"). Raises ChallengeError for
    options that are not valid and ChallengeConflict for a challenge that already exists."""
    template = TEMPLATES.get(kind)
    if template is None:
        raise ChallengeError("Ese tipo de reto no existe")
    if participation not in PARTICIPATIONS:
        raise ChallengeError("La participación debe ser de todos o voluntaria")
    if participation != AUTO and template.scope != GROUP:
        raise ChallengeError("Solo los retos del grupo pueden ser voluntarios")
    creator_id = creator.id if creator else None
    built = template.build(db, options or {}, today, creator_id)
    owner_id = creator_id if template.scope in (USER, DUEL) else None
    digest = challenges.fingerprint(kind, built, owner_id, participation)
    if db.query(models.Challenge.id).filter(models.Challenge.fingerprint == digest).first() is not None:
        raise ChallengeConflict("Ya existe un reto igual")
    challenge = models.Challenge(
        kind=kind, scope=template.scope, owner_user_id=owner_id, created_by=creator_id, title=built.title,
        params=json.dumps(built.params, ensure_ascii=False), game_id=built.game_id, starts_on=built.starts_on,
        ends_on=built.ends_on, fingerprint=digest, participation=participation,
    )
    db.add(challenge)
    try:
        db.commit()
    except IntegrityError:  # two equal ones launched at once: the key of the fingerprint decides
        db.rollback()
        raise ChallengeConflict("Ya existe un reto igual")
    return challenge


def opponent_id(challenge: models.Challenge) -> int | None:
    """The player a duel challenges."""
    return json.loads(challenge.params).get("opponent_id") if challenge.scope == DUEL else None


def declined(db: Session, challenge: models.Challenge) -> bool:
    """Has the challenged player turned the duel down? It is the same row as leaving a group challenge."""
    return challenge.scope == DUEL and db.get(models.ChallengeOptOut, (challenge.id, opponent_id(challenge))) is not None


def participants(db: Session, challenge: models.Challenge) -> list[int]:
    """Who takes part: a personal challenge its owner, a duel its owner and the challenged player (alone, if they
    declined it), a group one every active player that has not opted out or, if it is voluntary, only those who joined
    (both are rows of `challenge_optouts`: the row is a choice against what the challenge assumes)."""
    if challenge.scope == DUEL:
        return [challenge.owner_user_id] if declined(db, challenge) else [challenge.owner_user_id, opponent_id(challenge)]
    if challenge.scope == USER:
        return [challenge.owner_user_id] if challenge.owner_user_id is not None else []
    chosen = db.query(models.ChallengeOptOut.user_id).filter(models.ChallengeOptOut.challenge_id == challenge.id)
    rows = db.query(models.User.id).filter(models.User.is_active == 1, models.not_god())
    rows = rows.filter(models.User.id.in_(chosen) if challenge.participation == OPT_IN else ~models.User.id.in_(chosen))
    return [user_id for (user_id,) in rows.order_by(models.User.id)]


def can_opt_out(challenge: models.Challenge, today: datetime.date, viewer_id: int | None = None, now: datetime.datetime | None = None) -> bool:
    """Who can change whether they take part: in a group challenge that has not finished, anybody; in a duel, only the
    challenged player and only during the first DECLINE_HOURS after it was launched, to turn it down (a decline is
    final, see `view`; after that time the duel stands, so nobody dodges a duel they are losing)."""
    if challenge.scope == DUEL:
        launched = challenge.created_at or datetime.datetime.now()
        return viewer_id == opponent_id(challenge) and today <= challenge.ends_on and (now or datetime.datetime.now()) < launched + datetime.timedelta(hours=DECLINE_HOURS)
    return challenge.scope == GROUP and challenge.participation in PARTICIPATIONS and today <= challenge.ends_on


def opt(db: Session, challenge: models.Challenge, user_id: int, joined: bool) -> None:
    """Take part in a group challenge (`joined`) or stop taking part, or decline a duel. Asking twice changes nothing.
    The row means joining in a voluntary challenge and leaving (or declining) in any other."""
    row = db.get(models.ChallengeOptOut, (challenge.id, user_id))
    wants_row = joined if challenge.participation == OPT_IN else not joined
    if wants_row and row is None:
        db.add(models.ChallengeOptOut(challenge_id=challenge.id, user_id=user_id))
    elif not wants_row and row is not None:
        db.delete(row)
    db.commit()


def delete(db: Session, challenge: models.Challenge) -> None:
    db.delete(challenge)
    db.commit()


def progress_of(db: Session, challenge: models.Challenge) -> dict:
    return TEMPLATES[challenge.kind].progress(db, challenge, participants(db, challenge))


def view(db: Session, challenge: models.Challenge, viewer_id: int, today: datetime.date, progress: dict | None = None) -> dict:
    """A challenge as the app shows it, with its progress and whether the viewer takes part."""
    template = TEMPLATES[challenge.kind]
    taking_part = participants(db, challenge)
    game = db.get(models.Game, challenge.game_id) if challenge.game_id else None
    owner = db.get(models.User, challenge.owner_user_id) if challenge.owner_user_id else None
    opponent = db.get(models.User, opponent_id(challenge)) if challenge.scope == DUEL else None
    if progress is None:
        progress = template.progress(db, challenge, taking_part)
        if json.loads(challenge.params).get("versus"):
            rank_players(progress["players"])
    return {
        "id": challenge.id,
        "kind": challenge.kind,
        "label": template.label,
        "scope": challenge.scope,
        "title": challenge.title,
        "status": challenges.status_of(challenge, today),
        "starts_on": challenge.starts_on,
        "ends_on": challenge.ends_on,
        "params": json.loads(challenge.params),
        "game": {"id": game.id, "name": game.name, "image_url": game.image_url} if game else None,
        "owner": {"id": owner.id, "name": owner.name or owner.username} if owner else None,
        "visibility": challenge.visibility,
        "participation": challenge.participation,
        "opponent": {"id": opponent.id, "name": opponent.name or opponent.username} if opponent else None,
        "declined": declined(db, challenge),
        "taking_part": viewer_id in taking_part,
        "can_opt_out": can_opt_out(challenge, today, viewer_id) and not declined(db, challenge),
        "progress": progress,
    }


def block_of(challenge: models.Challenge, viewer_id: int) -> str:
    """Where the challenges page lists a challenge for the viewer: the group's, theirs, the duels they are in or the others'."""
    if challenge.scope == GROUP:
        return "group"
    if challenge.scope == USER and challenge.owner_user_id == viewer_id:
        return "mine"
    if challenge.scope == DUEL and viewer_id in (challenge.owner_user_id, opponent_id(challenge)):
        return "duels"
    return "others"


def limit_finished(rows: list[models.Challenge], viewer_id: int, today: datetime.date, per_block: int) -> list[models.Challenge]:
    """`rows` (latest first) without the finished challenges beyond the first `per_block` of each block of the page (pure): the
    page only shows the latest few of those, and working out the progress of every challenge there ever was is the cost
    of opening it. The challenges that are not over are all kept."""
    shown: dict[str, int] = {}
    kept = []
    for challenge in rows:
        if challenge.ends_on >= today:
            kept.append(challenge)
            continue
        block = block_of(challenge, viewer_id)
        if shown.get(block, 0) < per_block:
            shown[block] = shown.get(block, 0) + 1
            kept.append(challenge)
    return kept


def visible(
    db: Session, viewer_id: int, running_on: datetime.date | None = None, finished_per_block: int | None = None, today: datetime.date | None = None,
) -> list[models.Challenge]:
    """The challenges the viewer can see: every public one and their own; the latest period first. With `running_on`,
    only those whose period includes that day. With `finished_per_block`, only that many finished ones in each block of
    the page (see limit_finished), as of `today`."""
    query = db.query(models.Challenge).filter((models.Challenge.visibility == "public") | (models.Challenge.owner_user_id == viewer_id))
    if running_on is not None:
        query = query.filter(models.Challenge.starts_on <= running_on, models.Challenge.ends_on >= running_on)
    rows = query.order_by(models.Challenge.starts_on.desc(), models.Challenge.id.desc()).all()
    if finished_per_block is not None:
        rows = limit_finished(rows, viewer_id, today or datetime.date.today(), finished_per_block)
    return rows


def outcome(progress: dict, user_id: int) -> dict:
    """How a player did in a challenge (from its progress): whether they reached their part and whether the group did."""
    mine = next((p for p in progress["players"] if p["user_id"] == user_id), None)
    firsts = [p for p in progress["players"] if p.get("position") == 1]
    return {"done": bool(mine and mine["done"]), "group_done": progress.get("total_done"), "tied": len(firsts) > 1 and any(p["winner"] for p in firsts)}


def history(db: Session, player_id: int, today: datetime.date, since_year: int | None = None) -> list[dict]:
    """The finished challenges a player took part in, the latest first, with how they did. Public ones only. With
    `since_year`, only those that began in that year or later (what the achievements read: the rest is not even
    worked out)."""
    found = []
    finished = db.query(models.Challenge).filter(models.Challenge.ends_on < today, models.Challenge.visibility == "public")
    if since_year:
        finished = finished.filter(models.Challenge.starts_on >= datetime.date(since_year, 1, 1))
    for challenge in finished.order_by(models.Challenge.ends_on.desc(), models.Challenge.id.desc()):
        taking_part = participants(db, challenge)
        if player_id not in taking_part or declined(db, challenge):
            continue
        progress = TEMPLATES[challenge.kind].progress(db, challenge, taking_part)
        if json.loads(challenge.params).get("versus"):
            rank_players(progress["players"])
        found.append({
            "id": challenge.id, "kind": challenge.kind, "label": TEMPLATES[challenge.kind].label, "scope": challenge.scope,
            "title": challenge.title, "starts_on": challenge.starts_on, "ends_on": challenge.ends_on,
            **outcome(progress, player_id),
        })
    return found


def genres(db: Session, viewer_id: int) -> list[dict]:
    """The genres a personal challenge can be about (those of the games in the database), with how many games each has
    and whether the viewer already has a game of it in their library."""
    owned = set()
    for (genre_text,) in (
        db.query(models.Game.genres)
        .join(models.UserGame, models.UserGame.game_id == models.Game.id)
        .filter(models.UserGame.user_id == viewer_id, models.Game.genres.isnot(None))
        .distinct()
    ):
        owned.update(genre.casefold() for genre in challenges.split_genres(genre_text))
    return [
        {"genre": name, "games": count, "played": key in owned}
        for key, (name, count) in sorted(challenges.available_genres(db).items())
    ]


def debt_preview(db: Session, viewer_id: int, today: datetime.date) -> dict:
    """What a "reduce the debt" challenge launched today would be about: the seconds the viewer has left to play of
    the games they have open, how many of those games still owe time, and how many are open (the most they can ask
    to close). The same figures the challenge starts from, so the form can say what a percentage means in hours."""
    from . import debt  # that module imports the ones that import this one

    open_games = debt.games_in_debt_at(db, viewer_id, today, datetime.datetime.now())
    return {"seconds": sum(open_games.values()), "games": sum(1 for left in open_games.values() if left), "open_games": len(open_games)}


def reached_totals(db: Session, today: datetime.date) -> list[tuple[models.Challenge, dict]]:
    """The running group challenges whose total is reached and whose group has not been told yet."""
    found = []
    for challenge in db.query(models.Challenge).filter(
        models.Challenge.scope == GROUP,
        models.Challenge.total_notified_at.is_(None),
        models.Challenge.starts_on <= today,
        models.Challenge.ends_on >= today,
    ):
        progress = progress_of(db, challenge)
        if progress.get("total_done"):
            found.append((challenge, progress))
    return found
