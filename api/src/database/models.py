from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Index,
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
    # channels of the notice of the day a wished game comes out (NULL = the default: on); off when both are off
    wishlist_release_telegram = Column(Boolean, nullable=True)
    wishlist_release_push = Column(Boolean, nullable=True)
    # where the notices about the player's challenges go (NULL = the default: the notices on, the reminders off)
    challenge_notices_telegram = Column(Boolean, nullable=True)
    challenge_notices_push = Column(Boolean, nullable=True)
    challenge_reminders_telegram = Column(Boolean, nullable=True)
    challenge_reminders_push = Column(Boolean, nullable=True)
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
    # A DLC / expansion / edition, with or without its base game: the link is optional (a game made by hand may not
    # say which, RAWG's base may not be in the catalogue). Deleting the base game leaves the DLC marked, unlinked
    is_dlc = Column(Boolean, nullable=False, server_default=text("0"), default=False)
    parent_game_id = Column(String(255), ForeignKey("games.id", name="fk_games_parent", ondelete="SET NULL"), nullable=True)

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
    # when the player gave the game up (NULL = not abandoned). Whether it still counts as abandoned is derived:
    # a session after this moment resumes it (crud/users.is_abandoned)
    abandoned_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("user_id", "game_id", "platform", "season", name="uq_users_games_entry"),
    )


class UserGamePrice(Base):
    """What a player paid for a game on a platform (a game bought on two platforms is two purchases). Only the price is
    stored: the cost per hour is derived (crud/game_prices.py)."""

    __tablename__ = "users_game_prices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", name="fk_game_prices_user", ondelete="CASCADE"), nullable=False)
    game_id = Column(String(255), ForeignKey("games.id", name="fk_game_prices_game", ondelete="CASCADE"), nullable=False)
    platform = Column(String(255), ForeignKey("platform_tags.id", name="fk_game_prices_platform"), nullable=False)
    amount_cents = Column(Integer, nullable=False)  # euro cents, 0 for a free game
    updated_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    __table_args__ = (UniqueConstraint("user_id", "game_id", "platform", name="uq_game_prices_purchase"),)


class UserWishlist(Base):
    """A game a player wants to play (or is waiting for). Only the wish is stored: whether the game is
    upcoming, whether it is in the player's library and who else wants it are derived when asked
    (crud/wishlist.py). A wish stays until the player removes it."""

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
    # not loaded with the achievement: only the image route reads it, and the lists of awards load many rows
    image = deferred(Column(LargeBinary))
    # an achievement that is switched off is not earned, announced, recalculated or shown (see crud/achievements.py)
    active = Column(Boolean, nullable=False, server_default=text("1"))
    # a secret one is hidden from whoever has not unlocked it, and announced to the group without saying which
    # (the player gets the whole notice privately). Independent of `special`: an achievement is either, both or neither
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


class UserNotification(Base):
    """A notice in a player's inbox (see utils/inbox.py): what the group and the player were told, kept for a few days."""

    __tablename__ = "user_notifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer, ForeignKey("users.id", name="fk_user_notifications_user", ondelete="CASCADE"), nullable=False
    )
    title = Column(String(80), nullable=False)
    body = Column(String(255), nullable=False, server_default=text("''"))
    # where a tap opens the app (a path or a #/ route of this site)
    url = Column(String(200), nullable=False, server_default=text("'/'"))
    created_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    read_at = Column(DateTime, nullable=True)

    __table_args__ = (Index("ix_user_notifications_user_created", "user_id", "created_at"),)


class Challenge(Base):
    """A time-boxed goal made from a template in code (utils/challenges.py): only the definition is stored.
    Progress and completion are derived from the sessions and the library when asked."""

    __tablename__ = "challenges"

    id = Column(Integer, primary_key=True, autoincrement=True)
    kind = Column(String(32), nullable=False)  # the template
    scope = Column(String(8), nullable=False)  # 'group' or 'user'
    owner_user_id = Column(Integer, ForeignKey("users.id", name="fk_challenges_owner", ondelete="CASCADE"), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id", name="fk_challenges_creator", ondelete="SET NULL"), nullable=True)
    visibility = Column(String(8), nullable=False, server_default=text("'public'"))
    # 'auto': every active player takes part and may opt out; 'opt_in' is prepared and not used yet
    participation = Column(String(8), nullable=False, server_default=text("'auto'"))
    title = Column(String(120), nullable=False)
    params = Column(Text, nullable=False)  # the template's options, JSON
    game_id = Column(String(255), ForeignKey("games.id", name="fk_challenges_game", ondelete="CASCADE"), nullable=True)
    starts_on = Column(Date, nullable=False)
    ends_on = Column(Date, nullable=False)
    # a hash of kind, options, period and owner: an equal challenge is refused
    fingerprint = Column(String(64), nullable=False)
    # when the group was told its total was reached (said once)
    total_notified_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    __table_args__ = (UniqueConstraint("fingerprint", name="uq_challenges_fingerprint"),)


class ChallengeOptOut(Base):
    """A player who chose not to take part in a challenge."""

    __tablename__ = "challenge_optouts"

    challenge_id = Column(Integer, ForeignKey("challenges.id", name="fk_challenge_optouts_challenge", ondelete="CASCADE"), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", name="fk_challenge_optouts_user", ondelete="CASCADE"), primary_key=True)
    created_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))


