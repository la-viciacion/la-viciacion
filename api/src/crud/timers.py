"""Timers and sessions: starting, stopping and cancelling a timer, and the finished sessions a player enters, corrects
or removes by hand. The rules that keep one game at a time live here; who may do it is checked by the router."""
import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..crud import scores as scores_crud
from ..crud import users as users_crud
from ..database.models import Game, GameTimer, PlatformTag, User, UserGame
from ..database.schemas import (
    GameTimerCreate,
    GameTimerGroup,
    GameTimerGroupPage,
    ManualSessionCreate,
    NewGameUser,
    SessionUpdate,
)
from ..utils import seasons
from ..utils.refusal import Refused

MAX_SESSION = datetime.timedelta(hours=24)
FUTURE_SLACK = datetime.timedelta(minutes=1)


def lock_sessions(db: Session, user_id: int) -> None:
    """Hold the user's row until the transaction ends, so the checks that keep one game at a time (no other
    running timer, no overlap) and the write that follows cannot interleave with another request of the same
    user: two taps or two devices would otherwise both pass the check and leave two running timers."""
    db.query(User.id).filter(User.id == user_id).with_for_update().first()


def _valid_platform(db: Session, platform: str | None) -> str:
    if not platform or db.query(PlatformTag.id).filter(PlatformTag.id == platform).first() is None:
        raise Refused(400, "Plataforma no válida")
    return platform


# ── Running timers ──────────────────────────────────────────


def check_new_timer(db: Session, timer: GameTimerCreate) -> None:
    """The game (and the platform, when given) of a new timer must exist: nothing in the
    schema enforces it and a timer of an unknown game breaks every page that lists it."""
    if db.query(User.id).filter(User.id == timer.user_id).first() is None:
        raise Refused(404, "Usuario no encontrado")
    if db.query(Game.id).filter(Game.id == timer.game_id).first() is None:
        raise Refused(404, "Juego no encontrado")
    if timer.platform is not None:
        _valid_platform(db, timer.platform)


def create_timer(db: Session, timer: GameTimerCreate) -> tuple[GameTimer, bool]:
    """Start the timer. Returns it and whether the group must be told about a new game
    (the announcement is slow, so the caller sends it in the background)."""
    check_new_timer(db, timer)
    lock_sessions(db, timer.user_id)
    if get_active_timer(db, timer.user_id) is not None:
        raise Refused(400, "User already has an active timer. Stop it first.")

    # A timer never starts before the user's last finished session ended (manual
    # entries may end a minute "ahead" of the server clock): one game at a time.
    last_end = db.query(func.max(GameTimer.end_time)).filter(GameTimer.user_id == timer.user_id).scalar()
    started = datetime.datetime.now()
    if last_end is not None and last_end > started:
        started = last_end

    db_timer = GameTimer(
        user_id=timer.user_id,
        game_id=timer.game_id,
        start_time=started,
        platform=timer.platform,
        notes=timer.notes,
        is_active=True,
    )
    db.add(db_timer)
    try:
        db.commit()
    except IntegrityError:
        # the same game started twice within one second (a retried request): the table keeps seconds
        db.rollback()
        raise Refused(409, "Ya tienes un timer de ese juego que empieza a esa hora")
    db.refresh(db_timer)

    # One UserGame per (game, platform, season): the same game on another
    # platform, or in a later year, is a new entry.
    season = seasons.current()
    user = users_crud.get_user_by_id(db, timer.user_id)
    already_playing = (
        db.query(UserGame)
        .filter_by(user_id=timer.user_id, game_id=timer.game_id, platform=timer.platform, season=season)
        .first()
    )
    announce = False
    if already_playing is None and user is not None:
        # "new game" is announced the first time the user plays a game in a season,
        # whatever the platform: the same game on another platform is only a new entry
        announce = (
            db.query(UserGame.id).filter_by(user_id=timer.user_id, game_id=timer.game_id, season=season).first()
            is None
        )
        users_crud.add_new_game(db, game=NewGameUser(game_id=timer.game_id, platform=timer.platform), user=user)

    return db_timer, announce


