"""Bulk sync of the average time to complete of the games' catalogue against HowLongToBeat (admin-triggered).

The time is the main story of HLTB (`comp_main`, in seconds) and goes to `games.avg_time`: the ranking of debt,
"Justo a tiempo" and the notice of a completed game read it. Rules that keep it safe to run on real data:
  * HLTB is the source of truth, so a time it gives **replaces** the one stored (an admin's hand edit included);
    a game HLTB has no time for keeps the one it has, and nothing is ever blanked out
  * a game is matched on its name only when the match is clear (`pick`); anything doubtful is reported as ambiguous
    with its candidates (and their hours) and left alone, for the admin to type the time by hand in the game's page
"""
import datetime
import re
import threading
import time
import unicodedata
from difflib import SequenceMatcher

from howlongtobeatpy import HowLongToBeat
from sqlalchemy import func

from ..database import models
from ..database.database import SessionLocal
from .logger import LogManager

logger = LogManager().get_logger()

THROTTLE_SECONDS = 1.0           # HLTB has no published quota; be gentle with it
SEARCH_SECONDS = 5               # what one search takes: the library makes about four requests to HLTB's site (measured: 4 to 5 s)
MAX_CONSECUTIVE_ERRORS = 5
MAX_REPORTED = 200               # cap list sizes kept in memory / sent to the panel
MIN_CONFIDENT = 0.9              # similarity a name must reach to be matched without an exact match
MIN_LEAD = 0.05                  # ...and how far ahead of the runner-up it has to be
MIN_CANDIDATE = 0.6              # below this a result is not worth showing as a candidate
MAX_CANDIDATES = 5

_lock = threading.Lock()
_cancel = threading.Event()
_status: dict = {"state": "idle"}


# ── matching (pure) ─────────────────────────────────────────────


ROMAN = {"ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6", "vii": "7", "viii": "8", "ix": "9"}


def _tokens(name: str | None) -> list[str]:
    """The words of a name without accents, case, punctuation or a leading "The"; roman numerals become digits
    (Hades II is Hades 2)."""
    text = unicodedata.normalize("NFKD", name or "")
    text = "".join(c for c in text if not unicodedata.combining(c)).lower().replace("&", "and")
    words = re.findall(r"[a-z0-9]+", text)
    if words[:1] == ["the"]:
        words = words[1:]
    return [ROMAN.get(word, word) for word in words]


def _norm(name: str | None) -> str:
    return "".join(_tokens(name))


def _numbers(name: str | None) -> set[str]:
    return {word for word in _tokens(name) if word.isdigit()}


def _similarity(wanted: str, candidate: dict) -> float:
    want = _norm(wanted)
    return max(
        (SequenceMatcher(None, want, _norm(text)).ratio() for text in (candidate["name"], candidate["alias"]) if text),
        default=0.0,
    )


def _same_numbers(wanted: str, candidate: dict) -> bool:
    """A sequel is not the game: the numbers in the names have to agree for a match that is not exact."""
    return any(_numbers(wanted) == _numbers(text) for text in (candidate["name"], candidate["alias"]) if text)


def candidates(entries) -> list[dict]:
    """HLTB's results as plain dicts (`seconds` is the main story, 0 when HLTB has none), keeping the entry."""
    return [
        {
            "id": entry.game_id,
            "name": entry.game_name,
            "alias": entry.game_alias,
            "type": entry.game_type,
            "year": entry.release_world,
            "seconds": int((entry.json_content or {}).get("comp_main") or 0),
            "entry": entry,
        }
        for entry in entries or []
    ]


def pick(name: str, year: int | None, found: list[dict]) -> tuple[str, list[dict]]:
    """('match', [the one]) when the result is clear, ('ambiguous', [candidates]) when a person should decide,
    ('not_found', []) when nothing looks like the game. DLCs and the like are never the game.

    An exact name (accents, case, punctuation and a leading "The" aside) wins; several of them are told apart by
    the release year. Without one, the closest name wins only if it is very close and clearly ahead of the next."""
    games = [c for c in found if c["type"] in (None, "game")]
    scored = sorted(((_similarity(name, c), c) for c in games), key=lambda pair: -pair[0])
    exact = [c for score, c in scored if score == 1.0]
    if len(exact) > 1 and year:
        exact = [c for c in exact if c["year"] == year] or exact
    if len(exact) == 1:
        return "match", exact
    if exact:
        return "ambiguous", exact[:MAX_CANDIDATES]
    if (
        scored
        and scored[0][0] >= MIN_CONFIDENT
        and _same_numbers(name, scored[0][1])
        and (len(scored) == 1 or scored[0][0] - scored[1][0] >= MIN_LEAD)
    ):
        return "match", [scored[0][1]]
    near = [c for score, c in scored if score >= MIN_CANDIDATE][:MAX_CANDIDATES]
    return ("ambiguous", near) if near else ("not_found", [])


