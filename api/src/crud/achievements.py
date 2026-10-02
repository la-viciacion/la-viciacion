import datetime
import json
from typing import List, Union

from sqlalchemy import asc, create_engine, desc, func, select, text, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..config import Config
from ..crud import time_entries, users, games
from ..database import models, schemas
from ..utils import actions as actions
from ..utils import my_utils as utils
from ..utils.achievements import AchievementsElems
from ..utils.logger import LogManager
from ..utils import seasons

log_manager = LogManager()
logger = log_manager.get_logger()

config = Config()

E = AchievementsElems

# (achievement, needed): what a total has to reach to unlock each one
TOTAL_HOURS = (
    (E.PLAYED_100_HOURS, 100),
    (E.PLAYED_200_HOURS, 200),
    (E.PLAYED_500_HOURS, 500),
    (E.PLAYED_1000_HOURS, 1000),
)
HOURS_IN_A_DAY = (
    (E.PLAYED_4_HOURS_DAY, 4),
    (E.PLAYED_8_HOURS_DAY, 8),
    (E.PLAYED_12_HOURS_DAY, 12),
    (E.PLAYED_16_HOURS_DAY, 16),
)
TOTAL_DAYS = (
    (E.PLAYED_7_DAYS, 7),
    (E.PLAYED_15_DAYS, 15),
    (E.PLAYED_30_DAYS, 30),
    (E.PLAYED_60_DAYS, 60),
    (E.PLAYED_100_DAYS, 100),
    (E.PLAYED_200_DAYS, 200),
    (E.PLAYED_300_DAYS, 300),
    (E.PLAYED_365_DAYS, 365),
)
STREAKS = (
    (E.STREAK_7_DAYS, 7),
    (E.STREAK_15_DAYS, 15),
    (E.STREAK_30_DAYS, 30),
    (E.STREAK_60_DAYS, 60),
    (E.STREAK_100_DAYS, 100),
    (E.STREAK_200_DAYS, 200),
    (E.STREAK_300_DAYS, 300),
    (E.STREAK_365_DAYS, 365),
)
GAMES_IN_A_DAY = ((E.PLAYED_5_GAMES_DAY, 5), (E.PLAYED_10_GAMES_DAY, 10))
PLAYED_GAMES = (
    (E.PLAYED_10_GAMES, 10),
    (E.PLAYED_42_GAMES, 42),
    (E.PLAYED_50_GAMES, 50),
    (E.PLAYED_100_GAMES, 100),
)
COMPLETED_GAMES = ((E.COMPLETED_42_GAMES, 42), (E.COMPLETED_100_GAMES, 100))

######################
#### ACHIEVEMENTS ####
######################


