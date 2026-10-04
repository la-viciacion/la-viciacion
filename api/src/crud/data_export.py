"""A player's data as a file, and back: "Exportar mis datos" / "Importar datos" of the profile.

The export is a snapshot of what belongs to one player: finished sessions, library entries, ratings, wishlist and
the achievements they hold (these last ones for reading only), with the games and platforms those rows mention so
the file means something on its own. Nothing derived is in it (totals, rankings, streaks, the time of an entry).

The import is a **merge that never overwrites**: what the account already has wins, so importing the same file
twice changes nothing. It follows the rules of the app instead of bending them:

- sessions: end after start, not in the future, no overlap with anything else the player has played; a session
  that already exists (same game and start) is counted, not added; `duration_seconds` is recomputed, never trusted
- seasons: a player only imports the running season (closed ones are frozen, as for manual sessions); an admin
  imports any
- games and platforms are shared catalogues: a row whose game or platform the database does not have is skipped
  (a game is looked up by id, then by name); only an admin's import creates the missing ones
- completions: once per game and season, as always; ratings and the wishlist only for games the player has
- achievements are not imported: they are earned, and the follow-up check (silent) awards what the sessions deserve

`import_data` with `dry_run` runs everything and rolls back, which is how the profile shows what would happen.
"""
import bisect
import datetime
import re

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import models
from ..utils import messages as msg
from ..utils import seasons

FORMAT = "laviciacion-export"
VERSION = 1

FUTURE_SLACK = datetime.timedelta(minutes=1)
PROBLEMS_SHOWN = 25
PLATFORM_ID = re.compile(r"^[a-z0-9-]{1,60}$")
NEVER = datetime.datetime.max  # the end of a running timer


# ── Export ──────────────────────────────────────────────────────


