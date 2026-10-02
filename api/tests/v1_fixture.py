"""A synthetic v1 database: the v1 schema (tests/v1_schema.py) filled with invented data.

Nothing here comes from a real backup: names, e-mails and ids are made up and the sessions are
generated from a fixed seed, so the fixture is the same on every run. What it does reproduce are
the awkward cases the migrations were written for (see docs/migrations.md): sessions of a Clockify
project that never reached `games`, a double-start, abandoned timers, e-mails with spaces and
capitals, a blank e-mail, per-year library tables with rows that must and must not come back.

`load()` leaves the database exactly as an imported v1 dump would: no `alembic_version`, so
`alembic upgrade head` walks 000 to the head. The numbers the tests compare against are computed
here from the rows themselves, never read back from the migrated database.
"""
import datetime
import hashlib
import random
from dataclasses import dataclass, field

from sqlalchemy import text

from tests.v1_schema import V1_TABLES

FAKE_PASSWORD_HASH = "$2b$12$" + "a" * 53

PLATFORMS = [("pc", "PC"), ("switch", "Switch"), ("ps5", "PlayStation 5")]

# (id, name, username, email as typed, telegram_id)
USERS = [
    (1, "Ana", "ana", "  Ana@Example.COM ", 1001),   # admin; e-mail needs trimming and lower-casing
    (2, "Bea", "bea", "bea@example.com", 1002),
    (3, "Cai", "cai", "", None),                     # blank e-mail must become NULL
    (4, "Dani", "dani", "dani@example.com", None),
]

GAMES = {name: hashlib.md5(name.encode()).hexdigest()[:24] for name in (
    "Hollow Pine", "Stardew Fields", "Celeste Peak", "Portal Gun Co-op", "Rocket Arena", "Dungeon Crawl 3",
)}
HOLLOW, STARDEW, CELESTE, PORTAL, ROCKET, DUNGEON = GAMES.values()

# a Clockify project that was never synced into `games`
ORPHAN_PROJECT = "ffffffffffffffffffffff01"
GONE_GAME = "eeeeeeeeeeeeeeeeeeeeee01"  # a game that no longer exists
GONE_USER = 99                          # a user that no longer exists


def d(value: str) -> datetime.date:
    return datetime.date.fromisoformat(value)


# Library entries per season: (user, game, platform, started, completed, completed_date, score, played_time, completion_time)
LIBRARY_ACTIVE = [  # users_games: seasons 2025 and 2026, season stored as the year of started_date
    (1, HOLLOW, "pc", "2025-02-03", 1, "2025-03-01", 9.0, 7200, 36000),
    (1, HOLLOW, "pc", "2026-01-12", 0, None, None, 1800, None),    # the same game again, next season
    (2, STARDEW, "switch", "2025-05-20", 0, None, None, 5400, None),
    (3, CELESTE, "pc", "2025-07-01", 1, "2025-07-15", 8.5, 9000, 21600),
    (4, ROCKET, "ps5", "2026-02-02", 0, None, None, 3600, None),
]
LIBRARY_2024 = [  # users_games_2024: season 2024 (restored by 011)
    (1, STARDEW, "switch", "2024-03-10", 1, "2024-04-01", 7.0, 4000, 18000),
    (2, CELESTE, "pc", "2024-06-05", 1, None, 6.0, 3000, 12000),         # completed with no date: copied verbatim
    (3, ROCKET, "ps5", "2024-09-09", 0, None, None, 600, None),
    (4, PORTAL, "pc", "2025-01-01", 0, None, None, 100, None),           # dated 2025: not a 2024 entry, skipped
    (GONE_USER, HOLLOW, "pc", "2024-02-02", 0, None, None, 100, None),   # user no longer exists: skipped
    (1, GONE_GAME, "pc", "2024-02-03", 0, None, None, 100, None),        # game no longer exists: skipped
]
LIBRARY_HISTORICAL = [  # users_games_historical: 2023, plus an older snapshot of 2024 that must stay out
    (1, DUNGEON, "pc", "2023-04-04", 1, "2023-05-01", 8.0, 8000, 30000),
    (2, HOLLOW, "pc", "2023-08-08", 0, None, None, 500, None),
    (2, ROCKET, "ps5", "2024-01-15", 0, None, None, 200, None),          # 2024 snapshot, superseded by users_games_2024
]
RESTORED_2023 = 2
RESTORED_2024 = 3

