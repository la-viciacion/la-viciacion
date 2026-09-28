from sqlalchemy.orm import Session
from ..utils import actions as actions

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi_versioning import version

from ..database.database import SessionLocal
from ..utils import actions as actions
from ..utils.logger import LogManager
from ..config import Config
import threading

log_manager = LogManager()
logger = log_manager.get_logger()
process_lock = threading.Lock()
config = Config()

router = APIRouter(
    prefix="/webhooks", tags=["Webhooks"], responses={404: {"description": "Not found"}}
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/sync-data")
@version(1)
async def webhook_sync(
    request: Request, db: Session = Depends(get_db), include_in_schema=False
):
    """Recompute stats/rankings/achievements (cron entrypoint)"""
    with process_lock:
        api_key = request.headers.get("x-api-key")
        if api_key != config.API_KEY:
            raise HTTPException(status_code=401, detail="Unauthorized")
        logger.info("Sync from cron")

        await actions.recompute_all_users_and_rankings(
            db,
            silent=False,
            sync_season=False,
            sync_all=False,
            only_active_users=True,
        )
        return {"message": "Sync completed!"}