class Achievements:
    def __init__(self, silent: bool = False) -> None:
        self.silent = silent

    def populate_achievements(self, db: Session):
        """Create the achievements of the code that the table does not have yet.

        Existing rows are left alone: from then on the database is the source of truth, so
        the title and message an admin edits (PATCH /manage/achievements) are kept.
        """
        existing = {key for (key,) in db.query(models.Achievement.key).all()}
        missing = [a for a in AchievementsElems if a.name not in existing]
        if not missing:
            return
        try:
            for achievement in missing:
                db.add(
                    models.Achievement(
                        key=achievement.name,
                        title=achievement.value["title"],
                        message=achievement.value["message"],
                    )
                )
            db.commit()
        except SQLAlchemyError as e:
            db.rollback()
            logger.error("Error adding achievements: " + str(e))

    def get_ach_by_key(self, db: Session, key: str):
        return (
            db.query(models.Achievement.id)
            .filter(models.Achievement.key == key)
            .first()
        )

    def upload_image(self, db: Session, key: str, image: bytes):
        try:
            stmt = (
                update(models.Achievement)
                .where(models.Achievement.key == key)
                .values(image=image)
            )
            db.execute(stmt)
            db.commit()
        except SQLAlchemyError as e:
            db.rollback()
            logger.error("Error adding image: " + str(e))
            raise

    def get_image(self, db: Session, key: str):
        try:
            return (
                db.query(models.Achievement.image)
                .filter(models.Achievement.key == key)
                .first()
            )
        except SQLAlchemyError as e:
            logger.error("Error getting image: " + str(e))
            raise

    def achieved_keys(self, db: Session, user_id: int, keys, season: int = None) -> set[str]:
        """Which of the achievements `keys` the user already has in the season: one query."""
        keys = [str(key) for key in keys]
        if not keys:
            return set()
        rows = (
            db.query(models.Achievement.key)
            .join(models.UserAchievement, models.UserAchievement.achievement_id == models.Achievement.id)
            .filter(
                models.UserAchievement.user_id == user_id,
                models.UserAchievement.season == seasons.or_current(season),
                models.Achievement.key.in_(keys),
            )
            .all()
        )
        return {key for (key,) in rows}

    def check_already_achieved(
        self, db: Session, user_id: int, key: str, season: int = None
    ) -> bool:
        return bool(self.achieved_keys(db, user_id, [key], season))

    def set_user_achievement(
        self,
        db: Session,
        user_id: int,
        key: str,
        game_id: str = None,
        date: str = None,
    ):
        # the season is derived from the date by the database
        if date is None:
            date = datetime.datetime.now()
        else:
            date = utils.convert_date_from_text(date)
        ach_id = self.get_ach_by_key(db, key)
        user_achievement = models.UserAchievement(
            user_id=user_id,
            achievement_id=ach_id[0],
            date=date,
            game_id=game_id,
        )
        db.add(user_achievement)
        db.commit()
        # return

    ######################
    ##### ACH CHECKS #####
    ######################

    async def _award(
        self,
        db: Session,
        user: models.User,
        ach: AchievementsElems,
        silent: bool,
        date: str = None,
        game_id: str = None,
    ):
        """Store an unlocked achievement and announce it. `game_id` also names the game in the message."""
        logger.info("Set achievement " + ach.name)
        self.set_user_achievement(db, user.id, ach.name, game_id, date)
        msg = utils.get_ach_message(ach, user=user.name, db=db, game_id=game_id)
        await utils.send_message(msg, silent, image=self.get_image(db, ach.name)[0])

    async def _unlock_reached(
        self,
        db: Session,
        user: models.User,
        value: float,
        thresholds: tuple,
        silent: bool,
        date_for=lambda needed: None,
    ):
        """Unlock every achievement of `thresholds` ((achievement, needed) pairs) that `value` reaches.

        `date_for(needed)` gives the date it was earned (default: now)."""
        reached = [(ach, needed) for ach, needed in thresholds if value >= needed]
        if not reached:
            return  # the common case costs no query at all
        have = self.achieved_keys(db, user.id, [ach.name for ach, _ in reached])
        for ach, needed in reached:
            if ach.name not in have:
                await self._award(db, user, ach, silent, date=date_for(needed))

    async def _unlock_if_new(
        self,
        db: Session,
        user: models.User,
        ach: AchievementsElems,
        silent: bool,
        date: str = None,
        game_id: str = None,
    ) -> bool:
        """Unlock one achievement unless the user already has it; True if it did."""
        if self.check_already_achieved(db, user.id, ach.name):
            return False
        await self._award(db, user, ach, silent, date=date, game_id=game_id)
        return True

    async def user_played_total_time(
        self,
        db: Session,
        user: models.User,
        played_time: int,
        date: str = None,
        silent: bool = False,
    ):
        if played_time is None:
            return
        await self._unlock_reached(
            db, user, played_time / 60 / 60, TOTAL_HOURS, silent, date_for=lambda needed: date
        )

    async def _unlock_first_day_reaching(
        self,
        db: Session,
        user: models.User,
        days: list,
        thresholds: tuple,
        silent: bool,
    ):
        """`days` is (date, value) rows: unlock each achievement of `thresholds` that has not been
        earned yet, dated the first day whose value reaches it. One query, however many days there are."""
        have = self.achieved_keys(db, user.id, [ach.name for ach, _ in thresholds])
        days = sorted((day, value) for day, value in days if value is not None)
        for ach, needed in thresholds:
            if ach.name in have:
                continue
            first = next((day for day, value in days if value >= needed), None)
            if first is not None:
                await self._award(db, user, ach, silent, date=str(first))

    async def user_played_day_time(
        self,
        db: Session,
        user: models.User,
        silent: bool = False,
    ):
        days = [
            (day, seconds / 60 / 60 if seconds is not None else None)
            for day, seconds in time_entries.get_played_time_by_day(db, user.id)
        ]
        await self._unlock_first_day_reaching(db, user, days, HOURS_IN_A_DAY, silent)

    async def user_session_time(
        self, db: Session, user: models.User, silent: bool = False
    ):
        have = self.achieved_keys(
            db,
            user.id,
            [
                AchievementsElems.PLAYED_LESS_5_MIN_SESSION.name,
                AchievementsElems.PLAYED_4_HOURS_SESSION.name,
                AchievementsElems.PLAYED_8_HOURS_SESSION.name,
            ],
        )
        # -5 min
        if AchievementsElems.PLAYED_LESS_5_MIN_SESSION.name not in have:
            entry = time_entries.get_time_entry_by_time(db, user.id, 5 * 60, 2)
            if entry is not None:
                await self._award(
                    db, user, AchievementsElems.PLAYED_LESS_5_MIN_SESSION, silent,
                    date=str(entry.start), game_id=entry.game_id,
                )
        # +4 and +8 hours
        for ach, hours in (
            (AchievementsElems.PLAYED_4_HOURS_SESSION, 4),
            (AchievementsElems.PLAYED_8_HOURS_SESSION, 8),
        ):
            if ach.name not in have:
                entry = time_entries.get_time_entry_by_time(db, user.id, hours * 60 * 60, 3)
                if entry is not None:
                    await self._award(db, user, ach, silent, date=str(entry.start), game_id=entry.game_id)

    async def user_played_total_days(
        self, db: Session, user: models.User, total_days: list, silent: bool = False
    ):
        await self._unlock_reached(
            db, user, len(total_days), TOTAL_DAYS, silent,
            date_for=lambda needed: str(total_days[needed - 1]),
        )

    async def user_played_hours_game_day(
        self, db: Session, user: models.User, silent: bool = False
    ):
        ach = AchievementsElems.PLAYED_8_HOURS_GAME_DAY
        if self.check_already_achieved(db, user.id, ach.name):
            return
        for date, game_id, duration in time_entries.get_played_time_by_game_and_day(db, user.id):
            if duration is None or game_id is None:
                continue
            if duration / 60 / 60 >= 8:
                await self._award(db, user, ach, silent, date=str(date), game_id=game_id)
                return

    async def user_played_games_per_day(
        self, db: Session, user: models.User, silent: bool = False
    ):
        days = time_entries.get_played_games_count_by_day(db, user.id)
        await self._unlock_first_day_reaching(db, user, [tuple(row) for row in days], GAMES_IN_A_DAY, silent)

    async def user_played_total_games(
        self, db: Session, user: models.User, date: str = None, silent: bool = False
    ):
        played_games = users.count_played_games(db, user.id)  # distinct games
        await self._unlock_reached(db, user, played_games, PLAYED_GAMES, silent)

    async def user_completed_total_games(
        self, db: Session, user: models.User, silent: bool = False
    ):
        await self._unlock_reached(
            db, user, users.count_completed_games(db, user.id), COMPLETED_GAMES, silent
        )

    async def user_played_hours_game(
        self,
        db: Session,
        user: models.User,
        game_id: str,
        played_time: int,
        date: str = None,
        silent: bool = False,
    ):
        # only 100 h per game is active: the 500 h and 1000 h achievements exist but are not awarded yet
        if int(played_time / 60 / 60) >= 100:
            await self._unlock_if_new(
                db, user, AchievementsElems.PLAYED_100_HOURS_GAME, silent, game_id=game_id
            )

    async def happy_new_year(
        self,
        db: Session,
        user: models.User,
        silent: bool = False,
        season: int = None,
    ):
        new_year = str(seasons.or_current(season)) + "-01-01"
        entries = time_entries.get_time_entry_by_date(db, user.id, new_year, 1)
        if len(entries) > 0:
            await self._unlock_if_new(
                db, user, AchievementsElems.HAPPY_NEW_YEAR, silent, date=str(entries[0].start)
            )

    async def user_streak(
        self,
        db: Session,
        user: models.User,
        streak: int,
        date: datetime.datetime = None,
        silent: bool = False,
    ):
        if date is not None:
            date = date.strftime("%Y-%m-%d %H:%M:%S")
        await self._unlock_reached(db, user, streak, STREAKS, silent, date_for=lambda needed: date)

    async def teamwork(self, db: Session, silent: bool):
        active = time_entries.active_timer_user_ids(db)
        playing: List[models.User] = [user for user in users.get_users(db) if user.id in active]
        if len(playing) < 4:
            return
        logger.info("4 or more users are playing!")
        ach = AchievementsElems.TEAMWORK
        someone_not_achieved = False
        for player in playing:
            if not self.check_already_achieved(db, player.id, ach.name):
                someone_not_achieved = True
                logger.info("Set 'Teamwork' achievement for " + player.name)
                self.set_user_achievement(db, player.id, ach.name)
        if not someone_not_achieved:
            logger.info("All users unlocked this achievement")
            return
        # "Ana, Bob y Cris"
        names = ", ".join(player.name for player in playing).rsplit(",", 1)
        msg = utils.get_ach_message(ach, user=" y".join(names))
        await utils.send_message(msg, silent, image=self.get_image(db, ach.name)[0])

    async def timer_started(
        self, db: Session, user: models.User, start_time: datetime.datetime, silent: bool = False
    ):
        """Achievements decided by the moment a timer starts (early riser, nocturnal)."""
        for ach, first_hour, last_hour in (
            (AchievementsElems.EARLY_RISER, 5, 6),
            (AchievementsElems.NOCTURNAL, 2, 5),
        ):
            if first_hour <= start_time.hour < last_hour:
                await self._unlock_if_new(db, user, ach, silent, date=str(start_time))

    async def early_riser(self, db: Session, user: models.User, silent: bool):
        entries = time_entries.get_time_entry_between_hours(db, user.id, start_hour=5, end_hour=6)
        if len(entries) > 0:
            await self._unlock_if_new(
                db, user, AchievementsElems.EARLY_RISER, silent, date=str(entries[0].start)
            )

    async def nocturnal(self, db: Session, user: models.User, silent: bool):
        entries = time_entries.get_time_entry_between_hours(db, user.id, start_hour=2, end_hour=5)
        if len(entries) > 0:
            await self._unlock_if_new(
                db, user, AchievementsElems.NOCTURNAL, silent, date=str(entries[0].start)
            )

    def get_weekly_achievements(
        self, db: Session, user: models.User, weeks_ago: int = 0
    ):
        """Rows with (number of achievements unlocked that week,); 0 = this week, 1 = last week..."""
        first_day, last_day = utils.get_week_range_dates(weeks_ago)
        return (
            db.query(func.count(models.UserAchievement.id))
            .filter(models.UserAchievement.user_id == user.id)
            .filter(func.DATE(models.UserAchievement.date) >= first_day)
            .filter(func.DATE(models.UserAchievement.date) <= last_day)
            .all()
        )

    async def just_in_time(
        self,
        db: Session,
        user: models.User,
        played_time: int,
        avg_time: int,
        game_id: str,
        date: str = None,
        silent: bool = False,
    ):
        if not played_time or not avg_time:
            return
        # Both played_time and avg_time (HLTB comp_main) are in seconds;
        # matched at hour granularity since an exact-second match is
        # practically unreachable and everything else in the app buckets
        # played time into hours anyway.
        if round(played_time / 3600) == round(avg_time / 3600):
            await self._unlock_if_new(
                db, user, AchievementsElems.JUST_IN_TIME, silent, date=date, game_id=game_id
            )
