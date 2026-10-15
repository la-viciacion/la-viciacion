"""The platform catalogue (platform_tags)."""
import re
import unicodedata
from typing import Optional

from fastapi import Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from ...auth import get_db
from ...database import models
from .common import commit, get_or_404, router


PLATFORM_NAME_MAX = 100


def platform_id_for(name: str, taken: set) -> str:
    """A readable, url-safe id for a new platform ("PlayStation 5" -> "playstation-5"), unique among `taken`."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    base = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")[:60] or "platform"
    candidate, n = base, 2
    while candidate in taken:
        candidate = f"{base}-{n}"
        n += 1
    return candidate


def _platform_out(p: models.PlatformTag, sessions: int = 0, library: int = 0) -> dict:
    return {"id": p.id, "name": p.name, "sessions": sessions, "library": library}


def _platform_usage(db: Session, platform_id: str) -> dict:
    return {
        "sesiones": db.query(models.GameTimer).filter_by(platform=platform_id).count(),
        "biblioteca": db.query(models.UserGame).filter_by(platform=platform_id).count(),
    }


def _clean_platform_name(db: Session, name: str, exclude_id: Optional[str] = None) -> str:
    name = (name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="El nombre no puede estar vacío")
    if len(name) > PLATFORM_NAME_MAX:
        raise HTTPException(status_code=400, detail=f"El nombre admite {PLATFORM_NAME_MAX} caracteres como máximo")
    same = db.query(models.PlatformTag).filter(func.lower(models.PlatformTag.name) == name.lower())
    if exclude_id is not None:
        same = same.filter(models.PlatformTag.id != exclude_id)
    if same.first() is not None:
        raise HTTPException(status_code=409, detail="Ya hay una plataforma con ese nombre")
    return name


class PlatformBody(BaseModel):
    name: str


@router.get("/platforms")
def list_platforms(db: Session = Depends(get_db)):
    """Every platform with how many sessions and library entries use it."""
    sessions = dict(
        db.query(models.GameTimer.platform, func.count(models.GameTimer.id))
        .filter(models.GameTimer.platform.isnot(None))
        .group_by(models.GameTimer.platform)
        .all()
    )
    library = dict(
        db.query(models.UserGame.platform, func.count(models.UserGame.id))
        .filter(models.UserGame.platform.isnot(None))
        .group_by(models.UserGame.platform)
        .all()
    )
    platforms = db.query(models.PlatformTag).order_by(models.PlatformTag.name).all()
    return [_platform_out(p, sessions.get(p.id, 0), library.get(p.id, 0)) for p in platforms]


@router.post("/platforms", status_code=201)
def create_platform(body: PlatformBody, db: Session = Depends(get_db)):
    """Add a platform; its id is made from the name and never changes afterwards."""
    name = _clean_platform_name(db, body.name)
    taken = {row[0] for row in db.query(models.PlatformTag.id).all()}
    platform = models.PlatformTag(id=platform_id_for(name, taken), name=name)
    db.add(platform)
    commit(db, "Plataforma")
    return _platform_out(platform)


@router.patch("/platforms/{platform_id}")
def patch_platform(platform_id: str, body: PlatformBody, db: Session = Depends(get_db)):
    """Rename a platform: sessions and library entries keep pointing at it by id."""
    platform = get_or_404(db, models.PlatformTag, platform_id, "Plataforma")
    platform.name = _clean_platform_name(db, body.name, exclude_id=platform_id)
    commit(db, "Plataforma")
    return _platform_out(platform)


@router.delete("/platforms/{platform_id}")
def delete_platform(platform_id: str, db: Session = Depends(get_db)):
    """Delete a platform nobody uses. One that still has sessions or library entries is refused:
    deleting it would leave them without a platform, so rename it or change those first."""
    platform = get_or_404(db, models.PlatformTag, platform_id, "Plataforma")
    usage = {k: v for k, v in _platform_usage(db, platform_id).items() if v}
    if usage:
        detail = " y ".join(f"{v} {k}" for k, v in usage.items())
        raise HTTPException(
            status_code=409,
            detail=f"No se puede borrar: la usan {detail}. Cámbiales la plataforma antes, o renómbrala.",
        )
    db.delete(platform)
    db.commit()
    return {"message": "Plataforma eliminada"}
