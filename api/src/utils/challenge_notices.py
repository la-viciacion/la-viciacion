"""Notices about the challenges. The rules that keep them from becoming spam:

- The group only hears about **group** challenges (the launch and the total reached, in utils/actions.py, and how it
  ended, here). Personal challenges and duels never go to the group.
- Everything else is **private**, to the player it concerns, through the channels that player left on for it
  (`user_settings`): what concerns them (a duel, a proposal, how their challenges ended) is on by default and the
  reminders are off until each player turns them on. A notice with both channels off is not sent at all.
- At most **one message per player and day** for the results and for the reminders: several challenges are listed in
  one message.
- Nothing is remembered about what was told. Each notice is triggered by an exact condition (the challenge ended
  yesterday, it has exactly two days left) and its job runs once per slot (`job_runs`), so there is nothing to
  keep in the database and nothing to repeat.

The text is built by pure functions (the tests read them); the senders only look up who and how.
"""
import datetime
import json

from sqlalchemy.orm import Session

from ..crud import challenges as challenges_crud
from ..database import models
from . import challenges, inbox, my_utils as utils, settings, user_settings
from .logger import LogManager

logger = LogManager().get_logger()

REMINDER_DAYS = 2  # a reminder comes when a challenge has exactly this many days left
UNITS = {"games": ("juego", "juegos"), "days": ("día", "días"), "sessions": ("sesión", "sesiones"), "genres": ("género", "géneros")}
MEDALS = ["🥇", "🥈", "🥉"]


# ── text (pure) ─────────────────────────────────────────────────


def _bold(text: str) -> str:
    return "*" + utils.escape_markdown(text) + "*"


def _hours(seconds: float) -> str:
    return challenges.hours_text(round(seconds / 3600, 1)) + " h"


