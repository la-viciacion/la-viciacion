import asyncio
import datetime
import json
import re

import requests
from starlette.concurrency import run_in_threadpool
import telegram
from howlongtobeatpy import HowLongToBeat
from sqlalchemy import asc, create_engine, desc, func, or_, select, text, update
from sqlalchemy.orm import Session

from ..config import Config
from ..crud import games, time_entries, users
from ..database import models, schemas
from .achievements import AchievementsElems
from . import ai, hltb_sync, push, settings
from .redaction import redact_rawg_key
from ..utils.logger import LogManager

log_manager = LogManager()
logger = log_manager.get_logger()

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


def format_duration(seconds) -> str:
    """3725 -> '01h02m'. Units are spelled out so nobody reads it as minutes and seconds."""
    if seconds is None:
        return "00h00m"
    seconds = int(seconds)  # SQL sums come back as Decimal
    return f"{seconds // 3600:02d}h{seconds % 3600 // 60:02d}m"


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
        candidates.append(
            schemas.RawgGameCandidate(
                rawg_id=item.get("id"),
                name=item.get("name", ""),
                slug=item.get("slug", ""),
                released=item.get("released"),
                image_url=item.get("background_image"),
                genres=[g["name"] for g in item.get("genres", []) if "name" in g],
                platforms=[
                    p.get("platform", {}).get("name")
                    for p in item.get("platforms", [])
                    if p.get("platform", {}).get("name")
                ],
                rating=item.get("rating"),
                metacritic=item.get("metacritic"),
            )
        )
    if db is not None and candidates:
        await run_in_threadpool(mark_existing_games, db, candidates)
    return candidates


def mark_existing_games(db: Session, candidates: list[schemas.RawgGameCandidate]) -> None:
    """Flag the candidates that are already in the games table (same RAWG id, slug or name): one query."""
    rawg_ids = {c.rawg_id for c in candidates if c.rawg_id}
    slugs = {c.slug for c in candidates if c.slug}
    names = {c.name for c in candidates if c.name}
    filters = []
    if rawg_ids:
        filters.append(models.Game.rawg_id.in_(rawg_ids))
    if slugs:
        filters.append(models.Game.slug.in_(slugs))
    if names:
        filters.append(models.Game.name.in_(names))
    if not filters:
        return
    games_db = db.query(models.Game.id, models.Game.rawg_id, models.Game.slug, models.Game.name).filter(or_(*filters)).all()
    for candidate in candidates:
        for game in games_db:
            if (
                (candidate.rawg_id and game.rawg_id == candidate.rawg_id)
                or (candidate.slug and game.slug == candidate.slug)
                or (candidate.name and game.name == candidate.name)
            ):
                candidate.exists_in_db = True
                candidate.db_game_id = game.id
                break


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
    # the tags RAWG has in other languages are the same ones again: only the English ones
    tags = ",".join([t["name"] for t in data.get("tags") or [] if t.get("name") and t.get("language") == "eng"])

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
    try:
        hltb_results = await HowLongToBeat().async_search(hltb_sync.clean_name(name))
        if hltb_results and len(hltb_results) > 0:
            best_hltb = max(hltb_results, key=lambda x: x.similarity)
            # the time only from a clear match (seconds, like the rest of `games.avg_time`), the fallbacks below from the closest
            matched = hltb_sync.best_entry(name, int(released[:4]) if released and released[:4].isdigit() else None, hltb_results)
            avg_time = ((matched.json_content or {}).get("comp_main") or 0) if matched else 0
            if dev == "-" and hasattr(best_hltb, "profile_dev") and best_hltb.profile_dev:
                dev = best_hltb.profile_dev
            if not steam_id and hasattr(best_hltb, "profile_steam") and best_hltb.profile_steam:
                steam_id = str(best_hltb.profile_steam)
    except Exception as e:
        logger.warning(f"HLTB search failed for '{name}': {e}")

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
        "tags": tags,
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
    hltb_content = None
    try:
        results_list = await HowLongToBeat().async_search(hltb_sync.clean_name(game))
        # only a clear match: a doubtful one would replace the stored time with another game's
        best_element = hltb_sync.best_entry(game, None, results_list)
        if best_element is not None:
            hltb_content = best_element.json_content
    except Exception:
        hltb_content = None

    return {"rawg": rawg_content, "hltb": hltb_content}


