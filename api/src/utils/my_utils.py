import asyncio
import datetime
import json
import re
from io import BytesIO

import requests
import telegram
from howlongtobeatpy import HowLongToBeat
from PIL import Image
from sqlalchemy import asc, create_engine, desc, func, or_, select, text, update
from sqlalchemy.orm import Session

from ..config import Config
from ..crud import games, time_entries, users
from ..database import models, schemas
from .achievements import AchievementsElems
from ..clients.open_ai import OpenAIClient
from ..utils import ai_prompts as prompts
from . import push, settings
from .redaction import redact_rawg_key
from ..utils.logger import LogManager

log_manager = LogManager()
logger = log_manager.get_logger()

oai_client = OpenAIClient()
config = Config()


def escape_markdown(text) -> str:
    """Escape what Telegram's legacy Markdown reads as formatting, for names inside a message."""
    return re.sub(r"([_*`\[])", r"\\\1", str(text))


def validate_password_requirements(password):
    # Length
    if len(password) < 12 or len(password) > 24:
        return False

    # Uppercase
    if not re.search(r"[A-Z]", password):
        return False

    # Lowercase
    if not re.search(r"[a-z]", password):
        return False

    # Number
    if not re.search(r"\d", password):
        return False

    # Special character
    if not re.search(r"[!@#$%^&*()_+{}\[\]:;<>,.?/~\\-]", password):
        return False

    return True


def validate_email_format(email):
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    if re.match(pattern, email):
        return True
    else:
        return False


def normalize_email(email) -> str | None:
    """Trim and lower-case an email; blank becomes None."""
    return (email or "").strip().lower() or None


def validate_username(username) -> str | None:
    """Error message for an invalid nickname, or None when it is fine.
    No "@" so a nickname can never be mistaken for somebody's email at login."""
    if not (username or "").strip():
        return "El usuario no puede estar vacío"
    if "@" in username:
        return 'El usuario no puede contener "@" (el email es el identificador de inicio de sesión)'
    if any(c.isspace() for c in username):
        return "El usuario no puede contener espacios"
    return None


def convert_time_to_hours(seconds) -> str:
    if seconds is None:
        return "00:00"
    seconds = int(seconds)  # SQL sums come back as Decimal
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    return f"{hours:02d}:{minutes:02d}"


def convert_hours_minutes_to_seconds(time) -> int:
    if time is None:
        return 0
    return time * 3600


def convert_date_from_text(date: str):
    # logger.debug("Converting date")
    if date is None or date == "":
        return date
    if ":" not in date:
        return datetime.datetime.strptime(date, "%Y-%m-%d")
    return datetime.datetime.strptime(date, "%Y-%m-%d %H:%M:%S")


def get_week_range_dates(weeks_diff: int = 0):
    if weeks_diff < 0:
        raise ValueError("weeks_diff must be greater than or equal to 0")
    current_date = datetime.datetime.now()
    first_day_current_week = current_date - datetime.timedelta(
        days=current_date.weekday()
    )
    first_day_n_weeks_ago = first_day_current_week - datetime.timedelta(
        weeks=weeks_diff
    )
    last_day_n_weeks_ago = first_day_n_weeks_ago + datetime.timedelta(days=6)
    return first_day_n_weeks_ago.date(), last_day_n_weeks_ago.date()


def get_last_week_range_dates():
    current_date = datetime.datetime.now()
    first_day_current_week = current_date - datetime.timedelta(
        days=current_date.weekday()
    )
    first_day_last_week = first_day_current_week - datetime.timedelta(days=7)
    last_day_last_week = first_day_current_week - datetime.timedelta(days=1)
    return first_day_last_week.date(), last_day_last_week.date()


def get_current_week_range_dates():
    current_date = datetime.datetime.now()
    first_day_current_week = current_date - datetime.timedelta(
        days=current_date.weekday()
    )
    last_day_current_week = first_day_current_week + datetime.timedelta(days=6)
    return first_day_current_week.date(), last_day_current_week.date()


def day_of_the_year(date):
    date = datetime.datetime.strptime(date, "%Y-%m-%d %H:%M:%S")
    return date.timetuple().tm_yday


def date_from_day_of_the_year(day):
    current_date = datetime.datetime.now()
    start_date_base = datetime.datetime.strptime(
        str(current_date.year) + "-01-01", "%Y-%m-%d"
    )
    start_date = datetime.datetime(
        start_date_base.year, start_date_base.month, start_date_base.day
    )
    current_date = start_date + datetime.timedelta(days=day - 1)
    return current_date.strftime("%Y-%m-%d")


def date_from_datetime(datetime: str):
    return datetime.split(" ")[0]


