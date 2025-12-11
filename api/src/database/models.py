from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
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
    clockify_id = Column(String(255))
    clockify_key = Column(String(255))
    email = Column(String(255))
    is_admin = Column(Integer)
    is_active = Column(Integer)
    avatar = Column(LargeBinary)

    __table_args__ = (UniqueConstraint("username"),)


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


class UserStatisticsHistorical(Base):
    __tablename__ = "users_statistics_historical"

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

    __table_args__ = (UniqueConstraint("name"),)


class GameStatistics(Base):
    __tablename__ = "games_statistics"

    game_id = Column(String(255), primary_key=True)
    played_time = Column(Integer)
    avg_time = Column(Integer)
    current_ranking = Column(Integer)

    __table_args__ = (UniqueConstraint("game_id"),)


class GameStatisticsHistorical(Base):
    __tablename__ = "games_statistics_historical"

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
    started_date = Column(Date)
    season = Column(Integer)
    platform = Column(String(255))
    completed = Column(Integer)
    completed_date = Column(Date)
    score = Column(Float)
    played_time = Column(Integer)
    completion_time = Column(Integer)

    __table_args__ = (
        UniqueConstraint("user_id", "game_id", "platform", "season"),
    )


class UserGameHistorical(Base):
    __tablename__ = "users_games_historical"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer)
    game_id = Column(String(255))
    started_date = Column(Date)
    platform = Column(String(255))
    completed = Column(Integer)
    completed_date = Column(Date)
    score = Column(Float)
    played_time = Column(Integer)
    completion_time = Column(Integer)

    __table_args__ = (UniqueConstraint("user_id", "game_id", "platform"),)


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
    date = Column(Date)
    season = Column(Integer)
    game_id = Column(String(255))
    __table_args__ = (
        UniqueConstraint("user_id", "achievement_id", "date"),
        UniqueConstraint("user_id", "achievement_id", "season"),
    )


class UserAchievementHistorical(Base):
    __tablename__ = "users_achievements_historical"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer)
    achievement_id = Column(Integer)
    date = Column(Date)
    game_id = Column(String(255))
    __table_args__ = (UniqueConstraint("user_id", "achievement_id", "date"),)


class TimeEntry(Base):
    __tablename__ = "time_entries"

    id = Column(String(255), primary_key=True)
    user_id = Column(Integer)
    user_clockify_id = Column(String(255))
    project_clockify_id = Column(String(255))
    start = Column(DateTime)
    end = Column(DateTime)
    duration = Column(Integer)
    tags = Column(String(255))

    __table_args__ = (UniqueConstraint("id"),)


class TimeEntryHistorical(Base):
    __tablename__ = "time_entries_historical"

    id = Column(String(255), primary_key=True)
    user_id = Column(Integer)
    user_clockify_id = Column(String(255))
    project_clockify_id = Column(String(255))
    start = Column(DateTime)
    end = Column(DateTime)
    duration = Column(Integer)

    __table_args__ = (UniqueConstraint("id"),)


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


class CoreNotification(Base):
    __tablename__ = "core_notifications"

    notification = Column(String(255), primary_key=True)
    __table_args__ = (UniqueConstraint("notification"),)


class RequestSync(Base):
    __tablename__ = "request_sync"

    id = Column(Integer, primary_key=True, autoincrement=True)
    request_id = Column(String(255), primary_key=True)