def _day(value: datetime.date | datetime.datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def export_user(db: Session, user: models.User, now: datetime.datetime) -> dict:
    """Everything that belongs to `user`, as plain data ready for JSON."""
    sessions = (
        db.query(models.GameTimer)
        .filter(models.GameTimer.user_id == user.id, models.GameTimer.end_time.isnot(None))
        .order_by(models.GameTimer.start_time, models.GameTimer.id)
        .all()
    )
    library = db.query(models.UserGame).filter_by(user_id=user.id).order_by(models.UserGame.started_date, models.UserGame.id).all()
    scores = db.query(models.GameScore).filter_by(user_id=user.id).order_by(models.GameScore.id).all()
    wishes = db.query(models.UserWishlist).filter_by(user_id=user.id).order_by(models.UserWishlist.id).all()
    awards = (
        db.query(models.UserAchievement, models.Achievement.key)
        .join(models.Achievement, models.Achievement.id == models.UserAchievement.achievement_id)
        .filter(models.UserAchievement.user_id == user.id)
        .order_by(models.UserAchievement.date, models.UserAchievement.id)
        .all()
    )

    game_ids = {r.game_id for r in (*sessions, *library, *scores, *wishes)} | {a.game_id for a, _ in awards if a.game_id}
    platform_ids = {r.platform for r in (*sessions, *library) if r.platform}
    games = db.query(models.Game).filter(models.Game.id.in_(game_ids)).order_by(models.Game.name).all() if game_ids else []
    platforms = db.query(models.PlatformTag).filter(models.PlatformTag.id.in_(platform_ids)).order_by(models.PlatformTag.name).all() if platform_ids else []

    return {
        "format": FORMAT,
        "version": VERSION,
        "exported_at": now.replace(microsecond=0).isoformat(),
        "user": {"username": user.username, "name": user.name},
        "games": [
            {
                "id": g.id, "name": g.name, "dev": g.dev, "release_date": _day(g.release_date), "genres": g.genres,
                "avg_time": g.avg_time, "image_url": g.image_url, "slug": g.slug, "steam_id": g.steam_id, "rawg_id": g.rawg_id,
            }
            for g in games
        ],
        "platforms": [{"id": p.id, "name": p.name} for p in platforms],
        "library": [
            {
                "game_id": e.game_id, "platform": e.platform, "started_date": _day(e.started_date),
                "completed": bool(e.completed), "completed_date": _day(e.completed_date), "completion_time": e.completion_time,
                "abandoned_at": _day(e.abandoned_at),
            }
            for e in library
        ],
        "sessions": [
            {
                "game_id": s.game_id, "platform": s.platform, "start_time": _day(s.start_time), "end_time": _day(s.end_time),
                "duration_seconds": s.duration_seconds, "notes": s.notes,
            }
            for s in sessions
        ],
        "scores": [{"game_id": s.game_id, "score": s.score} for s in scores],
        "wishlist": [{"game_id": w.game_id, "added_at": _day(w.added_at)} for w in wishes],
        "achievements": [{"key": key, "date": _day(a.date), "game_id": a.game_id} for a, key in awards],
    }


def is_supported(data) -> bool:
    """Whether a parsed file is an export of this app, in a version this code reads."""
    return data.format == FORMAT and data.version == VERSION


# ── Import ──────────────────────────────────────────────────────


class Report:
    """What an import did, counted per kind of row, with the first problems worded for the person."""

    KINDS = ("sessions", "library", "scores", "wishlist")

    def __init__(self, dry_run: bool):
        self.dry_run = dry_run
        self.counts = {kind: {"imported": 0, "existing": 0, "skipped": 0} for kind in self.KINDS}
        self.created = {"games": 0, "platforms": 0}
        self.problems: list[dict] = []
        self.problems_total = 0

    def imported(self, kind: str):
        self.counts[kind]["imported"] += 1

    def existing(self, kind: str):
        self.counts[kind]["existing"] += 1

    def skipped(self, kind: str, label: str, reason: str):
        self.counts[kind]["skipped"] += 1
        self.problems_total += 1
        if len(self.problems) < PROBLEMS_SHOWN:
            self.problems.append({"kind": kind, "label": label, "reason": reason})

    def as_dict(self) -> dict:
        return {"dry_run": self.dry_run, **self.counts, "created": self.created, "problems": self.problems, "problems_total": self.problems_total}


def _when(value) -> str:
    return value.strftime("%Y-%m-%d %H:%M") if isinstance(value, datetime.datetime) else str(value)


def _resolve_platforms(db: Session, data, creator_is_admin: bool, report: Report) -> dict:
    """Platform id of the file -> id in this database (None when it has no counterpart and cannot be created)."""
    wanted = {p.id: p.name for p in data.platforms}
    for row in (*data.library, *data.sessions):
        if row.platform:
            wanted.setdefault(row.platform, None)
    if not wanted:
        return {}
    known = {p.id: p for p in db.query(models.PlatformTag).all()}
    by_name = {(p.name or "").strip().lower(): p.id for p in known.values()}
    resolved = {}
    for platform_id, name in wanted.items():
        name = (name or "").strip()
        if platform_id in known:
            resolved[platform_id] = platform_id
        elif name and name.lower() in by_name:
            resolved[platform_id] = by_name[name.lower()]
        elif creator_is_admin and name and len(name) <= 100 and PLATFORM_ID.match(platform_id):
            db.add(models.PlatformTag(id=platform_id, name=name))
            known[platform_id] = models.PlatformTag(id=platform_id, name=name)
            by_name[name.lower()] = platform_id
            resolved[platform_id] = platform_id
            report.created["platforms"] += 1
        else:
            resolved[platform_id] = None
    return resolved


def _resolve_games(db: Session, data, creator_is_admin: bool, report: Report) -> dict:
    """Game id of the file -> id in this database: the same id, else the game with the same name."""
    mentioned = {g.id: g for g in data.games}
    for collection in (data.library, data.sessions, data.scores, data.wishlist):
        for row in collection:
            mentioned.setdefault(row.game_id, None)
    ids = list(mentioned)
    present = {g.id for g in db.query(models.Game.id).filter(models.Game.id.in_(ids))} if ids else set()
    names = [g.name.lower() for g in mentioned.values() if g is not None and g.id not in present]
    by_name = {n.lower(): i for i, n in db.query(models.Game.id, models.Game.name).filter(func.lower(models.Game.name).in_(names))} if names else {}
    taken_names = set(by_name)
    resolved = {}
    for game_id, game in mentioned.items():
        if game_id in present:
            resolved[game_id] = game_id
        elif game is not None and game.name.lower() in by_name:
            resolved[game_id] = by_name[game.name.lower()]
        elif creator_is_admin and game is not None and game.name.lower() not in taken_names:
            db.add(models.Game(
                id=game_id, name=game.name, dev=game.dev, release_date=game.release_date, genres=game.genres, avg_time=game.avg_time,
                image_url=game.image_url, slug=game.slug, steam_id=game.steam_id, rawg_id=game.rawg_id,
            ))
            taken_names.add(game.name.lower())
            resolved[game_id] = game_id
            report.created["games"] += 1
        else:
            resolved[game_id] = None
    return resolved


def import_data(db: Session, actor: models.User, user: models.User, data, dry_run: bool = False) -> dict:
    """Merge `data` (a validated `schemas.ExportFile`) into `user`'s account. Commits unless `dry_run`, which
    rolls everything back and only reports. The caller has already checked `actor` may act for `user`."""
    report = Report(dry_run)
    is_admin = bool(actor.is_admin)
    current = seasons.current()
    now = datetime.datetime.now()
    names = {g.id: g.name for g in data.games}

    platform_map = _resolve_platforms(db, data, is_admin, report)
    game_map = _resolve_games(db, data, is_admin, report)

    def game_label(game_id):
        return names.get(game_id) or game_id

    def season_refused(day) -> bool:
        return not is_admin and seasons.of(day) != current

    # what the account already has
    entries = {
        (e.game_id, e.platform, e.season): e for e in db.query(models.UserGame).filter_by(user_id=user.id)
    }
    completed = {(g, s) for (g, _, s), e in entries.items() if e.completed}
    in_library = {g for g, _, _ in entries}

    # ── library
    for row in sorted(data.library, key=lambda r: r.started_date):
        label = f"{game_label(row.game_id)} · {row.started_date}"
        game = game_map.get(row.game_id)
        platform = platform_map.get(row.platform) if row.platform else None
        if game is None:
            report.skipped("library", label, msg.IMPORT_UNKNOWN_GAME)
        elif row.platform and platform is None:
            report.skipped("library", label, msg.IMPORT_UNKNOWN_PLATFORM)
        elif season_refused(row.started_date):
            report.skipped("library", label, msg.IMPORT_CLOSED_SEASON)
        elif (game, platform, seasons.of(row.started_date)) in entries:
            report.existing("library")
        else:
            season = seasons.of(row.started_date)
            done = bool(row.completed) and (game, season) not in completed
            done_date = row.completed_date if done and row.completed_date and row.completed_date.year == season else None
            entry = models.UserGame(
                user_id=user.id, game_id=game, platform=platform, started_date=row.started_date,
                completed=int(done), completed_date=(done_date or row.started_date) if done else None,
                completion_time=row.completion_time if done else None,
                abandoned_at=None if done else row.abandoned_at,
            )
            db.add(entry)
            entries[(game, platform, season)] = entry
            in_library.add(game)
            if done:
                completed.add((game, season))
            report.imported("library")

    # ── sessions: in time order, against what the player already played
    existing = db.query(models.GameTimer.game_id, models.GameTimer.start_time, models.GameTimer.end_time).filter_by(user_id=user.id).all()
    keys = {(g, s) for g, s, _ in existing}
    busy = sorted((s, e or NEVER) for _, s, e in existing)
    starts = [s for s, _ in busy]

    for row in sorted(data.sessions, key=lambda r: r.start_time):
        label = f"{game_label(row.game_id)} · {_when(row.start_time)}"
        game = game_map.get(row.game_id)
        platform = platform_map.get(row.platform) if row.platform else None
        if game is None:
            report.skipped("sessions", label, msg.IMPORT_UNKNOWN_GAME)
        elif row.platform and platform is None:
            report.skipped("sessions", label, msg.IMPORT_UNKNOWN_PLATFORM)
        elif row.end_time <= row.start_time:
            report.skipped("sessions", label, msg.IMPORT_BAD_TIMES)
        elif row.end_time > now + FUTURE_SLACK:
            report.skipped("sessions", label, msg.IMPORT_IN_THE_FUTURE)
        elif season_refused(row.start_time) or season_refused(row.end_time):
            report.skipped("sessions", label, msg.IMPORT_CLOSED_SEASON)
        elif (game, row.start_time) in keys:
            report.existing("sessions")
        else:
            # the player's sessions do not overlap one another, so ends are in the order of the starts and only the
            # last one that starts before this one ends can reach into it
            last = bisect.bisect_left(starts, row.end_time)
            if last and busy[last - 1][1] > row.start_time:
                report.skipped("sessions", label, msg.IMPORT_OVERLAP)
                continue
            at = bisect.bisect_left(starts, row.start_time)
            db.add(models.GameTimer(
                user_id=user.id, game_id=game, platform=platform, start_time=row.start_time, end_time=row.end_time,
                duration_seconds=int((row.end_time - row.start_time).total_seconds()), is_active=False, notes=row.notes,
            ))
            keys.add((game, row.start_time))
            busy.insert(at, (row.start_time, row.end_time))
            starts.insert(at, row.start_time)
            season = seasons.of(row.start_time)
            if (game, platform, season) not in entries:
                entries[(game, platform, season)] = models.UserGame(
                    user_id=user.id, game_id=game, platform=platform, completed=0, started_date=row.start_time.date()
                )
                db.add(entries[(game, platform, season)])
                in_library.add(game)
            report.imported("sessions")

    # ── ratings and wishlist: only for games the player has / does not have
    rated = {s.game_id for s in db.query(models.GameScore.game_id).filter_by(user_id=user.id)}
    for row in data.scores:
        game = game_map.get(row.game_id)
        if game is None:
            report.skipped("scores", game_label(row.game_id), msg.IMPORT_UNKNOWN_GAME)
        elif game in rated:
            report.existing("scores")
        elif game not in in_library:
            report.skipped("scores", game_label(row.game_id), msg.IMPORT_NOT_IN_LIBRARY)
        else:
            db.add(models.GameScore(user_id=user.id, game_id=game, score=row.score))
            rated.add(game)
            report.imported("scores")

    wished = {w.game_id for w in db.query(models.UserWishlist.game_id).filter_by(user_id=user.id)}
    for row in data.wishlist:
        game = game_map.get(row.game_id)
        if game is None:
            report.skipped("wishlist", game_label(row.game_id), msg.IMPORT_UNKNOWN_GAME)
        elif game in wished:
            report.existing("wishlist")
        elif game in in_library:
            report.skipped("wishlist", game_label(row.game_id), msg.IMPORT_ALREADY_PLAYED)
        else:
            db.add(models.UserWishlist(user_id=user.id, game_id=game))
            wished.add(game)
            report.imported("wishlist")

    if dry_run:
        db.rollback()
    else:
        db.commit()
    return report.as_dict()
