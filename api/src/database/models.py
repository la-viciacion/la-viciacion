from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    Numeric,
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


GOD_USERNAME = "admin"


def not_god():
    """Condition that leaves out the emergency account: it is a door, not a player, so it never
    appears in rankings, statistics, notices or the lists of people (only the admin panel lists it)."""
    return User.username != GOD_USERNAME


class UserSettings(Base):
    """Personal preferences, one row per user (see utils/user_settings.py).

    Every column is NULL until the user sets it, and NULL means "use the default".
    """

    __tablename__ = "user_settings"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    # hours a timer may run before the user is reminded about it
    forgotten_timer_hours = Column(SmallInteger, nullable=True)
    # channels of that reminder (NULL = the default: on); the reminder is off when both are off
    forgotten_timer_telegram = Column(Boolean, nullable=True)
    forgotten_timer_push = Column(Boolean, nullable=True)
    # minutes between refreshes of the running-timer push notification (10-120)
    timer_notice_minutes = Column(SmallInteger, nullable=True)
    # whether the others see this player in "playing now" (NULL = the default: shown)
    show_playing = Column(Boolean, nullable=True)
    # where the player lives: a city chosen from a geocoder's answer (never a GPS fix), for the weather achievements.
    # All three are set or none is (checked in utils/user_settings.py)
    place_name = Column(String(255), nullable=True)
    place_latitude = Column(Numeric(8, 5), nullable=True)
    place_longitude = Column(Numeric(8, 5), nullable=True)
    # for the birthday achievement; only the player and the admins can read it
    birth_date = Column(Date, nullable=True)
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
    # RAWG's tags, comma separated ("Horror, Singleplayer, ..."): what the genres leave out (there is no Horror genre)
    tags = Column(Text, nullable=True)
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
    # time played is not stored: it is the sum of the sessions (crud/time_entries.entry_played_time)
    completion_time = Column(Integer)
    # when the player gave the game up (NULL = not abandoned). Whether it still counts as abandoned is derived:
    # a session after this moment resumes it (crud/users.is_abandoned)
    abandoned_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("user_id", "game_id", "platform", "season", name="uq_users_games_entry"),
    )


class UserWishlist(Base):
    """A game a player wants to play (or is waiting for). Only the wish is stored: whether the game is
    upcoming, whether the wish is still pending (the game is not in the player's library yet) and who else
    wants it are derived when asked (crud/wishlist.py)."""

    __tablename__ = "users_wishlist"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", name="fk_users_wishlist_user"), nullable=False)
    game_id = Column(String(255), ForeignKey("games.id", name="fk_users_wishlist_game"), nullable=False)
    added_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    __table_args__ = (UniqueConstraint("user_id", "game_id", name="uq_users_wishlist_user_game"),)


class GameScore(Base):
    """A player's rating of a game, 1-100: one per user and game, whatever the seasons or platforms."""

    __tablename__ = "game_scores"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", name="fk_game_scores_user"), nullable=False)
    game_id = Column(String(255), ForeignKey("games.id", name="fk_game_scores_game"), nullable=False)
    score = Column(SmallInteger, nullable=False)
    updated_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), onupdate=text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        UniqueConstraint("user_id", "game_id", name="uq_game_scores_user_game"),
        CheckConstraint("score BETWEEN 1 AND 100", name="ck_game_scores_range"),
    )


class WeatherDay(Base):
    """The weather of one past day at one place, kept so that a day is asked for to Open-Meteo only once.

    It is outside data that never changes after the day is over, not something derived from the sessions: that is why
    it can be stored. `codes` are the 24 WMO weather codes of the hours of the day, comma separated."""

    __tablename__ = "weather_days"

    # the place rounded to two decimals ("40.42,-3.70"): about a kilometre, and players in one city share it
    place = Column(String(24), primary_key=True)
    day = Column(Date, primary_key=True)
    codes = Column(String(120), nullable=False)
    fetched_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))


class Achievement(Base):
    __tablename__ = "achievements"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(255))
    title = Column(String(255))
    message = Column(String(255))
    image = Column(LargeBinary)
    # an achievement that is switched off is not earned, announced, recalculated or shown (see crud/achievements.py)
    active = Column(Boolean, nullable=False, server_default=text("1"))
    # a secret one is hidden from whoever has not unlocked it, and announced to the group without saying which
    # (the player gets the whole notice privately)
    secret = Column(Boolean, nullable=False, server_default=text("0"))
    # 0 = an ordinary one; 1, 2 and 3 are special ones: silver, gold and purple aura (front/js/lib/special.js)
    special = Column(SmallInteger, nullable=False, server_default=text("0"))
    # the first season it can be earned (before it nothing is awarded, recalculated or shown); see utils/achievements.py
    valid_from_season = Column(SmallInteger, nullable=False, server_default=text("2023"))
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


class PasswordReset(Base):
    """A one-time password recovery link (see utils/password_reset.py). Only the hash of the
    token is stored: a copy of the database cannot be used to reset anybody's password."""

    __tablename__ = "password_resets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer, ForeignKey("users.id", name="fk_password_resets_user", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash = Column(String(64), nullable=False)
    created_at = Column(DateTime, nullable=False)  # UTC
    expires_at = Column(DateTime, nullable=False)  # UTC
    used_at = Column(DateTime, nullable=True)  # UTC

    __table_args__ = (UniqueConstraint("token_hash", name="uq_password_resets_token"),)


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


class AuditLog(Base):
    """What an admin changed from the admin panel (see utils/audit.py): one row per successful write."""

    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), index=True)
    # the account may be deleted later: the name stays, the key is set to NULL
    user_id = Column(Integer, ForeignKey("users.id", name="fk_audit_log_user", ondelete="SET NULL"), nullable=True)
    username = Column(String(255), nullable=False)
    method = Column(String(10), nullable=False)
    path = Column(String(255), nullable=False)
    # first segment under /manage ("timers") and the id of the row it touched
    entity = Column(String(50), nullable=True, index=True)
    entity_id = Column(String(255), nullable=True)
    status = Column(SmallInteger, nullable=False)
    # JSON: {"before": the row as it was, "body": what was sent (secrets hidden), "query": ...}
    detail = Column(Text, nullable=True)
