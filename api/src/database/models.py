from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Computed,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import deferred

from .database import Base

#############################
#### LA VICIACION TABLES ####
#############################


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255))
    username = Column(String(255))
    password = Column(String(255))
    telegram_id = Column(BigInteger)
    email = Column(String(255))
    is_admin = Column(Integer)
    is_active = Column(Integer)
    # not loaded with the user: nearly every request loads the user (auth) and none needs the picture
    avatar = deferred(Column(LargeBinary))

    # email is the login identifier, username the (unique) nickname
    __table_args__ = (
        UniqueConstraint("username"),
        UniqueConstraint("email", name="uq_users_email"),
        # the bot recognizes people by it; NULL (not set) may repeat
        UniqueConstraint("telegram_id", name="uq_users_telegram_id"),
    )


class UserSettings(Base):
    """Personal preferences, one row per user (see utils/user_settings.py).

    Every column is NULL until the user sets it, and NULL means "use the default".
    """

    __tablename__ = "user_settings"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    # hours a timer may run before the user is reminded about it
    forgotten_timer_hours = Column(SmallInteger, nullable=True)
    updated_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"), onupdate=text("CURRENT_TIMESTAMP"))


class Game(Base):
    __tablename__ = "games"

    id = Column(String(255), primary_key=True)
    name = Column(String(255))
    dev = Column(String(255))
    release_date = Column(Date)
    steam_id = Column(String(255))
    image_url = Column(String(255))
    genres = Column(String(255))
    avg_time = Column(Integer)
    slug = Column(String(255))
    rawg_id = Column(Integer, nullable=True, index=True)

    __table_args__ = (UniqueConstraint("name"),)


class UserGame(Base):
    __tablename__ = "users_games"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", name="fk_users_games_user"))
    game_id = Column(String(255), ForeignKey("games.id", name="fk_users_games_game"))
    started_date = Column(Date, nullable=False)
    # derived by the database from started_date: never written by the app
    season = Column(Integer, Computed("YEAR(started_date)", persisted=False))
    platform = Column(String(255), ForeignKey("platform_tags.id", name="fk_users_games_platform"))
    completed = Column(Integer)
    completed_date = Column(Date)
    score = Column(Float)
    # time played is not stored: it is the sum of the sessions (crud/time_entries.entry_played_time)
    completion_time = Column(Integer)

    __table_args__ = (
        UniqueConstraint("user_id", "game_id", "platform", "season", name="uq_users_games_entry"),
    )


class Achievement(Base):
    __tablename__ = "achievements"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(255))
    title = Column(String(255))
    message = Column(String(255))
    image = Column(LargeBinary)
    __table_args__ = (UniqueConstraint("key"),)


class UserAchievement(Base):
    __tablename__ = "users_achievements"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", name="fk_users_achievements_user"))
    achievement_id = Column(Integer, ForeignKey("achievements.id", name="fk_users_achievements_ach"))
    date = Column(Date, nullable=False)
    # derived by the database from date: never written by the app
    season = Column(Integer, Computed("YEAR(`date`)", persisted=False))
    game_id = Column(String(255), ForeignKey("games.id", name="fk_users_achievements_game"))
    # an achievement is earned once per user and season
    __table_args__ = (UniqueConstraint("user_id", "achievement_id", "season", name="uq_users_achievements_season"),)


class PlatformTag(Base):
    __tablename__ = "platform_tags"

    id = Column(String(255), primary_key=True)
    name = Column(String(255))
    __table_args__ = (UniqueConstraint("id"),)


class GameTimer(Base):
    __tablename__ = "game_timers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", name="fk_game_timers_user"), nullable=False)
    game_id = Column(String(255), ForeignKey("games.id", name="fk_game_timers_game"), nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    platform = Column(String(255), ForeignKey("platform_tags.id", name="fk_game_timers_platform"), nullable=True)
    # derived by the database from start_time: never written by the app
    season = Column(Integer, Computed("YEAR(start_time)", persisted=False))
    is_active = Column(Boolean, default=True)
    notes = Column(String(500), nullable=True)

    __table_args__ = (UniqueConstraint("user_id", "game_id", "start_time"),)


class AppSetting(Base):
    """Settings edited from the admin panel (see utils/settings.py)."""

    __tablename__ = "app_settings"

    key = Column(String(100), primary_key=True)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"), onupdate=text("CURRENT_TIMESTAMP"))
    # who edited it; ON DELETE SET NULL
    updated_by = Column(
        Integer, ForeignKey("users.id", name="fk_app_settings_updated_by", ondelete="SET NULL"), nullable=True
    )


class JobRun(Base):
    """Last run of each scheduled job (see utils/scheduler.py)."""

    __tablename__ = "job_runs"

    job = Column(String(100), primary_key=True)
    last_run_at = Column(DateTime, nullable=False)
    last_status = Column(String(255), nullable=True)


class PushSubscription(Base):
    """A device that receives Web Push notifications (see utils/push.py)."""

    __tablename__ = "push_subscriptions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer, ForeignKey("users.id", name="fk_push_subscriptions_user", ondelete="CASCADE"), nullable=False, index=True
    )
    endpoint = Column(String(700), nullable=False)
    p256dh = Column(String(255), nullable=False)
    auth = Column(String(255), nullable=False)
    # also receive what goes to the Telegram group (private notices always arrive)
    receive_group = Column(Boolean, nullable=False, server_default=text("1"))
    user_agent = Column(String(255), nullable=True)
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))

    __table_args__ = (UniqueConstraint("endpoint", name="uq_push_subscriptions_endpoint"),)
