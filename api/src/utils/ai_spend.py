"""What the AI has been used for and what it cost, summed from the record of calls (`ai_usage`) when asked.

Nothing is stored here. The figures are an estimate: the tokens are measured, the cost is their price at the time of the call
(utils/ai_cost.py), and a call whose model had no known price counts as a call with no cost (`unpriced`), never as a free one.
The admin sees who spent what only of the calls the group paid for; what a player paid with their own key is shown without
names. A player sees all of their own (`user_id`), whoever paid.
"""
import datetime

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from ..database import models
from . import ai_ledger

A = models.AiUsage
MICROS = 1_000_000
NO_TOOLS = "Sin herramientas"
TOTALS = (
    func.count(A.id).label("calls"),
    func.coalesce(func.sum(A.cost_micros), 0).label("cost"),
    func.coalesce(func.sum(A.input_tokens), 0).label("input"),
    func.coalesce(func.sum(A.cached_tokens), 0).label("cached"),
    func.coalesce(func.sum(A.output_tokens), 0).label("output"),
    func.coalesce(func.sum(A.web_searches), 0).label("searches"),
    func.coalesce(func.sum(case((A.cost_micros.is_(None), 1), else_=0)), 0).label("unpriced"),
    # what it really cost: the estimate, except on a key of a free plan, where it cost nothing
    func.coalesce(func.sum(ai_ledger.real_cost()), 0).label("real"),
    func.coalesce(func.sum(case((A.free_plan.is_(True), 1), else_=0)), 0).label("free"),
)
BY_COST = (func.coalesce(func.sum(A.cost_micros), 0).desc(), func.count(A.id).desc())


def dollars(micros) -> float:
    return round(int(micros or 0) / MICROS, 6)


def _figures(row) -> dict:
    return {
        "calls": int(row.calls), "cost": dollars(row.cost), "input_tokens": int(row.input), "cached_tokens": int(row.cached),
        "output_tokens": int(row.output), "web_searches": int(row.searches), "unpriced": int(row.unpriced),
        "real_cost": dollars(row.real), "free_calls": int(row.free),
    }


def month_bounds(month: str | None) -> tuple[datetime.datetime | None, datetime.datetime | None]:
    """The first moment of the month 'YYYY-MM' and of the next one, or (None, None) for the whole record."""
    if not month:
        return None, None
    start = datetime.datetime.strptime(month, "%Y-%m")
    return start, (start.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)


def _query(db: Session, *columns, start, end, source: str | None = None, user_id: int | None = None):
    query = db.query(*columns)
    if user_id is not None:
        query = query.filter(A.user_id == user_id)
    if start is not None:
        query = query.filter(A.created_at >= start)
    if end is not None:
        query = query.filter(A.created_at < end)
    if source is not None:
        query = query.filter(A.key_source == source)
    return query


def _split(db: Session, *keys, start, end, source: str | None = None, user_id: int | None = None) -> list:
    """The totals of each combination of values of `keys` (columns), the costliest first."""
    return _query(db, *keys, *TOTALS, start=start, end=end, source=source, user_id=user_id).group_by(*keys).order_by(*BY_COST).all()


def _days(db: Session, user_id: int | None = None) -> list:
    """The totals of every day with calls, by whose key paid and by provider: the months and the day-by-day view are made from these."""
    day = func.date(A.created_at)
    query = db.query(day.label("day"), A.key_source.label("source"), A.provider.label("provider"), *TOTALS)
    if user_id is not None:
        query = query.filter(A.user_id == user_id)
    return query.group_by(day, A.key_source, A.provider).order_by(day).all()


