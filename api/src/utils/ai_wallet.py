"""The wallet of the group's AI key: what each player put in and what they have left to spend of it.

The group pays the AI with one key and one account, so what a player spends of it is taken from what they contributed. A player's
**balance** is their contributions minus what the group's key spent on their calls since the wallet started, both summed when
asked (nothing is cached: the contributions are the one stored fact, `ai_wallet_entries`, and the spending is `ai_usage`). Only
what the group's key paid counts, at what it really cost (`ai_ledger.real_cost`): a player's own key spends nobody else's money.

The wallet is **off until the first contribution is written down**: before it the monthly budgets (utils/ai_budget.py) are the only
limit, so nothing changes for a group that does not use it. Once it is on, a player whose balance is 0 or less is stopped before
the group's key pays for a question (`ai_budget.exceeded` asks), and the balance can go below zero because the cost of a call is
known only when it ends. What counts as spending starts on `ai.wallet_start` (a date an admin can set) or, without it, at the moment
of the first contribution, so the history before the wallet does not leave everybody in debt. The monthly budgets still apply on top.

Amounts are millionths of a dollar, as in `ai_usage`; a contribution may be negative (a refund, a correction) and none is edited."""
import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import models
from . import ai_ledger, settings

MICROS = 1_000_000
MAX_USD = 10000


def active(db: Session) -> bool:
    """Whether the wallet is in use: at least one contribution has been written down."""
    return db.query(models.AiWalletEntry.id).first() is not None


def start(db: Session) -> datetime.datetime | None:
    """When the wallet starts counting the group's spending: the date an admin set or the moment of the first contribution
    (None while there is none)."""
    chosen = settings.get("ai.wallet_start")
    if chosen:
        return datetime.datetime.combine(datetime.date.fromisoformat(chosen), datetime.time.min)
    return db.query(func.min(models.AiWalletEntry.created_at)).scalar()


def contributed(db: Session, user_id: int | None = None) -> int:
    """Millionths of a dollar put in, by one player or by everybody (the money of a deleted account included)."""
    query = db.query(func.coalesce(func.sum(models.AiWalletEntry.amount_micros), 0))
    if user_id is not None:
        query = query.filter(models.AiWalletEntry.user_id == user_id)
    return int(query.scalar() or 0)


def spent(db: Session, user_id: int | None = None) -> int:
    """Millionths of a dollar the group's key has spent since the wallet started, on the calls of one player or of everybody."""
    since = start(db)
    if since is None:
        return 0
    query = db.query(func.coalesce(func.sum(ai_ledger.real_cost()), 0)).filter(
        models.AiUsage.key_source == ai_ledger.GROUP, models.AiUsage.created_at >= since
    )
    if user_id is not None:
        query = query.filter(models.AiUsage.user_id == user_id)
    return int(query.scalar() or 0)


def balance(db: Session, user_id: int) -> int:
    return contributed(db, user_id) - spent(db, user_id)


def empty(db: Session, user_id: int) -> bool:
    """Whether the wallet is on and this player has nothing left in it (0 or less)."""
    return active(db) and balance(db, user_id) <= 0


def _usd(micros: int) -> float:
    return round(micros / MICROS, 6)


def player(db: Session, user_id: int) -> dict | None:
    """For the player's own screen: their part of the wallet, or None while the wallet is off."""
    if not active(db):
        return None
    put, used = contributed(db, user_id), spent(db, user_id)
    return {"contributed": _usd(put), "spent": _usd(used), "balance": _usd(put - used), "since": start(db).date().isoformat()}


def overview(db: Session, entries: int = 50) -> dict:
    """For the admin: the wallet of the group (what is in, what is spent and what is left, to set against the balance of the
    OpenAI account), each player's part and the latest contributions."""
    since = start(db)
    put_by = dict(
        db.query(models.AiWalletEntry.user_id, func.sum(models.AiWalletEntry.amount_micros))
        .filter(models.AiWalletEntry.user_id.isnot(None)).group_by(models.AiWalletEntry.user_id).all()
    )
    spent_by = {}
    if since is not None:
        spent_by = dict(
            db.query(models.AiUsage.user_id, func.coalesce(func.sum(ai_ledger.real_cost()), 0))
            .filter(models.AiUsage.key_source == ai_ledger.GROUP, models.AiUsage.created_at >= since, models.AiUsage.user_id.isnot(None))
            .group_by(models.AiUsage.user_id).all()
        )
    players = []
    for user in db.query(models.User).filter(models.not_god()).order_by(models.User.username).all():
        put, used = int(put_by.get(user.id, 0) or 0), int(spent_by.get(user.id, 0) or 0)
        players.append({
            "user_id": user.id, "name": user.name or user.username, "is_active": bool(user.is_active),
            "contributed": _usd(put), "spent": _usd(used), "balance": _usd(put - used),
        })
    total_in, total_out = contributed(db), spent(db)
    names = {u.id: u.name or u.username for u in db.query(models.User).all()}
    latest = db.query(models.AiWalletEntry).order_by(models.AiWalletEntry.id.desc()).limit(entries).all()
    return {
        "active": active(db),
        "start": since.date().isoformat() if since else None,
        "start_setting": settings.get("ai.wallet_start"),
        "total": {"contributed": _usd(total_in), "spent": _usd(total_out), "available": _usd(total_in - total_out)},
        "players": players,
        "entries": [
            {
                "id": e.id, "created_at": e.created_at.isoformat(), "user_id": e.user_id, "name": names.get(e.user_id),
                "usd": _usd(e.amount_micros), "note": e.note, "by": names.get(e.created_by),
            }
            for e in latest
        ],
    }


def add(db: Session, user_id: int, usd: float, note: str | None, by: int | None) -> models.AiWalletEntry:
    """Writes down a contribution (or, if negative, a refund or a correction). Rounded to the millionth of a dollar."""
    entry = models.AiWalletEntry(user_id=user_id, amount_micros=round(usd * MICROS), note=(note or "").strip() or None, created_by=by)
    db.add(entry)
    db.commit()
    return entry
