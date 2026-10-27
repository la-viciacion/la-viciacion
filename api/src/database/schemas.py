import datetime
from typing import Optional, Union

from pydantic import BaseModel, ConfigDict, Field, NaiveDatetime

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

    model_config = ConfigDict(from_attributes=True)


class UserProfileUpdate(BaseModel):
    name: str | None = None
    email: str | None = None
    telegram_id: int | None = None


class UserSettingsUpdate(BaseModel):
    # whole hours; None goes back to the default (the range is checked in the route)
    forgotten_timer_hours: int | None = None
    # channels of the forgotten-timer notice; None goes back to the default (on)
    forgotten_timer_telegram: bool | None = None
    forgotten_timer_push: bool | None = None
    # channels of the notice of the day a wished game comes out; None goes back to the default (on)
    wishlist_release_telegram: bool | None = None
    wishlist_release_push: bool | None = None
    # channels of the notices about the player's challenges (on by default) and of the reminders (off by default)
    challenge_notices_telegram: bool | None = None
    challenge_notices_push: bool | None = None
    challenge_reminders_telegram: bool | None = None
    challenge_reminders_push: bool | None = None
    # whole minutes, 10-120 (checked in the route)
    timer_notice_minutes: int | None = None
    # whether the others see the user in "playing now"; None goes back to the default (shown)
    show_playing: bool | None = None
    # the city the player lives in, as a geocoder gave it (all three, or none: null removes it); checked in the route
    place_name: str | None = Field(default=None, max_length=255)
    place_latitude: float | None = Field(default=None, ge=-90, le=90)
    place_longitude: float | None = Field(default=None, ge=-180, le=180)
    # for the birthday achievement; null removes it (the range is checked in the route)
    birth_date: datetime.date | None = None


class CompletionUpdate(BaseModel):
    completed: bool
    completed_date: datetime.date | None = None


class AbandonUpdate(BaseModel):
    abandoned: bool


class ScoreUpdate(BaseModel):
    score: int = Field(ge=1, le=100)


class PriceUpdate(BaseModel):
    """What was paid for a game on a platform, in euros (a number, or text with a comma); null takes the price off."""

    platform: str = Field(min_length=1, max_length=255)
    amount: float | str | None = None


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
    tags: str | None = None
    avg_time: int | None = 0
    slug: str | None = None
    rawg_id: int | None = None
    is_dlc: bool = False
    parent_game_id: str | None = None

    model_config = ConfigDict(from_attributes=True)


class NewGame(BaseModel):
    name: str
    dev: Optional[str | None] = None
    release_date: Optional[datetime.date | None] = None
    steam_id: Optional[str | None] = None
    image_url: Optional[str | None] = None
    genres: Optional[str | None] = None
    tags: Optional[str | None] = None
    avg_time: Optional[int | None] = None
    slug: Optional[str | None] = None
    rawg_id: Optional[int | None] = None
    is_dlc: bool = False
    # the base game in the catalogue; a game with one is a DLC whatever `is_dlc` says
    parent_game_id: Optional[str | None] = None
    # RAWG's id for the base game, set only by get_new_game_info so that creating the game can add the base: never stored
    parent_rawg_id: Optional[int | None] = None


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


class RawgParent(BaseModel):
    """The base game of a RAWG DLC / expansion, and whether it is already in the catalogue."""
    rawg_id: int
    name: str
    exists_in_db: bool = False
    db_game_id: Optional[str | None] = None


class NewGameUser(BaseModel):
    game_id: str
    platform: str | None = None


class UsersGamesBase(BaseModel):
    id: int

    model_config = ConfigDict(from_attributes=True)


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
    played_time: int | None = None


class Achievement(BaseModel):
    id: int | None = None
    key: str | None = None
    title: str | None = None
    message: str | None = None

    model_config = ConfigDict(from_attributes=True)


class UserAchievement(BaseModel):
    id: int | None = None
    user_id: int | None = None
    achievement_id: int | None = None
    date: datetime.date | None = None
    game_id: str | None = None

    model_config = ConfigDict(from_attributes=True)


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

    model_config = ConfigDict(from_attributes=True)


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
    completed: bool = False  # completed in the running season
    score: int | None = None  # the user's rating of the game, 1-100
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
    game_name: str | None = None  # so the timer card needs no second request
    score: int | None = None  # the user's rating of the running game, 1-100


# ── Export file (crud/data_export.py): what "Importar datos" accepts ──
# Bounded on purpose: the file comes from outside. Datetimes are naive, like the database's (server-local).


class ExportGame(BaseModel):
    id: str = Field(min_length=1, max_length=255)
    name: str = Field(min_length=1, max_length=255)
    dev: str | None = Field(default=None, max_length=255)
    release_date: datetime.date | None = None
    genres: str | None = Field(default=None, max_length=255)
    avg_time: int | None = None
    image_url: str | None = Field(default=None, max_length=255)
    slug: str | None = Field(default=None, max_length=255)
    steam_id: str | None = Field(default=None, max_length=255)
    rawg_id: int | None = None


class ExportPlatform(BaseModel):
    id: str = Field(min_length=1, max_length=255)
    name: str | None = Field(default=None, max_length=255)


class ExportLibraryEntry(BaseModel):
    game_id: str = Field(min_length=1, max_length=255)
    platform: str | None = Field(default=None, max_length=255)
    started_date: datetime.date
    completed: bool = False
    completed_date: datetime.date | None = None
    abandoned_at: NaiveDatetime | None = None


class ExportSession(BaseModel):
    game_id: str = Field(min_length=1, max_length=255)
    platform: str | None = Field(default=None, max_length=255)
    start_time: NaiveDatetime
    end_time: NaiveDatetime
    notes: str | None = Field(default=None, max_length=NOTES_MAX)


class ExportScore(BaseModel):
    game_id: str = Field(min_length=1, max_length=255)
    score: int = Field(ge=1, le=100)


class ExportPrice(BaseModel):
    game_id: str = Field(min_length=1, max_length=255)
    platform: str = Field(min_length=1, max_length=255)
    amount_cents: int = Field(ge=0, le=1_000_000)


class ExportWish(BaseModel):
    game_id: str = Field(min_length=1, max_length=255)


class ExportFile(BaseModel):
    format: str
    version: int
    games: list[ExportGame] = Field(default=[], max_length=5000)
    platforms: list[ExportPlatform] = Field(default=[], max_length=200)
    library: list[ExportLibraryEntry] = Field(default=[], max_length=10000)
    sessions: list[ExportSession] = Field(default=[], max_length=50000)
    scores: list[ExportScore] = Field(default=[], max_length=5000)
    prices: list[ExportPrice] = Field(default=[], max_length=10000)
    wishlist: list[ExportWish] = Field(default=[], max_length=5000)