async def get_new_game_info(game) -> schemas.NewGame:
    """Build schemas.NewGame from the RAWG entry named by `rawg_id`. Without one (or when RAWG has nothing
    for it) the game is the one typed by hand: RAWG is never searched by name here, because its best
    match for a game it does not know is a different game."""
    game_data = game if isinstance(game, dict) else (game.dict() if hasattr(game, "dict") else vars(game))
    game_name = game_data.get("name", "")
    rawg_id = game_data.get("rawg_id")

    details = await get_game_details_by_rawg_id(rawg_id) if rawg_id else None

    if details:
        return schemas.NewGame(
            name=details["name"],
            dev=details["dev"],
            release_date=details["release_date"],
            steam_id=details["steam_id"],
            image_url=details["image_url"],
            genres=details["genres"],
            tags=details["tags"],
            avg_time=details["avg_time"],
            slug=details["slug"],
            rawg_id=details["rawg_id"],
        )

    logger.info(f"Adding '{game_name}' as typed (no RAWG entry)")
    return schemas.NewGame(
        name=game_name,
        dev=(game_data.get("dev") or "").strip() or "-",
        release_date=game_data.get("release_date"),
        steam_id="",
        image_url=(game_data.get("image_url") or "").strip(),
        genres=(game_data.get("genres") or "").strip(),
        tags="",
        avg_time=0,
        slug="",
        rawg_id=None,
    )


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
    ai_use: str | None = None,
    new_game_recommended: dict | None = None,
):
    """`ai_use` (an id of utils/ai_prompts.USES) lets the AI rewrite the notice when it is on for that use.
    `new_game_recommended` ({"game", "user"}) is suggested at the end of the notice: by the AI when
    it rewrites the message, as a plain line when it does not (off, no key, or it failed)."""
    if not silent and not settings.get("notifications.enabled"):
        logger.info("Notifications are disabled. Message not sent.")
        return
    telegram_ready = bool(settings.get("telegram.token") and settings.get("telegram.group_id"))
    if not silent and not (telegram_ready or push.is_ready()):
        logger.warning("Neither Telegram nor push are configured. Message not sent.")
        return
    if not silent:
        logger.info("Preparing message...")
        rewritten = False
        if ai_use and ai.is_ready(ai_use):
            try:
                # the clients block on the network: keep them off the event loop
                text = await asyncio.to_thread(ai.complete, ai.prompt_for(ai_use, new_game_recommended), msg)
                if text:
                    logger.info(text)
                    msg = text
                    rewritten = True
            except Exception as e:
                logger.info("Error generating completion: " + str(e))
        if new_game_recommended and not rewritten:
            msg += (
                f"\n\n🎮 ¿Te apetece probar *{escape_markdown(new_game_recommended['game'])}*? "
                f"Lo tiene {escape_markdown(new_game_recommended['user'])}."
            )
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


async def send_message_to_user(user_telegram_id, msg, user_id=None, telegram_on=True, push_on=True):
    """Private notice: Telegram (if the user has an id) and, given `user_id`, their pushed devices.
    `telegram_on` / `push_on` carry the user's choice of channel for this kind of notice."""
    if not settings.get("notifications.enabled"):
        logger.info("Notifications are disabled. Message to user not sent.")
        return
    if user_id is not None and push_on:
        await push.notify_user(user_id, msg, tag="private")
    if not telegram_on:
        return
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


def announcement_text(title: str, body: str | None = None) -> str:
    """A notice written by an admin as a Telegram message: the title in bold, then the message. Plain
    text in, so whatever they type is escaped and cannot break the Markdown."""
    title, body = (title or "").strip(), (body or "").strip()
    text = f"*{escape_markdown(title)}*"
    return text + "\n\n" + escape_markdown(body) if body else text


async def send_announcement_to_chat(chat_id, title: str, body: str | None = None) -> bool:
    """Send an admin's notice to one Telegram chat (the group or a private chat); True if Telegram took it.
    Only Telegram: nothing goes to the app's devices. Ignores the general notifications switch, like the test message."""
    bot = telegram.Bot(settings.get("telegram.token"))
    async with bot:
        return await _telegram_send(bot, chat_id, announcement_text(title, body))


async def send_test_message_to_user(chat_id) -> bool:
    """Private test message so a player can check their Telegram id; True if Telegram took it.
    Ignores the notification switches: it is an explicit request, like the admin's test message."""
    bot = telegram.Bot(settings.get("telegram.token"))
    async with bot:
        return await _telegram_send(bot, chat_id, "✅ Mensaje de prueba de La Viciación: tu Telegram ID es correcto")


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
