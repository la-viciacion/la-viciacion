"""What the group spends to keep the app running (cost_items). The server's own rate is kept by a daily job from Hetzner;
the rest (the domain, anything else) is typed in here."""
import datetime
from typing import Optional

from fastapi import Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...auth import get_db
from ...crud import costs
from ...database import models
from .common import commit, get_or_404, router


class CostBody(BaseModel):
    name: str
    kind: str
    amount: float  # euros
    period: str
    starts_on: datetime.date
    ends_on: Optional[datetime.date] = None
    note: Optional[str] = None


class CostPatch(BaseModel):
    name: Optional[str] = None
    kind: Optional[str] = None
    amount: Optional[float] = None
    period: Optional[str] = None
    starts_on: Optional[datetime.date] = None
    ends_on: Optional[datetime.date] = None
    note: Optional[str] = None


def _out(row: models.CostItem) -> dict:
    return {
        "id": row.id, "name": row.name, "kind": row.kind, "amount": row.amount_cents / 100, "period": row.period,
        "starts_on": row.starts_on, "ends_on": row.ends_on, "source": row.source, "note": row.note,
    }


def _valid(fields: dict) -> dict:
    try:
        return costs.clean(fields)
    except costs.CostError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/costs")
def list_costs(db: Session = Depends(get_db)):
    """Every rate, the newest first."""
    rows = db.query(models.CostItem).order_by(models.CostItem.starts_on.desc(), models.CostItem.id.desc()).all()
    return [_out(row) for row in rows]


@router.post("/costs", status_code=201)
def create_cost(body: CostBody, db: Session = Depends(get_db)):
    row = models.CostItem(source="manual", **_valid(body.model_dump()))
    db.add(row)
    commit(db, "Gasto")
    return _out(row)


@router.patch("/costs/{cost_id}")
def patch_cost(cost_id: int, body: CostPatch, db: Session = Depends(get_db)):
    """Change a rate. A `ends_on` that is sent empty clears the end; any other field that is not sent stays as it was."""
    row = get_or_404(db, models.CostItem, cost_id, "Gasto")
    fields = {
        "name": row.name, "kind": row.kind, "amount": row.amount_cents / 100, "period": row.period,
        "starts_on": row.starts_on, "ends_on": row.ends_on, "note": row.note,
    }
    fields.update(body.model_dump(exclude_unset=True))
    for key, value in _valid(fields).items():
        setattr(row, key, value)
    commit(db, "Gasto")
    return _out(row)


@router.delete("/costs/{cost_id}")
def delete_cost(cost_id: int, db: Session = Depends(get_db)):
    """Delete a rate. The server's, if it was the open one, is opened again by the daily job from the day the server was
    created, so close it with an end date instead of deleting it to stop counting a server that is gone."""
    db.delete(get_or_404(db, models.CostItem, cost_id, "Gasto"))
    db.commit()
    return {"message": "Gasto eliminado"}
