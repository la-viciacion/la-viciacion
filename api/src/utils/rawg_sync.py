"""Bulk sync of the games catalogue against RAWG.io (admin-triggered, expensive).

Budget notes (RAWG free plan: 20,000 requests/month, non-commercial):
  * game without rawg_id : 1 search + 1 details (+1 stores when steam_id is missing)
  * game with rawg_id    : 1 details (+1 stores when steam_id is missing)
so the whole catalogue is ~3 calls per game at worst. The job stops on its own
when it reaches `max_calls` or as soon as RAWG rejects the key / quota.

Rules that keep it safe to run on real data:
  * only blank fields are filled unless `overwrite` is set; the game name is never touched
  * a game is matched automatically only on an unambiguous name (or slug) match;
    anything else is reported as ambiguous with candidates for the admin to pick
  * a rawg_id already used by another game is never assigned (reported as duplicate)
"""
import datetime
import re
import threading
import time

import requests
from sqlalchemy import func, or_

from ..config import Config
from ..database import models
from ..database.database import SessionLocal
from .logger import LogManager
from .redaction import redact_rawg_key

logger = LogManager().get_logger()
config = Config()

RAWG = "https://api.rawg.io/api"
THROTTLE_SECONDS = 0.5           # ~2 req/s: RAWG answers bursts with transient 502s
MAX_CONSECUTIVE_ERRORS = 5
MAX_REPORTED = 200               # cap list sizes kept in memory / sent to the panel
FATAL_STATUS = {401, 403, 429}   # invalid key / forbidden / quota or rate exceeded


class RawgFatal(Exception):
    """RAWG refused us (key or quota): abort the whole run."""


_lock = threading.Lock()
_cancel = threading.Event()
_status: dict = {"state": "idle"}


# ── helpers ─────────────────────────────────────────────────────


def _norm(s: str | None) -> str:
    s = (s or "").lower()
    s = re.sub(r"^the\s+", "", s)
    return re.sub(r"[^a-z0-9]", "", s)


def _blank(v) -> bool:
    return v is None or (isinstance(v, str) and v.strip() in ("", "-"))


class _Client:
    """Counts every request against the budget and enforces the cap."""

    def __init__(self, max_calls: int):
        self.max_calls = max_calls
        self.calls = 0
        self.key = config.RAWG_API_KEY

    def budget_left(self, needed: int = 1) -> bool:
        return self.calls + needed <= self.max_calls

    def get(self, path: str, **params):
        for attempt in (1, 2):
            time.sleep(THROTTLE_SECONDS if attempt == 1 else 3)
            self.calls += 1
            try:
                resp = requests.get(f"{RAWG}{path}", params={"key": self.key, **params}, timeout=15)
            except requests.RequestException as e:
                raise ConnectionError(redact_rawg_key(str(e)))
            # One retry for transient upstream errors (each try counts as a call).
            if resp.status_code in (502, 503, 504) and attempt == 1 and self.budget_left():
                continue
            break
        if resp.status_code in FATAL_STATUS:
            raise RawgFatal(f"RAWG respondió {resp.status_code} (clave o cuota)")
        if not resp.ok:
            raise ConnectionError(f"RAWG respondió {resp.status_code}")
        return resp.json()


def _search(client: _Client, name: str) -> list[dict]:
    data = client.get("/games", search=name, search_precise="true", page_size=5)
    return data.get("results", [])


def _candidate(item: dict) -> dict:
    return {
        "rawg_id": item.get("id"),
        "name": item.get("name"),
        "released": item.get("released"),
        "platforms": [
            p["platform"]["name"] for p in item.get("platforms") or [] if p.get("platform")
        ][:4],
    }


def _pick_confident(game: models.Game, results: list[dict]) -> dict | None:
    """The single result we trust, or None when a human should decide."""
    want = _norm(game.name)
    exact = [r for r in results if _norm(r.get("name")) == want]
    if exact:
        return exact[0]                       # RAWG orders by relevance/popularity
    if game.slug:
        by_slug = [r for r in results if r.get("slug") == game.slug]
        if by_slug:
            return by_slug[0]
    return None


def _parse_date(value: str | None) -> datetime.date | None:
    try:
        return datetime.datetime.strptime(value, "%Y-%m-%d").date() if value else None
    except ValueError:
        return None


