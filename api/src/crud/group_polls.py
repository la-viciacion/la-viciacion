"""Polls an admin launches into the Telegram group (utils/polls.py talks to Telegram). A poll is a native, non-anonymous
Telegram poll: the bot hears each answer and the API keeps what each person chose now. Closing it, by hand or at its
deadline, is what ends it here; telling Telegram to stop it is best effort and tried again, so a failure there never
keeps a poll open. The tally, the winner and who voted what are derived when asked."""
import datetime
import json

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import models

MIN_OPTIONS, MAX_OPTIONS = 2, 10
MAX_QUESTION, MAX_OPTION = 300, 100  # what Telegram accepts
MAX_DEADLINE = datetime.timedelta(days=30)
STOP_RETRY_WINDOW = datetime.timedelta(days=1)  # a poll closed here is told to Telegram again for this long...
STOP_RETRY_AFTER = datetime.timedelta(minutes=1)  # ...but not at once: the closing itself has just tried


class PollError(ValueError):
    """The poll is not valid (the message is shown to whoever launched it)."""


# ── pure ────────────────────────────────────────────────────────


def clean(question, options, closes_at: datetime.datetime | None, now: datetime.datetime) -> tuple[str, list[str]]:
    """The question and options as they will be sent (blank options dropped), or a PollError."""
    question = str(question or "").strip()
    if not 1 <= len(question) <= MAX_QUESTION:
        raise PollError(f"La pregunta debe tener entre 1 y {MAX_QUESTION} caracteres")
    cleaned = [str(option).strip() for option in options or [] if str(option).strip()]
    if not MIN_OPTIONS <= len(cleaned) <= MAX_OPTIONS:
        raise PollError(f"Una encuesta necesita entre {MIN_OPTIONS} y {MAX_OPTIONS} opciones")
    if any(len(option) > MAX_OPTION for option in cleaned):
        raise PollError(f"Cada opción puede tener hasta {MAX_OPTION} caracteres")
    if len({option.casefold() for option in cleaned}) != len(cleaned):
        raise PollError("Las opciones no pueden repetirse")
    if closes_at is not None and not now < closes_at <= now + MAX_DEADLINE:
        raise PollError("La fecha límite debe ser futura y de como mucho 30 días")
    return question, cleaned


def tally(option_count: int, choices: list[list[int]]) -> list[int]:
    """The votes each option has, from what each voter chose (several each, in a poll that allows it)."""
    counts = [0] * option_count
    for chosen in choices:
        for position in set(chosen):
            if 0 <= position < option_count:
                counts[position] += 1
    return counts


def winners(counts: list[int]) -> list[int]:
    """The positions with the most votes (several on a tie); none when nobody voted."""
    top = max(counts, default=0)
    return [position for position, votes in enumerate(counts) if top and votes == top]


# ── stored ──────────────────────────────────────────────────────


def create(
    db: Session, creator: models.User | None, question: str, options: list[str], multiple: bool,
    closes_at: datetime.datetime | None, telegram_poll_id: str, telegram_message_id: int,
) -> models.GroupPoll:
    poll = models.GroupPoll(
        question=question, options=json.dumps(options, ensure_ascii=False), multiple=bool(multiple), closes_at=closes_at,
        telegram_poll_id=telegram_poll_id, telegram_message_id=telegram_message_id, created_by=creator.id if creator else None,
    )
    db.add(poll)
    db.commit()
    return poll


def open_poll(db: Session) -> models.GroupPoll | None:
    """The poll still open, if any: the group has one at a time."""
    return db.query(models.GroupPoll).filter(models.GroupPoll.closed_at.is_(None)).first()


def option_texts(poll: models.GroupPoll) -> list[str]:
    return json.loads(poll.options)