def clean_name(name: str) -> str:
    """What HLTB's search is given: it chokes on colons and slashes."""
    return re.sub(r"[:/]", "", name)


def best_entry(name: str, year: int | None, entries):
    """The HLTB entry that is the game, or None when it is not clear (see `pick`)."""
    outcome, chosen = pick(name, year, candidates(entries))
    return chosen[0]["entry"] if outcome == "match" else None


# ── public API ──────────────────────────────────────────────────


def estimate(db) -> dict:
    total = db.query(func.count(models.Game.id)).scalar()
    return {"total_games": total, "estimated_seconds": int(total * (THROTTLE_SECONDS + SEARCH_SECONDS))}


def status() -> dict:
    with _lock:
        return dict(_status)


def cancel() -> bool:
    with _lock:
        running = _status.get("state") == "running"
    if running:
        _cancel.set()
    return running


def start() -> bool:
    """Launch the background run. False if one is already running."""
    with _lock:
        if _status.get("state") == "running":
            return False
        _cancel.clear()
        _status.clear()
        _status.update(
            state="running",
            started_at=datetime.datetime.now().isoformat(timespec="seconds"),
            finished_at=None,
            total=0,
            processed=0,
            current=None,
            updated=0,
            unchanged=0,
            stop_reason=None,
            ambiguous=[],
            not_found=[],
            no_time=[],
            errors=[],
        )
    threading.Thread(target=_run, daemon=True).start()
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


def _report(candidate: dict) -> dict:
    return {"hltb_id": candidate["id"], "name": candidate["name"], "year": candidate["year"], "hours": round(candidate["seconds"] / 3600, 1)}


def _search(game: models.Game):
    results = HowLongToBeat(0).search(clean_name(game.name), similarity_case_sensitive=False)
    if results is None:                       # the library answers None when the request failed
        raise ConnectionError("HLTB no respondió")
    return results


def _run():
    db = SessionLocal()
    reason = "completed"
    try:
        # Most-played games first, so a cancelled run still covers what matters.
        sessions = dict(
            db.query(models.GameTimer.game_id, func.count(models.GameTimer.id)).group_by(models.GameTimer.game_id).all()
        )
        games = sorted(db.query(models.Game).all(), key=lambda g: (-sessions.get(g.id, 0), g.name.casefold()))
        _set(total=len(games))
        consecutive_errors = 0
        for game in games:
            if _cancel.is_set():
                reason = "cancelled"
                break
            _set(current=game.name)
            time.sleep(THROTTLE_SECONDS)
            try:
                year = game.release_date.year if game.release_date else None
                outcome, chosen = pick(game.name, year, candidates(_search(game)))
                consecutive_errors = 0
                if outcome == "not_found":
                    _push("not_found", {"game_id": game.id, "name": game.name})
                elif outcome == "ambiguous":
                    _push("ambiguous", {"game_id": game.id, "name": game.name, "candidates": [_report(c) for c in chosen]})
                elif not chosen[0]["seconds"]:
                    _push("no_time", {"game_id": game.id, "name": game.name})
                elif chosen[0]["seconds"] == game.avg_time:
                    _bump("unchanged")
                else:
                    game.avg_time = chosen[0]["seconds"]
                    db.commit()
                    _bump("updated")
            except ConnectionError as e:
                db.rollback()
                consecutive_errors += 1
                _push("errors", {"game_id": game.id, "name": game.name, "error": str(e)})
                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    reason = "errors"
                    break
            except Exception as e:                # a failure on one game (the library, the database): keep going
                db.rollback()
                _push("errors", {"game_id": game.id, "name": game.name, "error": str(e)})
            _bump("processed")
    except Exception as e:
        logger.error("HLTB sync crashed: " + str(e))
        reason = f"crash: {e}"
    finally:
        db.close()
        _set(
            state="cancelled" if reason == "cancelled" else "finished",
            stop_reason=reason,
            finished_at=datetime.datetime.now().isoformat(timespec="seconds"),
            current=None,
        )
        logger.info(f"HLTB sync ended ({reason})")
