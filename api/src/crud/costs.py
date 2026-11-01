"""The rates in `cost_items` (utils/costs.py derives what they cost): reading them, keeping the Hetzner server's up to
date, and checking what an admin types."""
import datetime

from sqlalchemy.orm import Session

from ..database import models
from ..utils.costs import KINDS, PERIODS

NAME_MAX = 100
NOTE_MAX = 255
AMOUNT_MAX_EUROS = 1_000_000
HETZNER = "hetzner"


class CostError(ValueError):
    """What an admin sent is not a valid rate; the text is Spanish and shown as it is."""


def as_dict(row: models.CostItem) -> dict:
    return {
        "id": row.id, "name": row.name, "kind": row.kind, "amount_cents": row.amount_cents, "hourly_micros": row.hourly_micros,
        "period": row.period, "starts_on": row.starts_on, "ends_on": row.ends_on, "source": row.source, "note": row.note,
    }


def all_items(db: Session) -> list[dict]:
    return [as_dict(row) for row in db.query(models.CostItem).all()]


def sync_server(db: Session, price: dict, today: datetime.date) -> str:
    """Makes the open Hetzner rate of the server match `price` (`amount_cents`, `hourly_micros`, `external_id`, `name`,
    `created`): the first time it opens one from the day the server was created, and when the price changes it closes
    the open one the day before and opens another from today. A change on the very day a rate began just corrects it.
    Idempotent: what it returns is `created`, `changed` or `unchanged`."""
    open_rate = (
        db.query(models.CostItem)
        .filter_by(source=HETZNER, external_id=price["external_id"], ends_on=None)
        .order_by(models.CostItem.starts_on.desc())
        .first()
    )
    fresh = {"amount_cents": price["amount_cents"], "hourly_micros": price["hourly_micros"]}
    if open_rate is None:
        db.add(models.CostItem(
            name=price["name"], kind="server", period="month", starts_on=price["created"], source=HETZNER,
            external_id=price["external_id"], **fresh,
        ))
        db.commit()
        return "created"
    if all(getattr(open_rate, key) == value for key, value in fresh.items()):
        return "unchanged"
    if open_rate.starts_on >= today:
        for key, value in fresh.items():
            setattr(open_rate, key, value)
    else:
        open_rate.ends_on = today - datetime.timedelta(days=1)
        db.add(models.CostItem(
            name=open_rate.name, kind="server", period="month", starts_on=today, source=HETZNER, external_id=price["external_id"], **fresh,
        ))
    db.commit()
    return "changed"


def clean(fields: dict) -> dict:
    """The columns of a rate from what an admin typed (`amount` in euros), or a CostError that says what is wrong."""
    name = (fields.get("name") or "").strip()
    if not name:
        raise CostError("El concepto no puede estar vacío")
    if len(name) > NAME_MAX:
        raise CostError(f"El concepto admite {NAME_MAX} caracteres como máximo")
    if fields.get("kind") not in KINDS:
        raise CostError("El tipo de gasto no es válido")
    if fields.get("period") not in PERIODS:
        raise CostError("La periodicidad no es válida")
    amount = fields.get("amount")
    if amount is None or not 0 <= amount <= AMOUNT_MAX_EUROS:
        raise CostError(f"El importe tiene que estar entre 0 y {AMOUNT_MAX_EUROS} €")
    starts_on, ends_on = fields.get("starts_on"), fields.get("ends_on")
    if starts_on is None:
        raise CostError("Falta la fecha de inicio")
    if fields["period"] == "once":
        ends_on = None  # a one-off cost has a day, not a span
    elif ends_on is not None and ends_on < starts_on:
        raise CostError("La fecha de fin no puede ser anterior a la de inicio")
    note = (fields.get("note") or "").strip() or None
    if note and len(note) > NOTE_MAX:
        raise CostError(f"La nota admite {NOTE_MAX} caracteres como máximo")
    return {
        "name": name, "kind": fields["kind"], "period": fields["period"], "amount_cents": round(amount * 100),
        "starts_on": starts_on, "ends_on": ends_on, "note": note,
    }
