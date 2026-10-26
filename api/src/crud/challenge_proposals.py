"""Group challenges proposed by players. A player proposes a game of the month or a themed challenge; an admin approves
it, which launches it like any other group challenge (crud/challenges.py), or rejects it with a note. Only the
proposal is stored; the challenge it becomes is derived as always."""
import datetime
import json

from sqlalchemy.orm import Session

from ..database import models
from ..utils import challenges
from ..utils.challenges import ChallengeConflict, ChallengeError
from . import challenges as challenges_crud

MAX_PENDING = 3  # proposals a player may have waiting at once
MAX_NOTE = 255
PENDING, APPROVED, REJECTED = "pending", "approved", "rejected"


def _built(db: Session, kind: str, options: dict, today: datetime.date, user_id: int | None) -> tuple[dict, challenges.Built]:
    """The options a proposal keeps and the challenge they would make, checked as if it were launched today."""
    if kind not in challenges.PROPOSABLE:
        raise ChallengeError("Solo se pueden proponer retos de juego del mes o temáticos")
    cleaned = challenges.clean_options(options)
    return cleaned, challenges.TEMPLATES[kind].build(db, cleaned, today, user_id)


def propose(db: Session, proposer: models.User, kind: str, options: dict, today: datetime.date) -> models.ChallengeProposal:
    """Keep a proposal for the admins. Raises ChallengeError when the options are not valid (the same checks as a
    launch, so an admin is never asked to approve what cannot be launched) and ChallengeConflict when the player has
    too many waiting or the same challenge exists or is already proposed."""
    waiting = db.query(models.ChallengeProposal).filter_by(proposer_id=proposer.id, status=PENDING).count()
    if waiting >= MAX_PENDING:
        raise ChallengeConflict(f"Ya tienes {MAX_PENDING} propuestas pendientes: espera a que se decidan o retira alguna")
    cleaned, built = _built(db, kind, options, today, proposer.id)
    digest = challenges.fingerprint(kind, built, None)
    if db.query(models.Challenge.id).filter(models.Challenge.fingerprint == digest).first() is not None:
        raise ChallengeConflict("Ya existe un reto igual")
    if db.query(models.ChallengeProposal.id).filter_by(fingerprint=digest, status=PENDING).first() is not None:
        raise ChallengeConflict("Ya hay una propuesta igual esperando respuesta")
    proposal = models.ChallengeProposal(
        proposer_id=proposer.id, kind=kind, options=json.dumps(cleaned, ensure_ascii=False), title=built.title, fingerprint=digest,
    )
    db.add(proposal)
    db.commit()
    return proposal


def approve(db: Session, proposal: models.ChallengeProposal, admin: models.User, today: datetime.date, participation: str = challenges.AUTO) -> models.Challenge:
    """Launch what was proposed, as the admin's challenge, and mark the proposal approved. Raises ChallengeError if it
    cannot be launched any more (its month has passed, the game was deleted...: the admin can reject it) and
    ChallengeConflict if it is already decided or an equal challenge exists."""
    if proposal.status != PENDING:
        raise ChallengeConflict("Esta propuesta ya está decidida")
    challenge = challenges_crud.create(db, admin, proposal.kind, json.loads(proposal.options), today, participation)
    proposal.status = APPROVED
    proposal.decided_by = admin.id
    proposal.decided_at = datetime.datetime.now()
    proposal.challenge_id = challenge.id
    db.commit()
    return challenge


def reject(db: Session, proposal: models.ChallengeProposal, admin: models.User, note: str | None) -> models.ChallengeProposal:
    if proposal.status != PENDING:
        raise ChallengeConflict("Esta propuesta ya está decidida")
    proposal.status = REJECTED
    proposal.decided_by = admin.id
    proposal.decided_at = datetime.datetime.now()
    proposal.decision_note = (note or "").strip()[:MAX_NOTE] or None
    db.commit()
    return proposal


def withdraw(db: Session, proposal: models.ChallengeProposal) -> None:
    """The proposer takes back a proposal nobody has decided yet."""
    if proposal.status != PENDING:
        raise ChallengeConflict("Esta propuesta ya está decidida")
    db.delete(proposal)
    db.commit()


def view(db: Session, proposal: models.ChallengeProposal) -> dict:
    """A proposal as the app shows it (to its proposer, and to the admins in the panel)."""
    proposer = db.get(models.User, proposal.proposer_id)
    decider = db.get(models.User, proposal.decided_by) if proposal.decided_by else None
    return {
        "id": proposal.id,
        "kind": proposal.kind,
        "label": challenges.TEMPLATES[proposal.kind].label,
        "title": proposal.title,
        "options": json.loads(proposal.options),
        "status": proposal.status,
        "decision_note": proposal.decision_note,
        "proposer": {"id": proposer.id, "name": proposer.name or proposer.username} if proposer else None,
        "decided_by": (decider.name or decider.username) if decider else None,
        "decided_at": proposal.decided_at,
        "challenge_id": proposal.challenge_id,
        "created_at": proposal.created_at,
    }


def mine(db: Session, user_id: int, limit: int = 30) -> list[dict]:
    """The proposals of a player, the latest first."""
    rows = db.query(models.ChallengeProposal).filter_by(proposer_id=user_id).order_by(models.ChallengeProposal.id.desc()).limit(limit)
    return [view(db, row) for row in rows]


def listing(db: Session, status: str | None = None) -> list[dict]:
    """Every proposal for the panel, the ones waiting first and then the latest."""
    query = db.query(models.ChallengeProposal)
    if status:
        query = query.filter_by(status=status)
    rows = query.order_by((models.ChallengeProposal.status != PENDING), models.ChallengeProposal.id.desc()).limit(200)
    return [view(db, row) for row in rows]
