"""Links the games of the catalogue to IGDB (admin-triggered, in batches): it fills `games.igdb_id` and what IGDB says of
the game (themes, keywords, franchises, collections), which no other source fills.

Rules that keep it safe to run on real data:
  * only those five columns are written, and only while they are empty (a game with an IGDB id and no IGDB data gets the
    data); the name and every other field are never touched
  * a game is linked automatically only on a certain match: the Steam app the game has, or the same name (roman numerals
    and punctuation aside) with a release year that agrees (a year of margin). Anything else is reported as ambiguous with
    candidates for the admin to pick: the best result for a name is never assumed (a remake is not the original)
  * an `igdb_id` already used by another game is never assigned (reported as duplicate)
IGDB has no quota to spend, but it allows about four requests a second, so each game takes a second or so."""
import datetime
import threading
import time

from sqlalchemy import func

from ..clients import igdb
from ..database import models
from ..database.database import SessionLocal
from .logger import LogManager

logger = LogManager().get_logger()

THROTTLE_SECONDS = 0.26          # IGDB allows 4 requests a second
SECONDS_PER_GAME = 1.5           # a Steam lookup and, when it finds nothing, a search
MAX_CONSECUTIVE_ERRORS = 5
MAX_REPORTED = 200               # cap list sizes kept in memory / sent to the panel
YEAR_MARGIN = 1                  # IGDB and RAWG disagree by a year on early access and regional releases
MAX_CANDIDATES = 5

_lock = threading.Lock()
_cancel = threading.Event()
_status: dict = {"state": "idle"}


def _year(item: dict) -> int | None:
    stamp = item.get("first_release_date")
    return datetime.datetime.fromtimestamp(stamp, datetime.timezone.utc).year if stamp else None


def candidate(item: dict) -> dict:
    return {
        "igdb_id": item["id"], "name": item["name"], "year": _year(item),
        "platforms": [p["name"] for p in item.get("platforms") or [] if p.get("name")][:4],
    }


def _games_proper(items: list[dict]) -> list[dict]:
    return [i for i in items if i.get("game_type") in igdb.MAIN_TYPES and i.get("version_parent") is None]


def choose(game: models.Game, steam_hits: list[dict], name_hits: list[dict]) -> tuple[str, object]:
    """What to do with a game: ("linked", item), ("ambiguous", [items]) or ("not_found", None). Pure."""
    if steam_hits:
        proper = _games_proper(steam_hits)
        if len(proper) == 1:
            return "linked", proper[0]
        if len(steam_hits) == 1:
            return "linked", steam_hits[0]
        return "ambiguous", (proper or steam_hits)[:MAX_CANDIDATES]
    exact = [i for i in name_hits if igdb._same_name(i["name"], game.name)]
    year = game.release_date.year if game.release_date else None
    if year is not None:
        agreeing = [i for i in exact if _year(i) is not None and abs(_year(i) - year) <= YEAR_MARGIN]
        if len(agreeing) > 1:
            agreeing = _games_proper(agreeing) or agreeing
        if len(agreeing) == 1:
            return "linked", agreeing[0]
        if agreeing:
            return "ambiguous", agreeing[:MAX_CANDIDATES]
    elif len(exact) == 1:
        return "linked", exact[0]
    if exact:
        return "ambiguous", exact[:MAX_CANDIDATES]  # the name is right and the year is not (or there are several)
    if name_hits:
        return "ambiguous", name_hits[:MAX_CANDIDATES]
    return "not_found", None


def pending_query(db):
    """Games with no IGDB id, and games with one whose IGDB data was never asked (linked by hand or created before it)."""
    return db.query(models.Game).filter(models.Game.igdb_id.is_(None) | models.Game.themes.is_(None))


def _fill(game: models.Game, extras: dict[str, str]) -> None:
    for column, text in extras.items():
        setattr(game, column, text)


def _alphabetical_first(games: list[models.Game], limit: int) -> list[models.Game]:
    return sorted(games, key=lambda g: (g.name.casefold(), g.id))[:limit]


def estimate(db, max_games: int | None = None) -> dict:
    pending = pending_query(db).count()
    games = min(pending, max_games) if max_games else pending
    return {
        "total_games": db.query(func.count(models.Game.id)).scalar(),
        "pending_games": pending,
        "games": games,
        "estimated_seconds": round(games * SECONDS_PER_GAME),
    }


def status() -> dict:
    with _lock:
        return dict(_status)


def cancel() -> bool:
    with _lock:
        running = _status.get("state") == "running"
    if running:
        _cancel.set()
    return running


