import datetime
from typing import Dict, List, Optional, Union

from pydantic import BaseModel


class UserBase(BaseModel):
    username: str


class UserCreate(UserBase):
    email: str
    name: str
    password: str
    invitation_key: str


class User(UserBase):
    id: int
    name: str | None = None
    telegram_id: int | None = None
    is_admin: int | None = 0
    email: str | None = None
    is_active: int | None = 0
    clockify_id: str | None = None
    clockify_key: str | None = None

    class Config:
        from_attributes = True


class UserForAdmins(UserBase):
    id: int
    name: str | None = None
    telegram_id: int | None = None
    is_admin: int | None = 0
    email: str | None = None
    is_active: int | None = 0
    clockify_id: str | None = None
    clockify_key: str | None = None


class UserStatistics(BaseModel):
    user_id: int
    played_time: int | None = 0
    current_ranking_hours: int | None = None
    current_streak: int | None = 0
    best_streak: int | None = 0
    best_streak_date: datetime.date | None = None
    played_days: int | None = 0
    best_unplayed_streak: int | None = None
    current_unplayed_streak: int | None = None
    best_unplayed_streak_date: datetime.date | None = None


class UserUpdate(BaseModel):
    name: str | None = None
    username: str
    password: str | None = None
    email: str | None = None
    telegram_id: int | None = None
    clockify_id: str | None = None
    clockify_key: str | None = None


class UserUpdateForAdmin(BaseModel):
    name: str | None = None
    username: str
    password: str | None = None
    email: str | None = None
    telegram_id: int | None = None
    is_admin: int | None = None
    is_active: int | None = None
    clockify_id: str | None = None
    clockify_key: str | None = None


class TelegramUser(BaseModel):
    username: str
    telegram_id: int


class Game(BaseModel):
    id: str
    name: str
    dev: str | None = None
    release_date: Union[datetime.date, str, None] = None
    steam_id: str | None = None
    image_url: str | None = None
    genres: str | None = None
    avg_time: int | None = 0
    slug: str | None = None

    class Config:
        from_attributes = True


class GameStatistics(BaseModel):
    game_id: str
    played_time: int | None = 0
    avg_time: int | None = 0
    current_ranking: Optional[int | None] = 10000000

    class Config:
        from_attributes = True


class NewGame(BaseModel):
    clockify_id: Optional[str | None] = None
    name: str
    dev: Optional[str | None] = None
    release_date: Optional[datetime.date | None] = None
    steam_id: Optional[str | None] = None
    image_url: Optional[str | None] = None
    genres: Optional[str | None] = None
    avg_time: Optional[int | None] = None
    slug: Optional[str | None] = None


class UpdateGame(BaseModel):
    name: str
    dev: Optional[str | None] = None
    release_date: Optional[datetime.date | None] = None
    steam_id: Optional[str | None] = None
    image_url: Optional[str | None] = None
    genres: Optional[str | None] = None
    avg_time: Optional[int | None] = None


class NewGameUser(BaseModel):
    game_id: str
    platform: str | None = None


class UsersGamesBase(BaseModel):
    id: int

    class Config:
        from_attributes = True


class UserGame(UsersGamesBase):
    id: int | None = None
    user_id: int | None = None
    game_id: str | None = None
    game_name: str | None = None
    started_date: datetime.date | None = None
    platform_id: str | None = None
    platform_name: str | None = None
    completed: int | None = None
    completed_date: datetime.date | None = None
    score: float | None = None
    played_time: int | None = None
    completion_time: int | None = None


class Achievement(BaseModel):
    id: int | None = None
    key: str | None = None
    title: str | None = None
    message: str | None = None

    class Config:
        from_attributes = True


class UserAchievement(BaseModel):
    id: int | None = None
    user_id: int | None = None
    achievement_id: int | None = None
    date: datetime.date | None = None
    game_id: str | None = None

    class Config:
        from_attributes = True


class TimeEntrie(BaseModel):
    id: int | None = None
    user_id: str | None = None
    user_clockify_id: str | None = None
    project_clockify_id: str | None = None
    start: datetime.date | None = None
    end: datetime.date | None = None
    duration: int | None = None
    tags: str | None = None

    class Config:
        from_attributes = True


class Email(BaseModel):
    receiver: list[str]
    subject: str
    message: str


class HttpExceptionDetailModel(BaseModel):
    message: str
    code: str


class HttpException(BaseModel):
    detail: HttpExceptionDetailModel