async def _http_get(url: str, params: dict, timeout: int):
    """`requests` blocks: run it in a thread so the event loop keeps serving everybody else."""
    return await asyncio.to_thread(requests.get, url, params=params, timeout=timeout)


async def search_rawg_games(query: str, db: Session = None) -> list[schemas.RawgGameCandidate]:
    """Search games in RAWG.io and return candidates, checking if they exist in the DB."""
    api_key = config.RAWG_API_KEY
    if not api_key:
        logger.warning("No RAWG API key configured")
        return []

    url = "https://api.rawg.io/api/games"
    params = {"key": api_key, "search": query, "page": 1, "page_size": 10}
    try:
        resp = await _http_get(url, params, timeout=10)
        if not resp.ok:
            logger.error(f"RAWG search error {resp.status_code}: {redact_rawg_key(resp.content)}")
            return []
        data = resp.json()
        results = data.get("results", [])
    except Exception as e:
        logger.error(f"Error searching RAWG for '{query}': {redact_rawg_key(e)}")
        return []

    candidates = []
    for item in results:
        rawg_id = item.get("id")
        name = item.get("name", "")
        slug = item.get("slug", "")
        released = item.get("released")
        image_url = item.get("background_image")
        genres = [g["name"] for g in item.get("genres", []) if "name" in g]
        platforms = [
            p.get("platform", {}).get("name")
            for p in item.get("platforms", [])
            if p.get("platform", {}).get("name")
        ]
        rating = item.get("rating")
        metacritic = item.get("metacritic")

        exists_in_db = False
        db_game_id = None
        if db is not None and (rawg_id or slug or name):
            filters = []
            if rawg_id:
                filters.append(models.Game.rawg_id == rawg_id)
            if slug:
                filters.append(models.Game.slug == slug)
            if name:
                filters.append(models.Game.name == name)
            existing = db.query(models.Game).filter(or_(*filters)).first()
            if existing:
                exists_in_db = True
                db_game_id = existing.id

        candidates.append(
            schemas.RawgGameCandidate(
                rawg_id=rawg_id,
                name=name,
                slug=slug,
                released=released,
                image_url=image_url,
                genres=genres,
                platforms=platforms,
                rating=rating,
                metacritic=metacritic,
                exists_in_db=exists_in_db,
                db_game_id=db_game_id,
            )
        )
    return candidates


async def get_game_details_by_rawg_id(rawg_id: int) -> dict | None:
    """Fetch complete game details from RAWG.io by rawg_id, including developers and Steam ID."""
    api_key = config.RAWG_API_KEY
    if not api_key:
        return None

    url = f"https://api.rawg.io/api/games/{rawg_id}"
    params = {"key": api_key}
    try:
        resp = await _http_get(url, params, timeout=10)
        if not resp.ok:
            logger.error(f"RAWG details error {resp.status_code}: {redact_rawg_key(resp.content)}")
            return None
        data = resp.json()
    except Exception as e:
        logger.error(f"Error fetching RAWG details for id {rawg_id}: {redact_rawg_key(e)}")
        return None

    name = data.get("name", "")
    slug = data.get("slug", "")
    released = data.get("released")
    image_url = data.get("background_image")
    genres = ",".join([g["name"] for g in data.get("genres", []) if "name" in g])

    # Developers and publishers from RAWG
    dev_list = [d["name"] for d in data.get("developers", []) if "name" in d]
    if not dev_list:
        dev_list = [p["name"] for p in data.get("publishers", []) if "name" in p]
    dev = ", ".join(dev_list) if dev_list else "-"

    # Steam ID from stores endpoint
    steam_id = ""
    try:
        stores_resp = await _http_get(
            f"https://api.rawg.io/api/games/{rawg_id}/stores", params, timeout=6
        )
        if stores_resp.ok:
            stores_data = stores_resp.json().get("results", [])
            for s in stores_data:
                u = s.get("url", "")
                if "steampowered.com/app/" in u:
                    match = re.search(r"app/(\d+)", u)
                    if match:
                        steam_id = match.group(1)
                        break
    except Exception as e:
        logger.warning(f"Error fetching stores for RAWG game {rawg_id}: {redact_rawg_key(e)}")

    # HLTB for estimated playtime (and fallback for dev/steam_id)
    avg_time = 0
    clean_name = re.sub(r"[:/]", "", name)
    try:
        hltb_results = await HowLongToBeat().async_search(clean_name)
        if hltb_results and len(hltb_results) > 0:
            best_hltb = max(hltb_results, key=lambda x: x.similarity)
            avg_time = getattr(best_hltb, "gameplay_main", 0) or 0
            if dev == "-" and hasattr(best_hltb, "profile_dev") and best_hltb.profile_dev:
                dev = best_hltb.profile_dev
            if not steam_id and hasattr(best_hltb, "profile_steam") and best_hltb.profile_steam:
                steam_id = str(best_hltb.profile_steam)
    except Exception as e:
        logger.warning(f"HLTB search failed for '{clean_name}': {e}")

    release_date = None
    if released:
        try:
            release_date = datetime.datetime.strptime(released, "%Y-%m-%d").date()
        except Exception:
            release_date = None

    return {
        "rawg_id": rawg_id,
        "name": name,
        "slug": slug,
        "dev": dev,
        "release_date": release_date,
        "steam_id": str(steam_id) if steam_id else "",
        "image_url": image_url,
        "genres": genres,
        "avg_time": int(avg_time) if avg_time else 0,
    }