ACHIEVEMENTS = [(1, "first_hour", "First hour", "One hour played"), (2, "marathon", "Marathon", "Ten hours in a day"),
                (3, "finisher", "Finisher", "Completed a game")]
USERS_ACHIEVEMENTS = [  # (user, achievement, date, game, season as v1 stored it)
    (1, 1, "2025-03-01", HOLLOW, 2025),
    (2, 1, "2025-04-02", STARDEW, 2025),
    (1, 2, "2026-02-01", HOLLOW, 2026),
    (1, 3, "2025-03-02", HOLLOW, 2025),
]


@dataclass
class Session:
    id: str
    user_id: int | None
    project: str | None
    start: datetime.datetime | None
    end: datetime.datetime | None
    duration: int | None


@dataclass
class Expected:
    """What the migrated database must contain, derived from the rows inserted below."""
    timers: int = 0
    timer_seconds: int = 0
    timers_by_season: dict = field(default_factory=dict)
    archived_time_entries: int = 0
    double_start_start: datetime.datetime | None = None
    double_start_kept_seconds: int = 0
    orphan_sessions: int = 0


def _hex(seed: str) -> str:
    return hashlib.md5(seed.encode()).hexdigest()[:24]


def build_sessions() -> list[Session]:
    """Sessions for every library entry above, a few per (user, game, season), from a fixed seed."""
    rng = random.Random(20260930)
    sessions: list[Session] = []
    seen: set[tuple] = set()

    def add(user, game, year_start: datetime.date, count: int):
        for n in range(count):
            day = year_start + datetime.timedelta(days=rng.randint(0, 120))
            start = datetime.datetime.combine(day, datetime.time(rng.randint(8, 22), rng.choice([0, 15, 30, 45])))
            if (user, game, start) in seen:
                continue
            seen.add((user, game, start))
            duration = rng.randint(20, 240) * 60
            sessions.append(Session(_hex(f"{user}{game}{start}"), user, game, start,
                                    start + datetime.timedelta(seconds=duration), duration))

    for table in (LIBRARY_ACTIVE, LIBRARY_2024, LIBRARY_HISTORICAL):
        for user, game, _, started, *_ in table:
            if user == GONE_USER or game == GONE_GAME:
                continue
            add(user, game, d(started), rng.randint(3, 8))
    return sessions


def build_edge_sessions() -> list[Session]:
    start = datetime.datetime(2025, 3, 3, 21, 0)
    return [
        # abandoned timer with nothing recoverable: 003 deletes it
        Session("00000000000000000000e001", None, None, None, None, None),
        # double start in Clockify: same user, project and start; 004 keeps the longest one
        Session("00000000000000000000e002", 1, HOLLOW, start, start + datetime.timedelta(seconds=3600), 3600),
        Session("00000000000000000000e003", 1, HOLLOW, start, start + datetime.timedelta(seconds=3000), 3000),
        # sessions of a project that is not in `games`: 003 invents a placeholder game for it
        Session("00000000000000000000e004", 2, ORPHAN_PROJECT, datetime.datetime(2024, 11, 3, 18, 0),
                datetime.datetime(2024, 11, 3, 19, 0), 3600),
        Session("00000000000000000000e005", 3, ORPHAN_PROJECT, datetime.datetime(2025, 12, 31, 23, 30),
                datetime.datetime(2026, 1, 1, 0, 30), 3600),   # crosses the season boundary: it is 2025's
        # a timer that was started and never stopped: kept as a finished session with no times
        Session("00000000000000000000e006", 4, ROCKET, datetime.datetime(2026, 2, 3, 20, 0), None, None),
    ]


def expected_totals(generated: list[Session], edges: list[Session]) -> Expected:
    kept = list(generated) + [s for s in edges if s.start is not None and s.id != "00000000000000000000e003"]
    out = Expected()
    out.timers = len(kept)
    out.timer_seconds = sum(s.duration or 0 for s in kept)
    for s in kept:
        out.timers_by_season[s.start.year] = out.timers_by_season.get(s.start.year, 0) + 1
    out.archived_time_entries = len(generated) + len(edges) - 1  # 003 removes the empty row, 004 keeps the double start's rows
    out.double_start_start = datetime.datetime(2025, 3, 3, 21, 0)
    out.double_start_kept_seconds = 3600
    out.orphan_sessions = 2
    return out


