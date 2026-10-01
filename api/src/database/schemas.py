import datetime
from typing import List, Optional, Union

from pydantic import BaseModel, Field

NOTES_MAX = 500  # width of game_timers.notes


class UserBase(BaseModel):
    username: str


class User(UserBase):
    id: int
    name: str | None = None
    telegram_id: int | None = None
    is_admin: int | None = 0
    email: str | None = None
    is_active: int | None = 0

    class Config:
        from_attributes = True


class UserProfileUpdate(BaseModel):
    name: str | None = None
    email: str | None = None
    telegram_id: int | None = None


class UserSettingsUpdate(BaseModel):
    # whole hours; None goes back to the default (the range is checked in the route)
    forgotten_timer_hours: int | None = None
    # whole minutes, 10-120 (checked in the route)
    timer_notice_minutes: int | None = None


class CompletionUpdate(BaseModel):
    completed: bool
    completed_date: datetime.date | None = None


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


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
    rawg_id: int | None = None

    class Config:
        from_attributes = True


class NewGame(BaseModel):
    name: str
    dev: Optional[str | None] = None
    release_date: Optional[datetime.date | None] = None
    steam_id: Optional[str | None] = None
    image_url: Optional[str | None] = None
    genres: Optional[str | None] = None
    avg_time: Optional[int | None] = None
    slug: Optional[str | None] = None
    rawg_id: Optional[int | None] = None


class UpdateGame(BaseModel):
    name: str
    dev: Optional[str | None] = None
    release_date: Optional[datetime.date | None] = None
    steam_id: Optional[str | None] = None
    image_url: Optional[str | None] = None
    genres: Optional[str | None] = None
    avg_time: Optional[int | None] = None
    slug: Optional[str | None] = None
    rawg_id: Optional[int | None] = None


class RawgGameCandidate(BaseModel):
    rawg_id: int
    name: str
    slug: str
    released: Optional[str | None] = None
    image_url: Optional[str | None] = None
    genres: list[str] = []
    platforms: list[str] = []
    rating: Optional[float | None] = None
    metacritic: Optional[int | None] = None
    exists_in_db: bool = False
    db_game_id: Optional[str | None] = None


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


# Game Timer Schemas
class GameTimerBase(BaseModel):
    user_id: int
    game_id: str
    platform: str | None = None
    notes: str | None = Field(default=None, max_length=NOTES_MAX)


class GameTimerCreate(GameTimerBase):
    pass


class ManualSessionCreate(BaseModel):
    """A finished session entered by hand."""

    user_id: int | None = None  # default: the logged-in user (admins may pass another)
    game_id: str
    platform: str
    start_time: datetime.datetime
    end_time: datetime.datetime
    notes: str | None = Field(default=None, max_length=NOTES_MAX)


class SessionUpdate(BaseModel):
    platform: str | None = None
    start_time: datetime.datetime | None = None
    end_time: datetime.datetime | None = None
    notes: str | None = Field(default=None, max_length=NOTES_MAX)


class GameTimerResponse(GameTimerBase):
    id: int
    season: int | None = None  # derived from start_time
    start_time: datetime.datetime
    end_time: datetime.datetime | None = None
    duration_seconds: int | None = None
    is_active: bool = True

    class Config:
        from_attributes = True


class GameTimerGroup(BaseModel):
    """All finished sessions of one game, collapsed into a single history row."""

    game_id: str
    game_name: str | None = None
    image_url: str | None = None
    platform: str | None = None  # platform of the most recent session
    platforms: list[str] = []  # every platform used, most recent first
    last_played: datetime.datetime
    total_seconds: int
    session_count: int
    # Most recent sessions first, capped by the endpoint's sessions_per_game.
    sessions: list[GameTimerResponse]


class GamePlatformsResponse(BaseModel):
    has_history: bool
    platforms: list[str]


class GameTimerGroupPage(BaseModel):
    groups: list[GameTimerGroup]
    total_games: int


class ActiveTimerResponse(BaseModel):
    is_active: bool
    timer: GameTimerResponse | None = None