def _months(days: list) -> list[dict]:
    """The months with calls. `cost` and its split are estimates; `group_real_cost` is what the group's keys really cost (a key on a
    free plan costs nothing) and `group_openai_real_cost` the part of it that is OpenAI's: the figure to set against what OpenAI
    billed (utils/ai_usage.py), which is the account's, and only OpenAI's."""
    months: dict[str, dict] = {}
    for row in days:
        key = str(row.day)[:7]
        month = months.setdefault(key, {"month": key, "calls": 0, "cost": 0.0, "group_cost": 0.0, "group_real_cost": 0.0, "group_openai_real_cost": 0.0, "user_cost": 0.0, "unpriced": 0})
        month["calls"] += int(row.calls)
        month["cost"] = round(month["cost"] + dollars(row.cost), 6)
        side = "group_cost" if row.source == ai_ledger.GROUP else "user_cost"
        month[side] = round(month[side] + dollars(row.cost), 6)
        if row.source == ai_ledger.GROUP:
            month["group_real_cost"] = round(month["group_real_cost"] + dollars(row.real), 6)
            if row.provider == "openai":
                month["group_openai_real_cost"] = round(month["group_openai_real_cost"] + dollars(row.real), 6)
        month["unpriced"] += int(row.unpriced)
    return list(months.values())


def group_months_by_provider(db: Session) -> dict[str, list[dict]]:
    """What the group's keys really cost each month, from the record, by provider: {provider: [{month, total}]} in dollars (a call
    on a key of a free plan counts as nothing, its estimate aside). It is what the server page shows of every provider whose spend
    cannot be asked (all of them without OpenAI's admin key), and the part of OpenAI's bill that is not its."""
    found: dict[str, dict[str, float]] = {}
    for row in _days(db):
        if row.source != ai_ledger.GROUP:
            continue
        months = found.setdefault(row.provider or "?", {})
        key = str(row.day)[:7]
        months[key] = months.get(key, 0.0) + dollars(row.real)
    return {provider: [{"month": month, "total": round(total, 6)} for month, total in sorted(months.items())] for provider, months in found.items()}


def _by_day(days: list, month: str | None) -> list[dict]:
    """The days of the chosen month (none when the whole record is shown, which has too many)."""
    if not month:
        return []
    shown: dict[str, dict] = {}
    for row in days:
        if str(row.day)[:7] != month:
            continue
        entry = shown.setdefault(str(row.day), {"date": str(row.day), "calls": 0, "cost": 0.0})
        entry["calls"] += int(row.calls)
        entry["cost"] = round(entry["cost"] + dollars(row.cost), 6)
    return list(shown.values())


def summary(db: Session, month: str | None = None, user_id: int | None = None) -> dict:
    """The record of calls as the admin's panel shows it, for one month ('YYYY-MM') or all of it; with `user_id`, only the
    calls of that player (their own panel: the list by player is then left out)."""
    start, end = month_bounds(month)
    window = {"start": start, "end": end, "user_id": user_id}
    days = _days(db, user_id)

    def named(rows, key="name"):
        return [{key: row[0], **_figures(row)} for row in rows]

    models_used = [
        {"name": f"{row.provider or '?'}/{row.model or '?'}", **_figures(row)}
        for row in _split(db, A.provider, A.model, **window)
    ]
    by_user = [] if user_id is not None else [
        {"user_id": row.user_id, "name": row.name or row.username or "Cuenta eliminada", **_figures(row)}
        for row in _query(db, A.user_id, models.User.name.label("name"), models.User.username.label("username"), *TOTALS, **window, source=ai_ledger.GROUP)
        .outerjoin(models.User, models.User.id == A.user_id)
        .group_by(A.user_id, models.User.name, models.User.username)
        .order_by(*BY_COST)
        .all()
    ]
    return {
        "total": _figures(_query(db, *TOTALS, **window).one()),
        "by_source": named(_split(db, A.key_source, **window)),
        "by_feature": named(_split(db, A.feature, **window)),
        "by_model": models_used,
        "by_tools": [{**item, "name": item["name"] or NO_TOOLS} for item in named(_split(db, A.tools, **window))],
        "by_status": [{"name": row.status, "calls": int(row.calls)} for row in _split(db, A.status, **window)],
        "group_paid_by_user": by_user,
        "months": _months(days),
        "days": _by_day(days, month),
        "price_stamp": _query(db, func.max(A.price_stamp), **window).scalar(),
    }
