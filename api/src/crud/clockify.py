import requests
from sqlalchemy import asc, create_engine, desc, func, select, text, update
from sqlalchemy.orm import Session

from ..config import Config
from ..crud import users
from ..database import models
from ..utils import actions as actions
from ..utils import my_utils as utils
from ..utils.clockify_api import ClockifyApi
from ..utils.logger import LogManager

log_manager = LogManager()
logger = log_manager.get_logger()

clockify = ClockifyApi()
config = Config()


def sync_clockify_tags(db: Session):
    tags = clockify.get_tags()
    for tag in tags:
        try:
            if "tracker" not in tag["name"]:
                if "Completed" not in tag["name"] and "Retired" not in tag["name"]:
                    new_tag = models.PlatformTag(id=tag["id"], name=tag["name"])
                    db.add(new_tag)
                    db.commit()
                else:
                    new_tag = models.OtherTag(id=tag["id"], name=tag["name"])
                    db.add(new_tag)
                    db.commit()
        except Exception:
            db.rollback()


def get_platform_by_tag_id(db: Session, tag_id):
    return (
        db.query(models.PlatformTag.name)
        .filter(models.PlatformTag.id == tag_id)
        .first()
    )


def check_completed_tag_by_id(db: Session, tag_id):
    # logger.info("Check completed tag: " + str(tag_id))
    return db.query(models.OtherTag.name).filter(models.OtherTag.id == tag_id).first()
