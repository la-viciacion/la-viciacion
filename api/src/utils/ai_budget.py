"""The monthly budget of the group's AI key: how much it may spend in a calendar month, and each player's share of it.

Only what the **group's key paid** counts (`ai_usage.key_source = 'group'`): what a player pays with their own key spends nobody
else's money and is never limited here. And it counts at what the call really cost: a call on a key of a free plan counts as nothing,
whatever its estimate says (`ai_usage.free_plan`). Two caps, in whole dollars. A cap that is not set (empty, None) is no limit and a
cap of 0 is exactly that: nothing of the group's key (a player can still use their own):

  `ai.group_budget_month`   everything the group's key spends in the month, whoever asked
  `ai.user_budget_month`    what each player may spend of it; an admin can give one player another amount
                            (`user_settings.ai_group_budget_usd`: NULL = this default, 0 = nothing of the group's key)

It is checked before a question that the group would pay for (utils/ai_source.py), against the usage record, which is summed when
asked: nothing is cached or stored. The cost of a call is known only when it ends, so a budget can be passed by one question; a
call whose model has no known price counts as nothing (the panel says how many there are). The month is the server's calendar
month: the budgets start again on the 1st. On top of them, once the wallet is on, a player with no balance left is stopped too
(utils/ai_wallet.py)."""
import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import models
from . import ai_ledger, ai_wallet, settings

MICROS = 1_000_000
GROUP, USER = "group", "user"  # which budget is spent
GROUP_OFF, USER_OFF = "group_off", "user_off"  # the budget is 0: nothing of the group's key for everybody, or for this player
WALLET = "wallet"  # the wallet is on (utils/ai_wallet.py) and this player has nothing left in it


def month_start(now: datetime.datetime | None = None) -> datetime.datetime:
    now = now or datetime.datetime.now()
    return datetime.datetime(now.year, now.month, 1)


def next_month(now: datetime.datetime | None = None) -> datetime.datetime:
    start = month_start(now)
    return (start.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)


def _cap(value) -> int | None:
    return None if value is None else int(value)


def group_cap() -> int | None:
    """Whole dollars the group's key may spend a month: None is no limit, 0 is nothing."""
    return _cap(settings.get("ai.group_budget_month"))


def default_user_cap() -> int | None:
    """What each player may spend of the group's key a month unless an admin says otherwise (None: no limit)."""
    return _cap(settings.get("ai.user_budget_month"))


def user_cap(db: Session, user_id: int) -> int | None:
    """Whole dollars this player may spend of the group's key a month: what an admin gave them, or the default; None is no limit,
    0 is nothing."""
    row = db.get(models.UserSettings, user_id)
    if row is not None and row.ai_group_budget_usd is not None:
        return int(row.ai_group_budget_usd)
    return default_user_cap()


def spent(db: Session, user_id: int | None = None, now: datetime.datetime | None = None) -> int:
    """Millionths of a dollar the group's key has spent this month, on the calls of one player or of everybody."""
    query = db.query(func.coalesce(func.sum(ai_ledger.real_cost()), 0)).filter(
        models.AiUsage.key_source == ai_ledger.GROUP, models.AiUsage.created_at >= month_start(now)
    )
    if user_id is not None:
        query = query.filter(models.AiUsage.user_id == user_id)
    return int(query.scalar() or 0)


def unpriced(db: Session, now: datetime.datetime | None = None) -> dict:
    """The calls of this month that the group's key paid and that spent tokens but have no cost, because the price list has no price
    for their model: they count as nothing in any budget, so the caps cannot limit them. `calls` and the `models` they used."""
    unknown = (
        models.AiUsage.key_source == ai_ledger.GROUP, models.AiUsage.created_at >= month_start(now),
        models.AiUsage.cost_micros.is_(None), models.AiUsage.input_tokens + models.AiUsage.output_tokens > 0,
    )
    found = db.query(models.AiUsage.provider, models.AiUsage.model, func.count(models.AiUsage.id)).filter(*unknown).group_by(
        models.AiUsage.provider, models.AiUsage.model
    ).all()
    return {"calls": sum(int(n) for _, _, n in found), "models": sorted(f"{p or '?'}/{m or '?'}" for p, m, _ in found)}