def get_active_timer(db: Session, user_id: int) -> GameTimer | None:
    return db.query(GameTimer).filter(GameTimer.user_id == user_id, GameTimer.is_active == True).first()  # noqa: E712


def game_name(db: Session, game_id: str) -> str | None:
    return db.query(Game.name).filter(Game.id == game_id).scalar()


def _running(db: Session, timer_id: int, user_id: int) -> GameTimer:
    timer = (
        db.query(GameTimer)
        .filter(GameTimer.id == timer_id, GameTimer.user_id == user_id, GameTimer.is_active == True)  # noqa: E712
        .first()
    )
    if not timer:
        raise Refused(404, "Active timer not found")
    return timer


def stop_timer(db: Session, timer_id: int, user_id: int) -> GameTimer:
    lock_sessions(db, user_id)  # a second stop of the same timer waits, then finds it stopped
    timer = _running(db, timer_id, user_id)
    # a timer may start "ahead" of the clock (after a manual session that ended a minute early):
    # stopping it right away must not give it a negative duration
    timer.end_time = max(datetime.datetime.now(), timer.start_time)
    timer.duration_seconds = int((timer.end_time - timer.start_time).total_seconds())
    timer.is_active = False
    db.commit()
    db.refresh(timer)
    return timer


def cancel_timer(db: Session, timer_id: int, user_id: int) -> GameTimer:
    """Discard a running timer as if it had never started (nothing is recorded)."""
    lock_sessions(db, user_id)
    timer = _running(db, timer_id, user_id)
    # starting it created the library entry of that game/platform/season: do not leave it
    # empty behind unless the user has other sessions, a completion or a score there
    entry = (timer.platform, seasons.of(timer.start_time))
    db.delete(timer)
    db.flush()
    users_crud.drop_empty_entry(db, user_id, timer.game_id, *entry)
    db.commit()
    return timer


# ── History ─────────────────────────────────────────────────


def get_timer_history(db: Session, user_id: int, game_id: str | None = None, limit: int = 100) -> list[GameTimer]:
    query = db.query(GameTimer).filter(GameTimer.user_id == user_id)
    if game_id:
        query = query.filter(GameTimer.game_id == game_id)
    return query.order_by(GameTimer.start_time.desc()).limit(limit).all()