async def get_game_info(game: str):
    """Retrieve rawg and hltb info for backward compatibility."""
    api_key = config.RAWG_API_KEY
    rawg_content = None
    if api_key:
        try:
            url = "https://api.rawg.io/api/games"
            params = {"key": api_key, "search": game, "page": 1, "page_size": 1}
            game_request = await _http_get(url, params, timeout=10)
            if game_request.ok:
                results = game_request.json().get("results", [])
                if results:
                    rawg_content = results[0]
        except Exception as e:
            logger.warning(f"Error fetching RAWG for {game}: {redact_rawg_key(e)}")

    # HLTB
    clean_game = re.sub(r"[:/]", "", game)
    hltb_content = None
    try:
        results_list = await HowLongToBeat().async_search(clean_game)
        if results_list and len(results_list) > 0:
            best_element = max(results_list, key=lambda element: element.similarity)
            hltb_content = best_element.json_content
    except Exception:
        hltb_content = None

    return {"rawg": rawg_content, "hltb": hltb_content}


async def get_new_game_info(game) -> schemas.NewGame:
    """Resolve and build schemas.NewGame using rawg_id if provided, or by searching RAWG."""
    game_data = game if isinstance(game, dict) else (game.dict() if hasattr(game, "dict") else vars(game))
    game_name = game_data.get("name", "")
    rawg_id = game_data.get("rawg_id")

    details = None
    if rawg_id:
        details = await get_game_details_by_rawg_id(rawg_id)

    if not details and game_name:
        candidates = await search_rawg_games(game_name)
        if candidates:
            top_candidate = candidates[0]
            details = await get_game_details_by_rawg_id(top_candidate.rawg_id)

    if details:
        return schemas.NewGame(
            name=details["name"],
            dev=details["dev"],
            release_date=details["release_date"],
            steam_id=details["steam_id"],
            image_url=details["image_url"],
            genres=details["genres"],
            avg_time=details["avg_time"],
            slug=details["slug"],
            rawg_id=details["rawg_id"],
        )

    # Safe fallback if RAWG finds nothing
    logger.warning(f"No RAWG details found for game: {game_name}. Using fallback.")
    return schemas.NewGame(
        name=game_name,
        dev="-",
        release_date=None,
        steam_id="",
        image_url="",
        genres="",
        avg_time=0,
        slug="",
        rawg_id=None,
    )


def convert_blob_to_image(
    blob_data,
    output_format: str,
):
    try:
        image = Image.open(BytesIO(blob_data))
        converted_image = BytesIO()
        image.save(converted_image, format=output_format)
        converted_data = converted_image.getvalue()

        return converted_data
    except Exception as e:
        print(f"Error converting image: {e}")
        raise


TELEGRAM_RETRIES = 3


async def _telegram_send(bot, chat_id, text: str, image=None) -> bool:
    """Send one message; True if Telegram took it. Never raises: a notification must not
    break the operation that triggered it.

    It goes as Markdown; if Telegram cannot parse it (a name with `_` or `*` in it, an
    unbalanced reply from the model) it is sent again as plain text.
    """
    parse_mode = telegram.constants.ParseMode.MARKDOWN
    for _ in range(TELEGRAM_RETRIES):
        try:
            if image is None:
                await bot.send_message(text=text, chat_id=chat_id, parse_mode=parse_mode)
            else:
                await bot.send_photo(chat_id=chat_id, photo=image, caption=text, parse_mode=parse_mode)
            return True
        except telegram.error.BadRequest as e:
            logger.warning("Telegram rejected the message (" + str(e) + ")")
            if parse_mode is None:
                return False
            parse_mode = None
        except Exception as e:
            logger.error("Error sending telegram message: " + str(e))
    logger.error("Max retries reached. Message not sent.")
    return False