def start(max_games: int | None = None) -> bool:
    """Launch the background run. False if one is already running.

    `max_games` keeps only the first N games without an IGDB id in alphabetical order, to link in small batches (the
    ones a batch could not decide are still pending and come back in the next); without it every pending game is
    processed, the most played first."""
    if not igdb.configured():
        raise RuntimeError("No hay credenciales de IGDB configuradas")
    with _lock:
        if _status.get("state") == "running":
            return False
        _cancel.clear()
        _status.clear()
        _status.update(
            state="running",
            started_at=datetime.datetime.now().isoformat(timespec="seconds"),
            finished_at=None,
            max_games=max_games,
            total=0,
            processed=0,
            current=None,
            linked=0,
            filled=0,
            stop_reason=None,
            ambiguous=[],
            not_found=[],
            duplicates=[],
            errors=[],
        )
    threading.Thread(target=_run, args=(max_games,), daemon=True).start()
    return True


def _set(**kw):
    with _lock:
        _status.update(kw)


def _push(key: str, item: dict):
    with _lock:
        if len(_status[key]) < MAX_REPORTED:
            _status[key].append(item)


def _bump(key: str):
    with _lock:
        _status[key] += 1


def _ask(function, *args):
    time.sleep(THROTTLE_SECONDS)
    return function(*args)


def _run(max_games: int | None):
    db = SessionLocal()
    reason = "completed"
    try:
        pending = pending_query(db).all()
        if max_games:
            games = _alphabetical_first(pending, max_games)
        else:
            sessions = dict(
                db.query(models.GameTimer.game_id, func.count(models.GameTimer.id)).group_by(models.GameTimer.game_id).all()
            )
            games = sorted(pending, key=lambda g: -sessions.get(g.id, 0))
        _set(total=len(games))
        consecutive_errors = 0

        for game in games:
            if _cancel.is_set():
                reason = "cancelled"
                break
            _set(current=game.name)
            try:
                if game.igdb_id:  # linked already: only its data is missing
                    extras = _ask(igdb.game_extras, game.igdb_id)
                    consecutive_errors = 0
                    if extras is None:
                        _push("not_found", {"game_id": game.id, "name": game.name})
                    else:
                        _fill(game, extras)
                        db.commit()
                        _bump("filled")
                    _bump("processed")
                    continue
                steam_hits = _ask(igdb.find_by_steam, game.steam_id) if (game.steam_id or "").strip() else []
                name_hits = [] if steam_hits else _ask(igdb.search_items, game.name, 10, True)
                verdict, found = choose(game, steam_hits, name_hits)
                consecutive_errors = 0
                if verdict == "not_found":
                    _push("not_found", {"game_id": game.id, "name": game.name})
                elif verdict == "ambiguous":
                    _push("ambiguous", {"game_id": game.id, "name": game.name, "candidates": [candidate(i) for i in found]})
                else:
                    taken = db.query(models.Game).filter(models.Game.igdb_id == found["id"], models.Game.id != game.id).first()
                    if taken:
                        _push("duplicates", {
                            "game_id": game.id, "name": game.name,
                            "igdb_id": found["id"], "other_game_id": taken.id, "other_name": taken.name,
                        })
                    else:
                        game.igdb_id = found["id"]
                        _fill(game, igdb.extras_of(found))
                        db.commit()
                        _bump("linked")
            except igdb.IgdbRefused as e:
                db.rollback()
                reason = f"igdb: {e}"
                break
            except igdb.IgdbError as e:
                db.rollback()
                consecutive_errors += 1
                _push("errors", {"game_id": game.id, "name": game.name, "error": str(e)})
                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    reason = "errors"
                    break
            except Exception as e:  # DB or logic error on one game: keep going
                db.rollback()
                _push("errors", {"game_id": game.id, "name": game.name, "error": str(e)})
            _bump("processed")
    except Exception as e:
        logger.error(f"IGDB link crashed: {e}")
        reason = f"crash: {e}"
    finally:
        db.close()
        _set(
            state="cancelled" if reason == "cancelled" else "finished",
            stop_reason=reason,
            finished_at=datetime.datetime.now().isoformat(timespec="seconds"),
            current=None,
        )
        logger.info(f"IGDB link ended ({reason})")


RELEASE_BATCH = 50  # games per request when the dates are refreshed


def refresh_release_dates(db, games: list[models.Game]) -> tuple[list[models.Game], list[models.Game]]:
    """Pull the release day of games that are not out yet from IGDB (one request per fifty): announced dates slip. Only
    an exact day IGDB gives is written (never blanked, never a placeholder). Returns (the games whose date changed, the
    games IGDB could not be asked about, to be tried elsewhere)."""
    asked = [g for g in games if g.igdb_id]
    if not asked or not igdb.configured():
        return [], list(games)
    changed, unanswered = [], [g for g in games if not g.igdb_id]
    for first in range(0, len(asked), RELEASE_BATCH):
        batch = asked[first:first + RELEASE_BATCH]
        try:
            dates = igdb.release_dates([g.igdb_id for g in batch])
        except igdb.IgdbError as e:
            logger.warning(f"IGDB release dates not refreshed: {e}")
            unanswered.extend(batch)
            continue
        for game in batch:
            day = dates.get(game.igdb_id)
            if day and day != game.release_date:
                game.release_date = day
                changed.append(game)
    db.commit()
    return changed, unanswered