def get_grouped_timer_history(
    db: Session, user_id: int, limit: int, offset: int, sessions_per_game: int
) -> GameTimerGroupPage:
    """Finished sessions collapsed per game, most recently played game first."""
    finished = (GameTimer.user_id == user_id, GameTimer.is_active == False)  # noqa: E712

    total_games = db.query(func.count(func.distinct(GameTimer.game_id))).filter(*finished).scalar() or 0

    page = (
        db.query(
            GameTimer.game_id,
            func.max(GameTimer.start_time).label("last_played"),
            func.coalesce(func.sum(GameTimer.duration_seconds), 0).label("total_seconds"),
            func.count(GameTimer.id).label("session_count"),
        )
        .filter(*finished)
        .group_by(GameTimer.game_id)
        .order_by(func.max(GameTimer.start_time).desc())
        .limit(limit)
        .offset(offset)
        .all()
    )
    game_ids = [row.game_id for row in page]
    if not game_ids:
        return GameTimerGroupPage(groups=[], total_games=total_games)

    games = {g.id: g for g in db.query(Game).filter(Game.id.in_(game_ids)).all()}

    # the newest `sessions_per_game` sessions of every game of the page, in one query
    rank = func.row_number().over(partition_by=GameTimer.game_id, order_by=GameTimer.start_time.desc())
    ranked = (
        select(GameTimer.id.label("id"), rank.label("rank"))
        .where(*finished, GameTimer.game_id.in_(game_ids))
        .subquery("ranked")
    )
    sessions_by_game: dict[str, list[GameTimer]] = {game_id: [] for game_id in game_ids}
    newest = (
        db.query(GameTimer)
        .join(ranked, ranked.c.id == GameTimer.id)
        .filter(ranked.c.rank <= sessions_per_game)
        .order_by(GameTimer.game_id, GameTimer.start_time.desc())
        .all()
    )
    for session in newest:
        sessions_by_game[session.game_id].append(session)

    # platforms used per game, the most recently used first
    platforms_by_game: dict[str, list[str]] = {game_id: [] for game_id in game_ids}
    used = (
        db.query(GameTimer.game_id, GameTimer.platform)
        .filter(*finished, GameTimer.game_id.in_(game_ids), GameTimer.platform.isnot(None))
        .group_by(GameTimer.game_id, GameTimer.platform)
        .order_by(func.max(GameTimer.start_time).desc())
        .all()
    )
    for game_id, platform in used:
        platforms_by_game[game_id].append(platform)

    # games the user has completed in the running season
    completed = {
        game_id
        for (game_id,) in db.query(UserGame.game_id)
        .filter(
            UserGame.user_id == user_id,
            UserGame.game_id.in_(game_ids),
            UserGame.completed == 1,
            UserGame.season == seasons.current(),
        )
        .distinct()
    }

    ratings = scores_crud.user_scores(db, user_id)
    groups = []
    for row in page:
        game = games.get(row.game_id)
        sessions = sessions_by_game[row.game_id]
        groups.append(
            GameTimerGroup(
                game_id=row.game_id,
                game_name=game.name if game else None,
                image_url=game.image_url if game else None,
                platform=sessions[0].platform if sessions else None,
                platforms=platforms_by_game[row.game_id],
                last_played=row.last_played,
                total_seconds=int(row.total_seconds),
                session_count=row.session_count,
                completed=row.game_id in completed,
                score=ratings.get(row.game_id),
                sessions=sessions,
            )
        )
    return GameTimerGroupPage(groups=groups, total_games=total_games)


def game_platforms(db: Session, user_id: int, game_id: str) -> tuple[bool, list[str]]:
    """What the user has already played of a game: whether there is any history and which platforms were used
    (most recent first; those of the library entries count too: sessions without a platform, a game added
    without any timer yet)."""
    rows = (
        db.query(GameTimer.platform)
        .filter(GameTimer.user_id == user_id, GameTimer.game_id == game_id, GameTimer.platform.isnot(None))
        .group_by(GameTimer.platform)
        .order_by(func.max(GameTimer.start_time).desc())
        .all()
    )
    platforms = [r.platform for r in rows]
    library = (
        db.query(UserGame.platform)
        .filter(UserGame.user_id == user_id, UserGame.game_id == game_id, UserGame.platform.isnot(None))
        .order_by(UserGame.season.desc())
        .all()
    )
    for r in library:
        if r.platform not in platforms:
            platforms.append(r.platform)
    has_history = bool(platforms) or (
        db.query(GameTimer.id).filter(GameTimer.user_id == user_id, GameTimer.game_id == game_id).first() is not None
    )
    return has_history, platforms


# ── Manual sessions: enter, correct or remove a finished session ──────────


def _check_season(current_user: User, *days: datetime.date | datetime.datetime):
    """Only the running season can be edited by its owner (closed seasons are frozen; admins may)."""
    current = seasons.current()
    if not current_user.is_admin and any(seasons.of(d) != current for d in days):
        raise Refused(400, f"Solo se pueden registrar, editar o borrar sesiones de la temporada actual ({current})")


