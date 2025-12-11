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
    """Sync using webhook"""
    with process_lock:
        headers = request.headers
        try:
            api_key = headers.get("x-api-key")
            if api_key != config.API_KEY:
                raise HTTPException(status_code=401, detail="Unauthorized")
            user_id = None
            event = None
            logger.info("Sync from cron")
        except:
            try:
                event = headers.get("clockify-webhook-event-type")
                signature = headers.get("clockify-signature")
                if signature in config.CLOCKIFY_SIGNATURES:
                    data = await request.json()
                    user_id = data["user"]["id"]
                    logger.info(f"Evet: {event}")
                    logger.info("Sync from Clockify TimeEntry")
                else:
                    raise HTTPException(status_code=401, detail="Unauthorized")
            except:
                raise HTTPException(status_code=400, detail="Bad Request")

        sync_result = await actions.sync_data(
            user_clfy_id=user_id,
            sync_season=False,
            silent=False,
            sync_all=False,
            only_acive_users=True,
            only_time_entries=False,
            db=db,
        )
        return sync_result