def _details(client: _Client, rawg_id: int, need_steam: bool) -> dict:
    d = client.get(f"/games/{rawg_id}")
    devs = [x["name"] for x in d.get("developers") or [] if x.get("name")]
    if not devs:
        devs = [x["name"] for x in d.get("publishers") or [] if x.get("name")]
    steam = ""
    if need_steam and client.budget_left():
        try:
            for s in client.get(f"/games/{rawg_id}/stores").get("results", []):
                m = re.search(r"steampowered\.com/app/(\d+)", s.get("url", ""))
                if m:
                    steam = m.group(1)
                    break
        except ConnectionError:
            pass                              # steam id is best-effort
    released = _parse_date(d.get("released"))
    return {
        "rawg_id": rawg_id,
        "slug": d.get("slug"),
        "dev": ", ".join(devs),
        "release_date": released,
        "image_url": d.get("background_image"),
        "genres": ",".join(g["name"] for g in d.get("genres") or [] if g.get("name")),
        "steam_id": steam,
    }


FIELDS = ("slug", "dev", "release_date", "image_url", "genres", "steam_id")


def _apply(game: models.Game, det: dict, overwrite: bool) -> list[str]:
    changed = []
    if game.rawg_id != det["rawg_id"]:
        game.rawg_id = det["rawg_id"]
        changed.append("rawg_id")
    for f in FIELDS:
        new = det.get(f)
        if _blank(new):
            continue                          # never blank something out
        if overwrite or _blank(getattr(game, f)):
            if getattr(game, f) != new:
                setattr(game, f, new)
                changed.append(f)
    return changed


def _needs_steam(game: models.Game, overwrite: bool) -> bool:
    return overwrite or _blank(game.steam_id)


def _pending_query(db, overwrite: bool):
    """Games worth a call: no rawg_id, or a rawg_id with blank fields (or all, on overwrite)."""
    q = db.query(models.Game)
    if overwrite:
        return q
    blanks = [
        models.Game.rawg_id.is_(None),
        *[getattr(models.Game, f).is_(None) | (getattr(models.Game, f) == "") for f in FIELDS],
        models.Game.dev == "-",
    ]
    return q.filter(or_(*blanks))


# ── public API ──────────────────────────────────────────────────