async def send_message(
    msg,
    silent: bool,
    image=None,
    openai=False,
    system_prompt=prompts.DEFAULT_SYSTEM_PROMPT,
    new_game_recommended=None,
):
    if not silent and not settings.get("notifications.enabled"):
        logger.info("Notifications are disabled. Message not sent.")
        return
    telegram_ready = bool(settings.get("telegram.token") and settings.get("telegram.group_id"))
    if not silent and not (telegram_ready or push.is_ready()):
        logger.warning("Neither Telegram nor push are configured. Message not sent.")
        return
    if not silent:
        logger.info("Preparing message...")
        if openai:
            try:
                # logger.debug("Original message: " + msg)
                # logger.debug("System prompt: " + system_prompt)
                if new_game_recommended is not None:
                    system_prompt += "\n" + prompts.NEW_GAME_RECOMENDATION + "\n"
                    system_prompt += (
                        "Juego recomendado: " + str(new_game_recommended["game"]) + "\n"
                    )
                    system_prompt += "Jugado por: " + str(new_game_recommended["user"])
                    # logger.info(system_prompt)
                # the client is synchronous: keep it off the event loop
                completion = await asyncio.to_thread(
                    oai_client.chat_completion, user_prompt=msg, system_prompt=system_prompt
                )
                if completion is not None:
                    logger.info(completion.choices[0].message.content)
                    msg = completion.choices[0].message.content
            except Exception as e:
                logger.info("Error generating completion: " + str(e))
        await push.notify_group(msg)  # never raises: it must not affect Telegram
        if not telegram_ready:
            logger.info("Telegram is not configured. Message sent by push only.")
            return
        try:
            bot = telegram.Bot(settings.get("telegram.token"))
            async with bot:
                logger.info("Sending message to group...")
                if await _telegram_send(bot, settings.get("telegram.group_id"), msg, image):
                    logger.info("Message sent successfully!")
        except Exception as e:  # e.g. Telegram unreachable when the bot session opens
            logger.error("Error sending telegram message: " + str(e))
    else:
        logger.info("Silent mode. Message not sent.")


async def send_message_to_user(user_telegram_id, msg, user_id=None):
    """Private notice: Telegram (if the user has an id) and, given `user_id`, their pushed devices."""
    if not settings.get("notifications.enabled"):
        logger.info("Notifications are disabled. Message to user not sent.")
        return
    if user_id is not None:
        await push.notify_user(user_id, msg, tag="private")
    if user_telegram_id is None or not settings.get("telegram.token"):
        logger.warning("User without Telegram id or bot not configured. Message not sent.")
        return
    try:
        bot = telegram.Bot(settings.get("telegram.token"))
        async with bot:
            logger.info("Sending message to user " + str(user_telegram_id) + "...")
            if await _telegram_send(bot, user_telegram_id, msg):
                logger.info("Message sent successfully!")
    except Exception as e:
        logger.error("Error sending telegram message to user: " + str(e))


async def send_message_to_admins(db: Session, msg):
    if not settings.get("notifications.admin_alerts") or not settings.get("telegram.token"):
        logger.info("Admin alerts are disabled or the bot is not configured. Message not sent.")
        return
    logger.info("Sending message to admins...")
    users_db = users.get_users(db)
    try:
        for user in users_db:
            if user.is_admin and user.telegram_id is not None:
                bot = telegram.Bot(settings.get("telegram.token"))
                async with bot:
                    if await _telegram_send(bot, user.telegram_id, msg):
                        logger.info("Message sent successfully!")
    except Exception as e:
        logger.info(e)


async def send_test_message(sent_by: str) -> None:
    """Diagnostic message to the configured group (ignores the notification switch).
    Raises if Telegram refuses it, so the admin sees why."""
    token, group = settings.get("telegram.token"), settings.get("telegram.group_id")
    if not token or not group:
        raise ValueError("Falta el token del bot o el ID del grupo")
    bot = telegram.Bot(token)
    async with bot:
        await bot.send_message(
            chat_id=group,
            text="✅ Mensaje de prueba de La Viciación (enviado por " + sent_by + ")",
        )


def get_ach_message(
    ach: AchievementsElems, user: str, db: Session = None, game_id: str = None
):
    msg = "🏆" + ach.value["title"] + "🏆\n"
    if game_id is not None:
        game_db = games.get_game_by_id(db, game_id)
        msg = msg + ach.value["message"].format(user, game_db.name)
    else:
        msg = msg + ach.value["message"].format(user)
    return msg


def get_platforms(db: Session):
    try:
        stmt = select(
            models.PlatformTag.id,
            models.PlatformTag.name,
        )
        return db.execute(stmt).fetchall()
    except Exception as e:
        logger.info(e)
        raise e