def _count(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def duel_invite_message(challenger: str, title: str, ends_on: datetime.date, decline_hours: int) -> str:
    return (
        f"⚔️ {_bold(challenger)} te ha retado a un duelo\n"
        f"{_bold(title)}: gana quien juegue más hasta el {challenges.spanish_date(ends_on)}. Ya está en marcha; "
        f"puedes rechazarlo en Retos durante las próximas {decline_hours} horas."
    )


def duel_declined_message(opponent: str, title: str) -> str:
    return f"🙅 {_bold(opponent)} ha rechazado tu duelo\n{_bold(title)} queda anulado: no cuenta para nadie."


def proposal_decided_message(title: str, approved: bool, note: str | None) -> str:
    if approved:
        return f"✅ Tu propuesta se ha aprobado\n{_bold(title)} ya es un reto del grupo: míralo en Retos."
    extra = f"\nNota: {utils.escape_markdown(note)}" if note else ""
    return f"❌ Tu propuesta se ha rechazado\n{_bold(title)}.{extra}"


def proposal_arrived_message(proposer: str, title: str) -> str:
    return f"📝 {_bold(proposer)} ha propuesto un reto\n{_bold(title)}: apruébalo o recházalo en el panel, en Propuestas."


def _amount(part: dict, value: int) -> str:
    """What a duel part is measured in, said for `value`: games completed or hours played."""
    return _count(value, *UNITS["games"]) if "target_count" in part else _hours(value)


def remaining_text(part: dict) -> str:
    """What a player still lacks in a challenge: "te faltan 1,5 h", "te falta 1 juego", "te falta saldar un 12,5 % más"."""
    if "target_count" in part:
        left = part["target_count"] - part["count"]
        one, many = UNITS.get(part.get("unit"), UNITS["games"])
        return f"te falta 1 {one}" if left == 1 else f"te faltan {left} {many}"
    if "target_percent" in part:
        return f"te falta saldar un {challenges.hours_text(round(part['target_percent'] - part['percent'], 1))} % más"
    return f"te faltan {_hours(part['target_seconds'] - part['seconds'])}"


def results_message(lines: list[str]) -> str:
    """One message with how the player's challenges that ended yesterday went (the first line is what a push shows)."""
    header = "🏁 Ha terminado uno de tus retos" if len(lines) == 1 else f"🏁 Han terminado {len(lines)} de tus retos"
    return header + "\n" + "\n".join(lines)


def reminders_message(lines: list[str]) -> str:
    header = f"⏰ Te quedan {REMINDER_DAYS} días en " + ("un reto" if len(lines) == 1 else f"{len(lines)} retos")
    return header + "\n" + "\n".join(lines)


def result_line(challenge: models.Challenge, progress: dict, user_id: int, names: dict[int, str]) -> str:
    """How a challenge went for one of its participants, a line of their results message."""
    mine = next(p for p in progress["players"] if p["user_id"] == user_id)
    if challenge.scope == challenges.DUEL:
        other = next((p for p in progress["players"] if p["user_id"] != user_id), None)
        rival = _bold(names[other["user_id"]]) if other else "tu rival"
        mine_value, other_value = (challenges.part_value(mine), challenges.part_value(other)) if other else (0, 0)
        if other is None or (not mine_value and not other_value):
            return f"⚪ {_bold(challenge.title)} contra {rival}: nadie {'completó nada' if 'target_count' in mine else 'jugó'}, sin ganador"
        score = f"{_amount(mine, mine_value)} frente a {_amount(mine, other_value)}"
        if mine_value == other_value:
            return f"🤝 {_bold(challenge.title)} contra {rival}: empate ({score})"
        return f"🥇 Ganaste el duelo a {rival} ({score})" if mine["done"] else f"🥈 Perdiste el duelo contra {rival} ({score})"
    line = f"{'✅' if mine['done'] else '❌'} {_bold(challenge.title)}: " + (
        "cumpliste tu parte" if mine["done"] else "se perdió: empezaste un juego nuevo antes de terminar uno" if mine.get("failed") else "no se cumplió"
    )
    if challenge.scope == challenges.GROUP and progress.get("total_done"):
        line += " y el grupo llegó al total"
    if mine.get("position"):
        line += f" ({MEDALS[mine['position'] - 1] if mine['position'] <= 3 else str(mine['position']) + 'º'})"
    return line


def group_result_message(challenge: models.Challenge, progress: dict) -> str:
    """How a group challenge ended, one message for the group."""
    players = progress["players"]
    met = sum(1 for p in players if p["done"])
    text = f"🏁 *Ha terminado el reto del grupo*\n{_bold(challenge.title)}\n{met} de {len(players)} habéis cumplido vuestra parte"
    if "total_done" in progress:
        text += " y " + ("el grupo llegó al total" if progress["total_done"] else "el grupo no llegó al total")
    text += "."
    winners = [p["name"] for p in players if p.get("winner")]
    if winners:
        text += f"\n🥇 {'Gana' if len(winners) == 1 else 'Ganan'} {utils.join_names([_bold(name) for name in winners])}."
    return text


# ── who is told and how ─────────────────────────────────────────


async def tell(db: Session, user: models.User, message: str, reminder: bool = False) -> bool:
    """A private notice through the channels the player left on for this kind (both off: nothing, not even the inbox).
    A reminder only matters at the moment, so it does not go in the inbox."""
    channels = (user_settings.challenge_reminders_channels if reminder else user_settings.challenge_notices_channels)(db, user.id)
    if not any(channels):
        return False
    await utils.send_message_to_user(
        user.telegram_id, message, user_id=user.id, telegram_on=channels[0], push_on=channels[1], in_inbox=not reminder
    )
    return True


def _progress(db: Session, challenge: models.Challenge, taking: list[int]) -> dict:
    progress = challenges.TEMPLATES[challenge.kind].progress(db, challenge, taking)
    if json.loads(challenge.params).get("versus"):
        challenges.rank_players(progress["players"])
    return progress


def _active(db: Session, user_id: int) -> models.User | None:
    user = db.get(models.User, user_id)
    return user if user is not None and user.is_active and user.username != models.GOD_USERNAME else None


# ── what happens to a challenge ─────────────────────────────────


async def duel_launched(db: Session, challenge_id: int) -> str:
    """The challenged player hears they have been challenged and for how long they can turn it down."""
    challenge = db.get(models.Challenge, challenge_id)
    if challenge is None or challenge.scope != challenges.DUEL or not settings.get("challenges.private_notices"):
        return "skipped"
    challenger = db.get(models.User, challenge.owner_user_id)
    opponent = _active(db, challenges_crud.opponent_id(challenge))
    if challenger is None or opponent is None:
        return "skipped"
    message = duel_invite_message(challenger.name or challenger.username, challenge.title, challenge.ends_on, challenges.DECLINE_HOURS)
    return "sent" if await tell(db, opponent, message) else "off"


async def duel_declined(db: Session, challenge_id: int) -> str:
    """The challenger hears the duel was turned down."""
    challenge = db.get(models.Challenge, challenge_id)
    if challenge is None or challenge.scope != challenges.DUEL or not challenges_crud.declined(db, challenge) or not settings.get("challenges.private_notices"):
        return "skipped"
    challenger = _active(db, challenge.owner_user_id)
    opponent = db.get(models.User, challenges_crud.opponent_id(challenge))
    if challenger is None or opponent is None:
        return "skipped"
    return "sent" if await tell(db, challenger, duel_declined_message(opponent.name or opponent.username, challenge.title)) else "off"


async def proposal_made(db: Session, proposal_id: int) -> str:
    """The admins find it in their inbox of the app: not on Telegram and not by push (the panel lists it too)."""
    proposal = db.get(models.ChallengeProposal, proposal_id)
    if proposal is None or not settings.get("notifications.enabled"):
        return "skipped"
    proposer = db.get(models.User, proposal.proposer_id)
    if proposer is None:
        return "skipped"
    message = proposal_arrived_message(proposer.name or proposer.username, proposal.title)
    admins = db.query(models.User.id).filter(models.User.is_admin == 1, models.User.is_active == 1, models.not_god(), models.User.id != proposer.id)
    told = 0
    for (admin_id,) in admins:
        inbox.record_user(admin_id, message)
        told += 1
    return f"{told} admins"


async def proposal_decided(db: Session, proposal_id: int) -> str:
    """The proposer hears how it was answered."""
    proposal = db.get(models.ChallengeProposal, proposal_id)
    if proposal is None or proposal.status == "pending" or not settings.get("challenges.private_notices"):
        return "skipped"
    proposer = _active(db, proposal.proposer_id)
    if proposer is None:
        return "skipped"
    message = proposal_decided_message(proposal.title, proposal.status == "approved", proposal.decision_note)
    return "sent" if await tell(db, proposer, message) else "off"


# ── the daily jobs ──────────────────────────────────────────────


async def announce_results(db: Session, today: datetime.date) -> str:
    """The challenges that ended yesterday: each participant gets one message with how theirs went (what concerns
    them) and the group hears how each group challenge ended (if an admin left that on). A declined duel is nothing."""
    private, group = settings.get("challenges.private_notices"), settings.get("challenges.result_notice")
    if not (private or group):
        return "off"
    lines: dict[int, list[str]] = {}
    group_messages = []
    ended = db.query(models.Challenge).filter(models.Challenge.ends_on == today - datetime.timedelta(days=1), models.Challenge.visibility == "public").order_by(models.Challenge.id)
    for challenge in ended:
        taking = challenges_crud.participants(db, challenge)
        if not taking or challenges_crud.declined(db, challenge):
            continue
        progress = _progress(db, challenge, taking)
        names = challenges.names_of(db, taking)
        for user_id in taking:
            lines.setdefault(user_id, []).append(result_line(challenge, progress, user_id, names))
        if challenge.scope == challenges.GROUP:
            group_messages.append(group_result_message(challenge, progress))
    told = 0
    if private:
        for user_id, user_lines in lines.items():
            try:
                user = _active(db, user_id)
                if user is not None and await tell(db, user, results_message(user_lines)):
                    told += 1
            except Exception as e:  # one player's notice failing must not cost the others theirs
                db.rollback()
                logger.error(f"Challenge result not told to user {user_id}: {e}", exc_info=True)
    if group:
        for message in group_messages:
            await utils.send_message(message, False)
    return f"{told} told, {len(group_messages) if group else 0} to the group"


async def send_reminders(db: Session, today: datetime.date) -> str:
    """The running challenges with exactly two days left: whoever has not met their part gets one message with all of
    them (only if they turned the reminders on). In a duel the reminder is for whoever is behind."""
    if not settings.get("challenges.reminders"):
        return "off"
    lines: dict[int, list[str]] = {}
    closing = db.query(models.Challenge).filter(
        models.Challenge.ends_on == today + datetime.timedelta(days=REMINDER_DAYS), models.Challenge.starts_on <= today, models.Challenge.visibility == "public",
    ).order_by(models.Challenge.id)
    for challenge in closing:
        taking = challenges_crud.participants(db, challenge)
        if not taking or challenges_crud.declined(db, challenge):
            continue
        progress = _progress(db, challenge, taking)
        names = challenges.names_of(db, taking)
        for part in progress["players"]:
            if challenge.scope == challenges.DUEL:
                other = next((p for p in progress["players"] if p["user_id"] != part["user_id"]), None)
                if other is None or challenges.part_value(part) >= challenges.part_value(other):
                    continue
                gap = _amount(part, challenges.part_value(other) - challenges.part_value(part))
                lines.setdefault(part["user_id"], []).append(f"{_bold(challenge.title)}: vas perdiendo contra {_bold(names[other['user_id']])} por {gap}")
            elif part.get("contribution"):
                if not progress["total_done"]:
                    lines.setdefault(part["user_id"], []).append(f"{_bold(challenge.title)}: al grupo le faltan {_hours(progress['total_target_seconds'] - progress['total_seconds'])}")
            elif not part["done"] and not part.get("failed"):  # a lost challenge has nothing left to do
                lines.setdefault(part["user_id"], []).append(f"{_bold(challenge.title)}: {remaining_text(part)}")
    told = 0
    for user_id, user_lines in lines.items():
        try:
            user = _active(db, user_id)
            if user is not None and await tell(db, user, reminders_message(user_lines), reminder=True):
                told += 1
        except Exception as e:  # one player's reminder failing must not cost the others theirs
            db.rollback()
            logger.error(f"Challenge reminder not sent to user {user_id}: {e}", exc_info=True)
    return f"{told} told"