def exceeded(db: Session, user_id: int, now: datetime.datetime | None = None) -> str | None:
    """`GROUP` if the group has spent its budget of the month, `USER` if this player has spent theirs, `WALLET` if the wallet is on
    and their balance is spent, else None. A budget of 0 has nothing to spend: `GROUP_OFF` / `USER_OFF`."""
    cap = group_cap()
    if cap is not None and (cap == 0 or spent(db, None, now) >= cap * MICROS):
        return GROUP_OFF if cap == 0 else GROUP
    own = user_cap(db, user_id)
    if own is not None and (own == 0 or spent(db, user_id, now) >= own * MICROS):
        return USER_OFF if own == 0 else USER
    return WALLET if ai_wallet.empty(db, user_id) else None


WARN_AT = 0.8  # the share of the group's budget at which the admins are warned, once a month


def alert_level(db: Session, now: datetime.datetime | None = None) -> int | None:
    """How much of the group's budget this month is spent as a warning level: 100 when it is all spent, 80 from eighty percent,
    None below that or without a cap (an admin warning is about the group's budget, not a player's)."""
    cap = group_cap()
    if not cap:  # no limit, or none to spend: nothing to warn about
        return None
    spent_now = spent(db, None, now)
    if spent_now >= cap * MICROS:
        return 100
    return int(WARN_AT * 100) if spent_now >= WARN_AT * cap * MICROS else None


def top_spenders(db: Session, now: datetime.datetime | None = None, limit: int = 3) -> list[dict]:
    """The players that have spent most of the group's key this month (only those that spent something)."""
    ranked = sorted((p for p in players(db, now) if p["spent"] > 0), key=lambda p: -p["spent"])
    return ranked[:limit]


def usage(db: Session, user_id: int, now: datetime.datetime | None = None) -> dict:
    """For the player's screen: what the group's key has spent this month against each cap (dollars; a cap of 0 is no limit)."""
    start = month_start(now)
    return {
        "month": start.strftime("%Y-%m"),
        "resets_on": next_month(now).date().isoformat(),
        "group": {"cap": group_cap(), "spent": round(spent(db, None, now) / MICROS, 6)},
        "user": {"cap": user_cap(db, user_id), "spent": round(spent(db, user_id, now) / MICROS, 6)},
    }


def set_user_cap(db: Session, user_id: int, usd: int | None) -> None:
    """An admin gives a player another budget than the default (None goes back to the default, 0 is no limit)."""
    row = db.get(models.UserSettings, user_id)
    if row is None:
        row = models.UserSettings(user_id=user_id)
        db.add(row)
    row.ai_group_budget_usd = usd
    db.commit()


def players(db: Session, now: datetime.datetime | None = None) -> list[dict]:
    """Every player with what they may spend of the group's key this month and what they have spent: the admin's table."""
    start = month_start(now)
    spent_by = {
        user_id: (int(cost), int(calls))
        for user_id, cost, calls in db.query(
            models.AiUsage.user_id, func.coalesce(func.sum(ai_ledger.real_cost()), 0), func.count(models.AiUsage.id)
        ).filter(models.AiUsage.key_source == ai_ledger.GROUP, models.AiUsage.created_at >= start, models.AiUsage.user_id.isnot(None))
        .group_by(models.AiUsage.user_id).all()
    }
    default = default_user_cap()
    overrides = dict(db.query(models.UserSettings.user_id, models.UserSettings.ai_group_budget_usd).all())
    out = []
    for user in db.query(models.User).filter(models.not_god()).order_by(models.User.username).all():
        cost, calls = spent_by.get(user.id, (0, 0))
        override = overrides.get(user.id)
        out.append({
            "user_id": user.id,
            "name": user.name or user.username,
            "is_active": bool(user.is_active),
            "override": override,
            "cap": default if override is None else int(override),
            "spent": round(cost / MICROS, 6),
            "calls": calls,
        })
    return out
