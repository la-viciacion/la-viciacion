"""The one router of the admin panel API and the helpers its areas share."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ... import auth
from ...utils import audit

router = APIRouter(
    prefix="/manage",
    tags=["Manage"],
    # `remember` and AuditedRoute write every successful change of the panel to the audit log (utils/audit.py)
    dependencies=[Depends(auth.require_admin), Depends(audit.remember)],
    route_class=audit.AuditedRoute,
)


def commit(db: Session, what: str):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"{what}: conflicto con un registro existente")


def get_or_404(db: Session, model, key, what: str):
    row = db.get(model, key)
    if row is None:
        raise HTTPException(status_code=404, detail=f"{what} no encontrado")
    return row


def confirm_or_409(counts: dict, force: bool):
    """Refuse to delete something with dependants unless the admin forced it."""
    counts = {k: v for k, v in counts.items() if v}
    if counts and not force:
        raise HTTPException(status_code=409, detail={"message": "Tiene datos asociados", "counts": counts})


def ordered(query, column, order: str, tie_breaker):
    """ORDER BY `column` (asc/desc); the id keeps pages stable when values repeat."""
    direction = column.desc() if order == "desc" else column.asc()
    return query.order_by(direction, tie_breaker.desc() if order == "desc" else tie_breaker.asc())


def like(term: str) -> str:
    return "%" + term.replace("%", r"\%").replace("_", r"\_") + "%"