def record_answer(db: Session, telegram_poll_id: str, telegram_user_id: int, option_ids: list[int], now: datetime.datetime) -> bool:
    """Keep what a person chose now in a poll (nothing chosen = they took their vote back). False when it counts for
    nothing: a poll that is not ours, or one already closed here. Positions that are not an option are dropped."""
    poll = db.query(models.GroupPoll).filter_by(telegram_poll_id=str(telegram_poll_id)).first()
    if poll is None or poll.closed_at is not None:
        return False
    total = len(option_texts(poll))
    chosen = sorted({position for position in option_ids if isinstance(position, int) and 0 <= position < total})
    if not poll.multiple:
        chosen = chosen[:1]
    row = db.get(models.GroupPollVote, (poll.id, telegram_user_id))
    if not chosen:
        if row is not None:
            db.delete(row)
            db.commit()
        return True
    if row is None:
        db.add(models.GroupPollVote(poll_id=poll.id, telegram_user_id=telegram_user_id, option_ids=json.dumps(chosen), updated_at=now))
        try:
            db.commit()
            return True
        except IntegrityError:  # two answers of the same person at once: the later one is an update
            db.rollback()
            row = db.get(models.GroupPollVote, (poll.id, telegram_user_id))
    row.option_ids = json.dumps(chosen)
    row.updated_at = now
    db.commit()
    return True


def close(db: Session, poll: models.GroupPoll, admin_id: int | None, now: datetime.datetime) -> bool:
    """Close it here (what ends it, whatever Telegram does). False if it already was."""
    if poll.closed_at is not None:
        return False
    poll.closed_at = now
    poll.closed_by = admin_id
    db.commit()
    return True


def mark_stopped(db: Session, poll: models.GroupPoll, voters: int | None) -> None:
    """Telegram stopped the poll; `voters` is how many people it counted."""
    poll.telegram_stopped = True
    poll.telegram_voters = voters
    db.commit()


def due(db: Session, now: datetime.datetime) -> list[models.GroupPoll]:
    """The open polls whose deadline has passed."""
    return db.query(models.GroupPoll).filter(models.GroupPoll.closed_at.is_(None), models.GroupPoll.closes_at <= now).order_by(models.GroupPoll.id).all()


def to_stop(db: Session, now: datetime.datetime) -> list[models.GroupPoll]:
    """The polls closed here that Telegram has not been told to stop, from a minute after closing for a day (a poll whose
    message was deleted would otherwise be tried for ever)."""
    return (
        db.query(models.GroupPoll)
        .filter(models.GroupPoll.closed_at.isnot(None), models.GroupPoll.telegram_stopped.is_(False), models.GroupPoll.closed_at > now - STOP_RETRY_WINDOW, models.GroupPoll.closed_at <= now - STOP_RETRY_AFTER)
        .order_by(models.GroupPoll.id).all()
    )


def results(db: Session, poll: models.GroupPoll) -> dict:
    """The tally of a poll: the votes of each option with who gave them, the winners and how many people voted."""
    options = option_texts(poll)
    votes = db.query(models.GroupPollVote).filter_by(poll_id=poll.id).all()
    chosen = {vote.telegram_user_id: json.loads(vote.option_ids) for vote in votes}
    accounts = {
        telegram_id: {"user_id": user_id, "name": name or username}
        for telegram_id, user_id, name, username in db.query(models.User.telegram_id, models.User.id, models.User.name, models.User.username)
        .filter(models.User.telegram_id.in_(list(chosen) or [0]))
    }
    counts = tally(len(options), list(chosen.values()))
    shown = []
    for position, text in enumerate(options):
        voters = [accounts.get(who, {"user_id": None, "name": None}) for who, picks in chosen.items() if position in picks]
        voters.sort(key=lambda voter: (voter["name"] is None, (voter["name"] or "").lower()))  # those with no account last
        shown.append({"text": text, "votes": counts[position], "voters": voters})
    return {"options": shown, "winners": winners(counts), "voters": len(chosen)}


def view(db: Session, poll: models.GroupPoll) -> dict:
    """A poll as the panel shows it."""
    shown = results(db, poll)
    return {
        "id": poll.id, "question": poll.question, "multiple": bool(poll.multiple),
        "status": "open" if poll.closed_at is None else "closed",
        "closes_at": poll.closes_at, "closed_at": poll.closed_at, "created_at": poll.created_at,
        "telegram_stopped": bool(poll.telegram_stopped),
        # Telegram counted more people than this table knows: an answer was missed (the bot was down for long)
        "missed_votes": poll.telegram_voters is not None and poll.telegram_voters > shown["voters"],
        **shown,
    }