def estimate(db, overwrite: bool = False) -> dict:
    games = _pending_query(db, overwrite).all()
    no_id = [g for g in games if g.rawg_id is None]
    with_id = [g for g in games if g.rawg_id is not None]
    steam = lambda gs: sum(1 for g in gs if _needs_steam(g, overwrite))  # noqa: E731
    return {
        "total_games": db.query(func.count(models.Game.id)).scalar(),
        "pending_games": len(games),
        "without_rawg_id": len(no_id),
        "with_rawg_id": len(with_id),
        # worst case: every search finds a match and every steam lookup runs
        "estimated_calls": len(no_id) * 2 + len(with_id) + steam(games),
        "monthly_quota": 20000,
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


def start(max_calls: int, overwrite: bool) -> bool:
    """Launch the background run. False if one is already running."""
    if not config.RAWG_API_KEY:
        raise RuntimeError("No hay clave de RAWG configurada")
    with _lock:
        if _status.get("state") == "running":
            return False
        _cancel.clear()
        _status.clear()
        _status.update(
            state="running",
            started_at=datetime.datetime.now().isoformat(timespec="seconds"),
            finished_at=None,
            overwrite=overwrite,
            max_calls=max_calls,
            calls=0,
            total=0,
            processed=0,
            current=None,
            updated=0,
            unchanged=0,
            stop_reason=None,
            ambiguous=[],
            not_found=[],
            duplicates=[],
            errors=[],
        )
    threading.Thread(target=_run, args=(max_calls, overwrite), daemon=True).start()
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


def _run(max_calls: int, overwrite: bool):
    db = SessionLocal()
    client = _Client(max_calls)
    reason = "completed"
    try:
        # Most-played games first, so a small call cap still covers what matters.
        sessions = dict(
            db.query(models.GameTimer.game_id, func.count(models.GameTimer.id))
            .group_by(models.GameTimer.game_id)
            .all()
        )
        games = sorted(_pending_query(db, overwrite).all(), key=lambda g: -sessions.get(g.id, 0))
        _set(total=len(games))
        consecutive_errors = 0

        for game in games:
            if _cancel.is_set():
                reason = "cancelled"
                break
            needed = 1 if game.rawg_id is not None else 2
            if not client.budget_left(needed):
                reason = "max_calls"
                break
            _set(current=game.name, calls=client.calls)
            try:
                rawg_id = game.rawg_id
                if rawg_id is None:
                    results = _search(client, game.name)
                    if not results:
                        _push("not_found", {"game_id": game.id, "name": game.name})
                        _bump("processed")
                        consecutive_errors = 0
                        continue
                    pick = _pick_confident(game, results)
                    if pick is None:
                        _push("ambiguous", {
                            "game_id": game.id,
                            "name": game.name,
                            "candidates": [_candidate(r) for r in results],
                        })
                        _bump("processed")
                        consecutive_errors = 0
                        continue
                    rawg_id = pick["id"]
                    taken = db.query(models.Game).filter(
                        models.Game.rawg_id == rawg_id, models.Game.id != game.id
                    ).first()
                    if taken:
                        _push("duplicates", {
                            "game_id": game.id, "name": game.name,
                            "rawg_id": rawg_id, "other_game_id": taken.id, "other_name": taken.name,
                        })
                        _bump("processed")
                        consecutive_errors = 0
                        continue
                det = _details(client, rawg_id, _needs_steam(game, overwrite))
                changed = _apply(game, det, overwrite)
                db.commit()
                _bump("updated" if changed else "unchanged")
                consecutive_errors = 0
            except RawgFatal:
                raise
            except ConnectionError as e:
                db.rollback()
                consecutive_errors += 1
                _push("errors", {"game_id": game.id, "name": game.name, "error": redact_rawg_key(str(e))})
                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    reason = "errors"
                    break
            except Exception as e:                # DB or logic error on one game: keep going
                db.rollback()
                _push("errors", {"game_id": game.id, "name": game.name, "error": redact_rawg_key(str(e))})
            _bump("processed")
    except RawgFatal as e:
        reason = f"rawg: {e}"
    except Exception as e:
        logger.error("RAWG sync crashed: " + redact_rawg_key(str(e)))
        reason = f"crash: {redact_rawg_key(str(e))}"
    finally:
        db.close()
        _set(
            state="cancelled" if reason == "cancelled" else "finished",
            stop_reason=reason,
            finished_at=datetime.datetime.now().isoformat(timespec="seconds"),
            calls=client.calls,
            current=None,
        )
        logger.info(f"RAWG sync ended ({reason}); {client.calls} RAWG calls")


def refresh_release_dates(db, games: list[models.Game], max_calls: int = 50) -> list[models.Game]:
    """Pull the release date of games that are not out yet from RAWG (one call each): announced dates slip.
    Only a date RAWG actually gives is written (never blanked out). Returns the games whose date changed."""
    if not config.RAWG_API_KEY or not games:
        return []
    client = _Client(max_calls)
    changed = []
    try:
        for game in games:
            if not client.budget_left():
                break
            try:
                released = _parse_date(client.get(f"/games/{game.rawg_id}").get("released"))
            except ConnectionError as e:
                logger.warning(f"RAWG release date of {game.name} not refreshed: {redact_rawg_key(str(e))}")
                continue
            if released and released != game.release_date:
                game.release_date = released
                changed.append(game)
    except RawgFatal as e:
        logger.warning(f"RAWG release dates not refreshed: {e}")
    db.commit()
    return changed


def apply_one(db, game_id: str, rawg_id: int, overwrite: bool = False) -> dict:
    """Resolve one ambiguous game by hand: fetch that RAWG entry and apply it."""
    game = db.get(models.Game, game_id)
    if game is None:
        raise LookupError("Juego no encontrado")
    taken = db.query(models.Game).filter(
        models.Game.rawg_id == rawg_id, models.Game.id != game_id
    ).first()
    if taken:
        raise ValueError(f"Ese id de RAWG ya lo tiene «{taken.name}»")
    client = _Client(max_calls=3)
    det = _details(client, rawg_id, _needs_steam(game, overwrite))
    changed = _apply(game, det, overwrite)
    db.commit()
    return {"changed": changed, "calls": client.calls}
