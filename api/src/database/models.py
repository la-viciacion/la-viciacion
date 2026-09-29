from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    Computed,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Interval,
    LargeBinary,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import relationship

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
    # Legacy from the Clockify era; no longer written to, kept for history.
    clockify_id = Column(String(255))
    clockify_key = Column(String(255))
    email = Column(String(255))
    is_admin = Column(Integer)
    is_active = Column(Integer)
    avatar = Column(LargeBinary)

    # email is the login identifier, username the (unique) nickname
    __table_args__ = (UniqueConstraint("username"), UniqueConstraint("email", name="uq_users_email"))


class UserStatistics(Base):
    __tablename__ = "users_statistics"

    user_id = Column(Integer, primary_key=True)
    played_time = Column(Integer)
    current_ranking_hours = Column(Integer)
    current_streak = Column(Integer)
    best_streak = Column(Integer)
    best_streak_date = Column(Date)
    played_days = Column(Integer)
    best_unplayed_streak = Column(Integer)
    current_unplayed_streak = Column(Integer)
    best_unplayed_streak_date = Column(Date)
    played_games = Column(Integer)
    completed_games = Column(Integer)

    __table_args__ = (UniqueConstraint("user_id"),)


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


class GameStatistics(Base):
    __tablename__ = "games_statistics"

    game_id = Column(String(255), primary_key=True)
    played_time = Column(Integer)
    avg_time = Column(Integer)
    current_ranking = Column(Integer)

    __table_args__ = (UniqueConstraint("game_id"),)


class UserGame(Base):
    __tablename__ = "users_games"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer)
    game_id = Column(String(255))
    started_date = Column(Date, nullable=False)
    # derived by the database from started_date: never written by the app
    season = Column(Integer, Computed("YEAR(started_date)", persisted=False))
    platform = Column(String(255))
    completed = Column(Integer)
    completed_date = Column(Date)
    score = Column(Float)
    played_time = Column(Integer)
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
    user_id = Column(Integer)
    achievement_id = Column(Integer)
    date = Column(Date, nullable=False)
    # derived by the database from date: never written by the app
    season = Column(Integer, Computed("YEAR(`date`)", persisted=False))
    game_id = Column(String(255))
    # an achievement is earned once per user and season
    __table_args__ = (UniqueConstraint("user_id", "achievement_id", "season", name="uq_users_achievements_season"),)


class PlatformTag(Base):
    __tablename__ = "platform_tags"

    id = Column(String(255), primary_key=True)
    name = Column(String(255))
    __table_args__ = (UniqueConstraint("id"),)


class OtherTag(Base):
    __tablename__ = "other_tags"

    id = Column(String(255), primary_key=True)
    name = Column(String(255))
    __table_args__ = (UniqueConstraint("id"),)


class Log(Base):
    __tablename__ = "logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    player = Column(String(255))
    action = Column(String(255))
    date = Column(DateTime)


class RequestSync(Base):
    __tablename__ = "request_sync"

    id = Column(Integer, primary_key=True, autoincrement=True)
    request_id = Column(String(255), primary_key=True)


class GameTimer(Base):
    __tablename__ = "game_timers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False)
    game_id = Column(String(255), nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    platform = Column(String(255), nullable=True)
    # derived by the database from start_time: never written by the app
    season = Column(Integer, Computed("YEAR(start_time)", persisted=False))
    is_active = Column(Boolean, default=True)
    notes = Column(String(500), nullable=True)

    __table_args__ = (UniqueConstraint("user_id", "game_id", "start_time"),)