class ChallengeProposal(Base):
    """A group challenge a player proposes; an admin approves it (it is launched as a `Challenge`) or rejects it."""

    __tablename__ = "challenge_proposals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    proposer_id = Column(Integer, ForeignKey("users.id", name="fk_challenge_proposals_proposer", ondelete="CASCADE"), nullable=False)
    kind = Column(String(32), nullable=False)  # the template
    options = Column(Text, nullable=False)  # what the player chose, JSON
    title = Column(String(120), nullable=False)  # as the challenge would be called
    # the hash of the challenge it would be: an equal pending proposal is refused
    fingerprint = Column(String(64), nullable=False)
    status = Column(String(8), nullable=False, server_default=text("'pending'"))  # pending, approved or rejected
    decision_note = Column(String(255), nullable=True)
    decided_by = Column(Integer, ForeignKey("users.id", name="fk_challenge_proposals_decider", ondelete="SET NULL"), nullable=True)
    decided_at = Column(DateTime, nullable=True)
    challenge_id = Column(Integer, ForeignKey("challenges.id", name="fk_challenge_proposals_challenge", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))


class ChallengeSchedule(Base):
    """A group challenge that launches itself every month (crud/challenge_schedules.py). Only the definition is
    stored: the game of a month is worked out from `first_month` and the list of games."""

    __tablename__ = "challenge_schedules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    label = Column(String(80), nullable=False)
    kind = Column(String(32), nullable=False)  # the template
    options = Column(Text, nullable=False)  # the options of the template without the month and the game, JSON
    games = Column(Text, nullable=True)  # the game ids a game of the month rotates along, JSON
    participation = Column(String(8), nullable=False, server_default=text("'auto'"))
    announce = Column(Boolean, nullable=False, server_default=text("0"))  # tell the group when it launches
    active = Column(Boolean, nullable=False, server_default=text("1"))
    first_month = Column(Date, nullable=False)  # the first day of the first month it launches for
    last_month = Column(Date, nullable=True)  # the first day of the last month it was launched for
    last_status = Column(String(255), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id", name="fk_challenge_schedules_creator", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))


class GroupPoll(Base):
    """A non-anonymous Telegram poll an admin launched into the group (crud/group_polls.py). The tally and the winner
    are derived from the votes when asked."""

    __tablename__ = "group_polls"

    id = Column(Integer, primary_key=True, autoincrement=True)
    question = Column(String(300), nullable=False)
    options = Column(Text, nullable=False)  # JSON list of the option texts, in the order Telegram shows them
    option_keys = Column(Text, nullable=True)  # JSON list of the ids Telegram gave the options, as `options`; NULL = launched before them
    multiple = Column(Boolean, nullable=False, server_default=text("0"))  # several answers allowed
    allow_adding_options = Column(Boolean, nullable=False, server_default=text("0"))  # the group may add options in Telegram
    telegram_poll_id = Column(String(32), nullable=False)  # what an answer of the bot names
    telegram_message_id = Column(BigInteger, nullable=False)  # what stopping the poll in Telegram needs
    closes_at = Column(DateTime, nullable=True)  # the deadline; NULL = only by hand
    closed_at = Column(DateTime, nullable=True)  # NULL = open; once set no answer counts
    closed_by = Column(Integer, ForeignKey("users.id", name="fk_group_polls_closer", ondelete="SET NULL"), nullable=True)
    telegram_stopped = Column(Boolean, nullable=False, server_default=text("0"))  # Telegram was told to stop it
    telegram_voters = Column(Integer, nullable=True)  # the voters Telegram counted when it was stopped
    created_by = Column(Integer, ForeignKey("users.id", name="fk_group_polls_creator", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    __table_args__ = (UniqueConstraint("telegram_poll_id", name="uq_group_polls_telegram"),)


class GroupPollVote(Base):
    """What one person has chosen in a poll now (an empty choice is a row deleted). The account is derived from
    `users.telegram_id` when asked; a voter with no account is just an id."""

    __tablename__ = "group_poll_votes"

    poll_id = Column(Integer, ForeignKey("group_polls.id", name="fk_group_poll_votes_poll", ondelete="CASCADE"), primary_key=True, autoincrement=False)
    telegram_user_id = Column(BigInteger, primary_key=True, autoincrement=False)
    option_ids = Column(Text, nullable=False)  # JSON list of the positions chosen
    updated_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))


class AuditLog(Base):
    """The audit log (see utils/audit.py): one row per successful write of the admin panel, and one per security event."""

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
    # what happened when the row is not a panel write ("login_failed"...); NULL for a panel write
    event = Column(String(40), nullable=True, index=True)
    ip = Column(String(45), nullable=True)
    user_agent = Column(String(255), nullable=True)
