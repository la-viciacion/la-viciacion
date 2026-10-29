"""Polls in the Telegram group: sending them, stopping them and telling the winner (crud/group_polls.py keeps them).

A poll is a native **non-anonymous** poll sent by the app's bot, which is the one that hears the answers (a poll answer
only reaches the bot that sent the poll, and only one process may read the bot's updates). Closing a poll is decided
here, not in Telegram: it is closed in the database first, so a Telegram that is down, a message that was deleted or a
poll Telegram already stopped never keeps it open. Telling Telegram to stop it is best effort and is tried again.
"""
import datetime

import telegram
from sqlalchemy.orm import Session

from ..crud import group_polls
from ..database import models
from . import my_utils, settings
from .logger import LogManager

logger = LogManager().get_logger()


class TelegramFailure(Exception):
    """Telegram did not take the poll (the message is shown to the admin)."""


# ── text (pure) ─────────────────────────────────────────────────


def _votes(n: int) -> str:
    return f"{n} voto" if n == 1 else f"{n} votos"


def result_message(question: str, options: list[str], counts: list[int], winners: list[int]) -> str:
    """The notice of a poll that closed: the question and the winning option, a tie or that nobody voted."""
    head = f"📊 *Encuesta cerrada*\n{my_utils.escape_markdown(question)}\n"
    if not winners:
        return head + "Nadie votó."
    names = [f"*{my_utils.escape_markdown(options[position])}*" for position in winners]
    if len(winners) == 1:
        return head + f"🏆 Gana {names[0]} con {_votes(counts[winners[0]])}."
    return head + f"🤝 Empate entre {my_utils.join_names(names)} con {_votes(counts[winners[0]])} cada una."


# ── Telegram ────────────────────────────────────────────────────


def _bot_and_group() -> tuple[str, str]:
    token, group = settings.get("telegram.token"), settings.get("telegram.group_id")
    if not token or not group:
        raise TelegramFailure("Falta el token del bot o el ID del grupo")
    return token, group


async def send(question: str, options: list[str], multiple: bool, allow_adding_options: bool = False) -> tuple[str, int, list[str]]:
    """Send the poll to the group: (the id of the poll, the id of its message, the ids Telegram gave its options). Not
    tied to the notifications switch, like a test message: an admin asked for it. Raises TelegramFailure with why."""
    token, group = _bot_and_group()
    try:
        async with telegram.Bot(token) as bot:
            message = await bot.send_poll(
                chat_id=group, question=question, options=options, is_anonymous=False, allows_multiple_answers=multiple,
                allow_adding_options=allow_adding_options,
            )
    except Exception as e:
        logger.error(f"Could not send the poll: {e}", exc_info=True)
        raise TelegramFailure(f"Telegram no aceptó la encuesta: {e}")
    return message.poll.id, message.message_id, [option.persistent_id for option in message.poll.options]


async def stop(poll: models.GroupPoll) -> tuple[bool, int | None]:
    """Tell Telegram to stop the poll: (whether it is stopped there now, how many people it counted when it knows).
    Never raises: a poll that is closed here is closed whatever this says. One Telegram already stopped counts as stopped."""
    try:
        token, group = _bot_and_group()
        async with telegram.Bot(token) as bot:
            stopped = await bot.stop_poll(chat_id=group, message_id=poll.telegram_message_id)
        return True, stopped.total_voter_count
    except telegram.error.BadRequest as e:
        if "already" in str(e).lower() and "closed" in str(e).lower():
            return True, None
        logger.warning(f"Telegram did not stop poll {poll.id}: {e}")
    except Exception as e:
        logger.warning(f"Telegram did not stop poll {poll.id}: {e}")
    return False, None


# ── what happens to a poll ──────────────────────────────────────


async def launch(
    db: Session, creator: models.User, question: str, options: list[str], multiple: bool, closes_at: datetime.datetime | None,
    allow_adding_options: bool = False,
) -> models.GroupPoll:
    """Send a poll that was already checked (`group_polls.clean`) and keep it."""
    poll_id, message_id, keys = await send(question, options, multiple, allow_adding_options)
    return group_polls.create(db, creator, question, options, multiple, closes_at, poll_id, message_id, keys, allow_adding_options)


async def close(db: Session, poll: models.GroupPoll, admin_id: int | None, announce: bool, now: datetime.datetime) -> bool:
    """Close a poll: here first, then in Telegram (again if it was closed here but Telegram never stopped), and tell the
    group the winner when it closes now and `announce`. False if it was already closed."""
    newly = group_polls.close(db, poll, admin_id, now)
    if not poll.telegram_stopped:
        stopped, voters = await stop(poll)
        if stopped:
            group_polls.mark_stopped(db, poll, voters)
    if newly and announce:
        shown = group_polls.results(db, poll)
        counts = [option["votes"] for option in shown["options"]]
        await my_utils.send_message(result_message(poll.question, [option["text"] for option in shown["options"]], counts, shown["winners"]), False)
    return newly


async def close_due(db: Session, now: datetime.datetime) -> str:
    """The scheduler's job: close the polls whose deadline has passed (and tell the group the winner)."""
    closed = 0
    for poll in group_polls.due(db, now):
        try:
            await close(db, poll, None, True, now)
            closed += 1
        except Exception as e:  # one poll failing must not cost the others theirs
            db.rollback()
            logger.error(f"Poll {poll.id} not closed: {e}", exc_info=True)
    return f"{closed} closed"


async def retry_stops(db: Session, now: datetime.datetime) -> str:
    """The scheduler's job: tell Telegram again to stop the polls closed here that it did not stop."""
    stopped = 0
    for poll in group_polls.to_stop(db, now):
        done, voters = await stop(poll)
        if done:
            group_polls.mark_stopped(db, poll, voters)
            stopped += 1
    return f"{stopped} stopped"
