"""The notice of the recap of a month or a season: it only says that the recap is ready and where to see it. The figures
are in the page and the story (`crud/recap.py`), not in the notice.

It is one notice, the same on both channels: the Telegram group and the app's devices (push), where a tap opens the story."""
import datetime

from sqlalchemy.orm import Session

from ..config import Config
from ..crud import recap
from ..database import models
from . import my_utils as utils
from . import push
from .logger import LogManager

logger = LogManager().get_logger()
config = Config()

MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def period_label(period: recap.Period) -> str:
    """"septiembre de 2026" or "temporada 2026"."""
    if period.kind == "month":
        return f"{MONTHS[period.start.month - 1]} de {period.start.year}"
    return f"temporada {period.start.year}"


def previous_month(today: datetime.date) -> recap.Period:
    """The month that has just ended."""
    return recap.month_period(today.year, today.month).previous()


def annual_period(day: datetime.date) -> recap.Period:
    """The season the annual job reports on when it runs on `day`: the running one in December (what there is so far),
    the one that has just ended in January."""
    return recap.year_period(day.year if day.month == 12 else day.year - 1)


def kind_word(period: recap.Period) -> str:
    """"mensual" or "anual": all the notice says about which recap it is (the period is in the link, not in the text)."""
    return "mensual" if period.kind == "month" else "anual"


def push_payload(period: recap.Period) -> dict:
    """The notice for the app's devices."""
    return push.build_recap_payload(kind_word(period), period.key)


def telegram_text(period: recap.Period) -> str:
    """The same notice for Telegram: the title and the link to the story (without a public address there is no link)."""
    title = f"🎬 *Ya está disponible el resumen {kind_word(period)}*"
    if not config.PUBLIC_URL:
        return f"{title}\n\nMíralo en historias dentro de la app."
    return f"{title}\n\n[Pulsa para verlo en historias]({config.PUBLIC_URL}/#/story/{period.key})"


async def announce_recap(db: Session, period: recap.Period, only: models.User | None = None) -> dict:
    """Send the notice of the period to the Telegram group and to the app's devices that want the group's notices, or, with
    `only`, to that user alone (an admin trying it: their own Telegram chat and devices).

    A period in which nobody played sends nothing. The general notifications switch is respected by the senders.
    Returns {"empty": nobody played}."""
    if not recap.anyone_played(db, period):
        return {"empty": True}
    if only is not None:
        await utils.send_message_to_user(only.telegram_id, telegram_text(period), user_id=only.id, push_payload=push_payload(period))
    else:
        await utils.send_message(telegram_text(period), silent=False, push_payload=push_payload(period))
    return {"empty": False}


def describe(result: dict, only: bool = False) -> str:
    """The result of `announce_recap` as the status of a job run."""
    if result["empty"]:
        return "nobody played"
    return "sent to the admin" if only else "sent to the group"