def _blank(value) -> bool:
    return value is None or (isinstance(value, str) and value.strip() in ("", "-"))


APPLIED = ("dev", "release_date", "image_url", "genres", "steam_id")


def _apply_details(db, game: models.Game, details: dict) -> list[str]:
    """Overwrite the game with what IGDB gives (a blank never overwrites; the name is never touched) and return what
    changed. The slug is IGDB's only for a game RAWG does not know: RAWG's slug opens RAWG's page, IGDB's would not."""
    changed = []
    if game.igdb_id != details["igdb_id"]:
        game.igdb_id = details["igdb_id"]
        changed.append("igdb_id")
    for field in APPLIED:
        new = details.get(field)
        if not _blank(new) and getattr(game, field) != new:
            setattr(game, field, new)
            changed.append(field)
    if not game.rawg_id and not _blank(details.get("slug")) and game.slug != details["slug"]:
        game.slug = details["slug"]
        changed.append("slug")
    for column in igdb.EXTRA_COLUMNS:
        new, current = details.get(column), getattr(game, column)
        if (new and new != current) or (current is None and new is not None):
            setattr(game, column, new)
            changed.append(column)
    if details.get("is_dlc") and not game.is_dlc:  # only ever adds the mark, like the RAWG sync
        game.is_dlc = True
        changed.append("is_dlc")
    if details.get("parent_igdb_id") and game.parent_game_id is None:  # linked only when the base is in the catalogue
        base = db.query(models.Game.id).filter(models.Game.igdb_id == details["parent_igdb_id"], models.Game.id != game.id).first()
        if base:
            game.parent_game_id = base.id
            changed.append("parent_game_id")
    return changed


def resync_one(db, game_id: str) -> dict:
    """Refresh one game from IGDB on the admin's explicit request: every field IGDB gives overwrites ours (a blank one
    never does). Without an `igdb_id` the game is looked for first, like the batch does: a doubtful match comes back as
    `ambiguous` with its candidates, to be chosen through `apply_one`. A few IGDB requests."""
    if not igdb.configured():
        raise RuntimeError("No hay credenciales de IGDB configuradas")
    game = db.get(models.Game, game_id)
    if game is None:
        raise LookupError("Juego no encontrado")
    igdb_id = game.igdb_id
    if igdb_id is None:
        steam_hits = igdb.find_by_steam(game.steam_id) if (game.steam_id or "").strip() else []
        verdict, found = choose(game, steam_hits, [] if steam_hits else igdb.search_items(game.name, 10))
        if verdict == "not_found":
            return {"status": "not_found"}
        if verdict == "ambiguous":
            return {"status": "ambiguous", "candidates": [candidate(i) for i in found]}
        igdb_id = found["id"]
        taken = db.query(models.Game).filter(models.Game.igdb_id == igdb_id, models.Game.id != game.id).first()
        if taken:
            return {"status": "duplicate", "other_name": taken.name}
    details = igdb.game_details(igdb_id)
    if details is None:
        return {"status": "not_found"}
    changed = _apply_details(db, game, details)
    db.commit()
    return {"status": "updated" if changed else "unchanged", "changed": changed}


def apply_one(db, game_id: str, igdb_id: int, overwrite: bool = False) -> dict:
    """Resolve one doubtful game by hand: link it to the IGDB entry the admin chose (one IGDB request to check it exists).
    With `overwrite` (the resync of one game) every field IGDB gives replaces ours, as `resync_one` does."""
    game = db.get(models.Game, game_id)
    if game is None:
        raise LookupError("Juego no encontrado")
    taken = db.query(models.Game).filter(models.Game.igdb_id == igdb_id, models.Game.id != game_id).first()
    if taken:
        raise ValueError(f"Ese id de IGDB ya lo tiene «{taken.name}»")
    details = igdb.game_details(igdb_id)
    if details is None:
        raise LookupError("IGDB no tiene ese juego")
    if overwrite:
        changed = _apply_details(db, game, details)
        db.commit()
        return {"linked": True, "changed": changed}
    game.igdb_id = igdb_id
    _fill(game, {column: details[column] for column in igdb.EXTRA_COLUMNS})
    db.commit()
    return {"linked": True, "changed": ["igdb_id"]}