def _insert(conn, table: str, rows: list[dict]) -> None:
    if rows:
        columns = list(rows[0])
        marks = ", ".join(f":{c}" for c in columns)
        names = ", ".join(f"`{c}`" for c in columns)
        conn.execute(text(f"INSERT INTO `{table}` ({names}) VALUES ({marks})"), rows)


def _library(rows, with_season: bool):
    out = []
    for user, game, platform, started, completed, completed_date, score, played, completion in rows:
        row = {"user_id": user, "game_id": game, "started_date": d(started), "platform": platform,
               "completed": completed, "completed_date": d(completed_date) if completed_date else None,
               "score": score, "played_time": played, "completion_time": completion}
        if with_season:
            row["season"] = d(started).year
        out.append(row)
    return out


def _time_entry(s: Session) -> dict:
    return {"id": s.id, "user_id": s.user_id, "user_clockify_id": f"clk-user-{s.user_id}" if s.user_id else None,
            "project_clockify_id": s.project, "start": s.start, "end": s.end, "duration": s.duration, "tags": None}


def load(engine) -> Expected:
    """Creates the v1 schema and its synthetic data on an empty database."""
    generated, edges = build_sessions(), build_edge_sessions()
    with engine.begin() as conn:
        for ddl in V1_TABLES.values():
            conn.execute(text(ddl))

        _insert(conn, "platform_tags", [{"id": i, "name": n} for i, n in PLATFORMS])
        _insert(conn, "users", [
            {"id": uid, "name": name, "username": username, "telegram_id": tg, "clockify_id": f"clk-user-{uid}",
             "is_admin": 1 if uid == 1 else 0, "password": FAKE_PASSWORD_HASH, "is_active": 1,
             "email": email, "clockify_key": f"not-a-real-key-{uid}"}
            for uid, name, username, email, tg in USERS
        ])
        _insert(conn, "games", [{"id": gid, "name": name, "avg_time": 36000} for name, gid in GAMES.items()])
        _insert(conn, "users_games", _library(LIBRARY_ACTIVE, with_season=True))
        _insert(conn, "users_games_2024", _library(LIBRARY_2024, with_season=True))
        _insert(conn, "users_games_historical", _library(LIBRARY_HISTORICAL, with_season=False))
        _insert(conn, "achievements", [{"id": i, "key": k, "title": t, "message": m} for i, k, t, m in ACHIEVEMENTS])
        _insert(conn, "users_achievements", [
            {"user_id": u, "achievement_id": a, "date": d(day), "game_id": g, "season": s}
            for u, a, day, g, s in USERS_ACHIEVEMENTS
        ])

        _insert(conn, "time_entries", [_time_entry(s) for s in generated + edges])
        # leftovers of the Clockify era and of earlier yearly resets; the migrations archive or drop them
        _insert(conn, "time_entries_historical", [_time_entry(s) for s in generated[:3]])
        _insert(conn, "time_entries_legacy", [
            {"id": None, "user_id": 1, "user_clockify_id": "clk-user-1", "project_clockify_id": HOLLOW,
             "games_name": "Hollow Pine", "start": "2022-05-05 20:00:00", "end": "2022-05-05 21:00:00",
             "duration": 3600.0, "tags": "pc", "completed": "no"},
        ])
        _insert(conn, "games_statistics", [{"game_id": HOLLOW, "played_time": 100, "avg_time": 36000, "current_ranking": 1}])
        _insert(conn, "games_statistics_historical", [{"game_id": STARDEW, "played_time": 50, "avg_time": 36000, "current_ranking": 2}])
        _insert(conn, "users_statistics", [{"user_id": u[0], "played_time": 100, "current_streak": 2, "best_streak": 5} for u in USERS])
        _insert(conn, "users_statistics_historical", [{"user_id": u[0], "played_time": 90} for u in USERS])
        _insert(conn, "logs", [{"player": "ana", "action": "start", "date": datetime.datetime(2025, 1, 1, 12, 0)}])
        _insert(conn, "request_sync", [{"request_id": "req-1"}, {"request_id": "req-2"}])
        _insert(conn, "other_tags", [{"id": "tag-completed", "name": "Completed"}])
    return expected_totals(generated, edges)
