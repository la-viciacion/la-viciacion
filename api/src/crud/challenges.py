"""Challenges (utils/challenges.py has the templates): create them, who takes part, what each one looks like with its
progress, and the history of a player. Only the definition and the opt-outs are stored; progress is derived."""
import datetime
import json

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import models
from ..utils import challenges
from ..utils.challenges import ChallengeError, GROUP, TEMPLATES, USER


def create(db: Session, creator: models.User, kind: str, options: dict, today: datetime.date) -> models.Challenge:
    """Launch a challenge. A group one belongs to nobody, a personal one to `creator`. Who may launch which is checked
    by the caller. Raises ChallengeError for options that are not valid or a challenge that already exists."""
    template = TEMPLATES.get(kind)
    if template is None:
        raise ChallengeError("Ese tipo de reto no existe")
    built = template.build(db, options or {}, today)
    owner_id = creator.id if template.scope == USER else None
    digest = challenges.fingerprint(kind, built, owner_id)
    if db.query(models.Challenge.id).filter(models.Challenge.fingerprint == digest).first() is not None:
        raise ChallengeError("Ya existe un reto igual")
    challenge = models.Challenge(
        kind=kind, scope=template.scope, owner_user_id=owner_id, created_by=creator.id, title=built.title,
        params=json.dumps(built.params, ensure_ascii=False), game_id=built.game_id, starts_on=built.starts_on,
        ends_on=built.ends_on, fingerprint=digest,
    )
    db.add(challenge)
    try:
        db.commit()
    except IntegrityError:  # two equal ones launched at once: the key of the fingerprint decides
        db.rollback()
        raise ChallengeError("Ya existe un reto igual")
    return challenge


def participants(db: Session, challenge: models.Challenge) -> list[int]:
    """Who takes part: a personal challenge its owner, a group one every active player that has not opted out."""
    if challenge.scope == USER:
        return [challenge.owner_user_id] if challenge.owner_user_id is not None else []
    left = db.query(models.ChallengeOptOut.user_id).filter(models.ChallengeOptOut.challenge_id == challenge.id)
    rows = db.query(models.User.id).filter(models.User.is_active == 1, models.not_god(), ~models.User.id.in_(left))
    return [user_id for (user_id,) in rows.order_by(models.User.id)]


def can_opt_out(challenge: models.Challenge, today: datetime.date) -> bool:
    """Only a group challenge that has not finished can be left or rejoined."""
    return challenge.scope == GROUP and challenge.participation == "auto" and today <= challenge.ends_on


def opt(db: Session, challenge: models.Challenge, user_id: int, joined: bool) -> None:
    """Take part in a group challenge again (`joined`) or stop taking part. Asking twice changes nothing."""
    row = db.get(models.ChallengeOptOut, (challenge.id, user_id))
    if joined and row is not None:
        db.delete(row)
    elif not joined and row is None:
        db.add(models.ChallengeOptOut(challenge_id=challenge.id, user_id=user_id))
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
        "taking_part": viewer_id in taking_part,
        "can_opt_out": can_opt_out(challenge, today),
        "progress": progress if progress is not None else template.progress(db, challenge, taking_part),
    }


def visible(db: Session, viewer_id: int) -> list[models.Challenge]:
    """The challenges the viewer can see: every public one and their own; the latest period first."""
    return (
        db.query(models.Challenge)
        .filter((models.Challenge.visibility == "public") | (models.Challenge.owner_user_id == viewer_id))
        .order_by(models.Challenge.starts_on.desc(), models.Challenge.id.desc())
        .all()
    )


def outcome(progress: dict, user_id: int) -> dict:
    """How a player did in a challenge (from its progress): whether they reached their part and whether the group did."""
    mine = next((p for p in progress["players"] if p["user_id"] == user_id), None)
    return {"done": bool(mine and mine["done"]), "seconds": mine["seconds"] if mine else 0, "group_done": progress.get("total_done")}


def history(db: Session, player_id: int, today: datetime.date) -> list[dict]:
    """The finished challenges a player took part in, the latest first, with how they did. Public ones only."""
    found = []
    for challenge in (
        db.query(models.Challenge)
        .filter(models.Challenge.ends_on < today, models.Challenge.visibility == "public")
        .order_by(models.Challenge.ends_on.desc(), models.Challenge.id.desc())
    ):
        taking_part = participants(db, challenge)
        if player_id not in taking_part:
            continue
        progress = TEMPLATES[challenge.kind].progress(db, challenge, taking_part)
        found.append({
            "id": challenge.id, "kind": challenge.kind, "label": TEMPLATES[challenge.kind].label, "scope": challenge.scope,
            "title": challenge.title, "starts_on": challenge.starts_on, "ends_on": challenge.ends_on,
            **outcome(progress, player_id),
        })
    return found


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
