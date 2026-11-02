"""RAWG, HLTB and IGDB bulk syncs (the first two consume outside quotas, hence the confirmation phrase)."""
from typing import Optional

from fastapi import Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...auth import get_db
from ...clients import igdb
from ...utils import hltb_sync, igdb_sync, rawg_sync
from .common import router


# ── RAWG sync (intensive: consumes the monthly RAWG quota) ──────

RAWG_SYNC_PHRASE = "SINCRONIZAR"


@router.get("/rawg-sync/estimate")
def rawg_sync_estimate(overwrite: bool = False, max_games: Optional[int] = None, db: Session = Depends(get_db)):
    """How many games/calls a sync would take. Makes no RAWG request."""
    if max_games is not None and max_games < 1:
        raise HTTPException(status_code=400, detail="max_games debe ser al menos 1")
    return rawg_sync.estimate(db, overwrite, max_games)


@router.get("/rawg-sync/status")
def rawg_sync_status():
    return rawg_sync.status()


class RawgSyncBody(BaseModel):
    confirm: str                       # must equal RAWG_SYNC_PHRASE (the panel asks for it twice)
    max_calls: int = 2000
    overwrite: bool = False
    max_games: Optional[int] = None    # only the first N pending games, alphabetically; None = all of them


@router.post("/rawg-sync/start", status_code=202)
def rawg_sync_start(body: RawgSyncBody):
    if body.confirm != RAWG_SYNC_PHRASE:
        raise HTTPException(status_code=400, detail="Confirmación incorrecta")
    if not 1 <= body.max_calls <= 20000:
        raise HTTPException(status_code=400, detail="max_calls debe estar entre 1 y 20000")
    if body.max_games is not None and body.max_games < 1:
        raise HTTPException(status_code=400, detail="max_games debe ser al menos 1")
    try:
        started = rawg_sync.start(body.max_calls, body.overwrite, body.max_games)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not started:
        raise HTTPException(status_code=409, detail="Ya hay una sincronización en curso")
    return rawg_sync.status()


@router.post("/rawg-sync/cancel")
def rawg_sync_cancel():
    return {"cancelling": rawg_sync.cancel()}


class RawgApplyBody(BaseModel):
    game_id: str
    rawg_id: int
    overwrite: bool = False


@router.post("/rawg-sync/apply")
def rawg_sync_apply(body: RawgApplyBody, db: Session = Depends(get_db)):
    """Resolve an ambiguous game by choosing its RAWG entry (1-2 RAWG calls)."""
    try:
        return rawg_sync.apply_one(db, body.game_id, body.rawg_id, body.overwrite)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except (ConnectionError, rawg_sync.RawgFatal) as e:
        raise HTTPException(status_code=502, detail=str(e))


# ── IGDB link (fills games.igdb_id in batches; writes nothing else) ──


@router.get("/igdb-sync/estimate")
def igdb_sync_estimate(max_games: Optional[int] = None, db: Session = Depends(get_db)):
    """How many games a batch would go through and how long it takes. Makes no IGDB request."""
    if max_games is not None and max_games < 1:
        raise HTTPException(status_code=400, detail="max_games debe ser al menos 1")
    return igdb_sync.estimate(db, max_games)


@router.get("/igdb-sync/status")
def igdb_sync_status():
    return igdb_sync.status()


class IgdbSyncBody(BaseModel):
    max_games: Optional[int] = None    # only the first N games without an IGDB id, alphabetically; None = all of them


@router.post("/igdb-sync/start", status_code=202)
def igdb_sync_start(body: IgdbSyncBody):
    if body.max_games is not None and body.max_games < 1:
        raise HTTPException(status_code=400, detail="max_games debe ser al menos 1")
    try:
        started = igdb_sync.start(body.max_games)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not started:
        raise HTTPException(status_code=409, detail="Ya hay un enlazado en curso")
    return igdb_sync.status()


@router.post("/igdb-sync/cancel")
def igdb_sync_cancel():
    return {"cancelling": igdb_sync.cancel()}


class IgdbApplyBody(BaseModel):
    game_id: str
    igdb_id: int
    overwrite: bool = False            # the resync of one game: what IGDB gives replaces ours


@router.post("/igdb-sync/apply")
def igdb_sync_apply(body: IgdbApplyBody, db: Session = Depends(get_db)):
    """Resolve a doubtful game by choosing its IGDB entry (one IGDB request)."""
    if not igdb.configured():
        raise HTTPException(status_code=400, detail="No hay credenciales de IGDB configuradas")
    try:
        return igdb_sync.apply_one(db, body.game_id, body.igdb_id, body.overwrite)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except igdb.IgdbError as e:
        raise HTTPException(status_code=502, detail=str(e))


# ── HLTB sync (average time to complete; replaces the stored times) ──


class HltbSyncBody(BaseModel):
    confirm: str                       # must equal RAWG_SYNC_PHRASE too: it replaces the time of every game it goes through
    scope: str = "all"                 # "all", "missing", "suspicious" or "recent" (see utils/hltb_sync.py)
    limit: Optional[int] = None        # "recent": how many of the games played most recently


@router.get("/hltb-sync/estimate")
def hltb_sync_estimate(scope: str = "all", limit: Optional[int] = None, db: Session = Depends(get_db)):
    """How many games and how long a sync of those would take. Makes no HLTB request."""
    try:
        return hltb_sync.estimate(db, scope, limit)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/hltb-sync/status")
def hltb_sync_status():
    return hltb_sync.status()


@router.post("/hltb-sync/start", status_code=202)
def hltb_sync_start(body: HltbSyncBody):
    if body.confirm != RAWG_SYNC_PHRASE:
        raise HTTPException(status_code=400, detail="Confirmación incorrecta")
    try:
        started = hltb_sync.start(body.scope, body.limit)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not started:
        raise HTTPException(status_code=409, detail="Ya hay una sincronización en curso")
    return hltb_sync.status()


@router.post("/hltb-sync/cancel")
def hltb_sync_cancel():
    return {"cancelling": hltb_sync.cancel()}