def validate_session(
    db: Session,
    current_user: User,
    user_id: int,
    start: datetime.datetime,
    end: datetime.datetime,
    exclude_id: int | None = None,
) -> None:
    """Rules for a finished session (create and edit): sensible times, current season,
    and no overlap with anything else the same user played (or is playing)."""
    if end <= start:
        raise Refused(400, "El fin debe ser posterior al inicio")
    if end > datetime.datetime.now() + FUTURE_SLACK:
        raise Refused(400, "La sesión no puede terminar en el futuro")
    if end - start > MAX_SESSION:
        raise Refused(400, "Una sesión no puede durar más de 24 horas")
    _check_season(current_user, start, end)

    overlapping = db.query(GameTimer).filter(
        GameTimer.user_id == user_id,
        GameTimer.start_time < end,
        or_(GameTimer.end_time.is_(None), GameTimer.end_time > start),
    )
    if exclude_id is not None:
        overlapping = overlapping.filter(GameTimer.id != exclude_id)
    other = overlapping.first()
    if other is not None:
        name = game_name(db, other.game_id) or other.game_id
        when = other.start_time.strftime("%d/%m %H:%M") + (
            "" if other.end_time is None else " a " + other.end_time.strftime("%H:%M")
        )
        raise Refused(409, f"Se solapa con otra sesión ({name}, {when})")


def _commit_session(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise Refused(409, "Ya tienes una sesión de ese juego que empieza a esa hora")


def create_manual_session(db: Session, current_user: User, user_id: int, body: ManualSessionCreate) -> GameTimer:
    """A finished session of `user_id` entered by hand (the caller already checked it may)."""
    if db.query(Game.id).filter(Game.id == body.game_id).first() is None:
        raise Refused(404, "Juego no encontrado")
    platform = _valid_platform(db, body.platform)
    lock_sessions(db, user_id)
    if get_active_timer(db, user_id) is not None:
        raise Refused(409, "Tienes un timer en curso: páralo o cancélalo antes de añadir una sesión manual")
    validate_session(db, current_user, user_id, body.start_time, body.end_time)

    timer = GameTimer(
        user_id=user_id,
        game_id=body.game_id,
        start_time=body.start_time,
        end_time=body.end_time,
        duration_seconds=int((body.end_time - body.start_time).total_seconds()),
        platform=platform,
        notes=body.notes,
        is_active=False,
    )
    db.add(timer)
    # the library entry of that game/platform/season, without announcing "new game"
    users_crud.ensure_library_entry(db, user_id, body.game_id, platform, body.start_time)
    _commit_session(db)
    db.refresh(timer)
    return timer


def get_session(db: Session, timer_id: int) -> GameTimer:
    timer = db.query(GameTimer).filter(GameTimer.id == timer_id).first()
    if timer is None:
        raise Refused(404, "Sesión no encontrada")
    return timer


def _finished(timer: GameTimer) -> None:
    if timer.is_active:
        raise Refused(409, "Es un timer en curso: páralo antes de editarlo")


def update_session(db: Session, current_user: User, timer: GameTimer, body: SessionUpdate) -> GameTimer:
    """Correct a finished session (platform, start, end, notes); the caller already checked it may."""
    _finished(timer)
    old_entry = (timer.platform, seasons.of(timer.start_time))
    data = body.model_dump(exclude_unset=True)
    start = data.get("start_time") or timer.start_time
    end = data.get("end_time") or timer.end_time
    # a session of a closed season cannot be edited by its owner, nor moved out of the current one
    _check_season(current_user, timer.start_time)
    lock_sessions(db, timer.user_id)
    validate_session(db, current_user, timer.user_id, start, end, exclude_id=timer.id)
    if "platform" in data:
        timer.platform = _valid_platform(db, data["platform"])
    if "notes" in data:
        timer.notes = data["notes"]
    timer.start_time, timer.end_time = start, end
    timer.duration_seconds = int((end - start).total_seconds())
    users_crud.ensure_library_entry(db, timer.user_id, timer.game_id, timer.platform, start)
    # moving a session to another platform or season must not leave its old entry empty behind
    db.flush()
    if old_entry != (timer.platform, seasons.of(start)):
        users_crud.drop_empty_entry(db, timer.user_id, timer.game_id, *old_entry)
    _commit_session(db)
    db.refresh(timer)
    return timer


def delete_session(db: Session, current_user: User, timer: GameTimer) -> None:
    """Remove a finished session; the caller already checked it may."""
    _finished(timer)
    _check_season(current_user, timer.start_time)
    db.delete(timer)
    db.commit()
