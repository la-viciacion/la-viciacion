import datetime
import json
from typing import List, NamedTuple, Union

from sqlalchemy import and_, asc, create_engine, desc, func, or_, select, text, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..config import Config
from ..crud import time_entries, users, games
from ..database import models, schemas
from ..utils import actions as actions
from ..utils import my_utils as utils
from ..utils.achievements import SPECIAL_EMOJI, AchievementsElems, first_season, is_lifetime
from ..utils.logger import LogManager
from ..utils import seasons, streaks

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
COMPLETED_GAMES = (
    (E.COMPLETED_1_GAME, 1),
    (E.COMPLETED_5_GAMES, 5),
    (E.COMPLETED_10_GAMES, 10),
    (E.COMPLETED_25_GAMES, 25),
    (E.COMPLETED_42_GAMES, 42),
    (E.COMPLETED_100_GAMES, 100),
)
# The achievements with no season limit (their key ends in _LIFETIME): the same families, over the whole history.
# A check looks at one table or the other according to its season: the running one, or seasons.ALL.
LIFETIME_TOTAL_HOURS = (
    (E.PLAYED_500_HOURS_LIFETIME, 500),
    (E.PLAYED_1000_HOURS_LIFETIME, 1000),
    (E.PLAYED_2000_HOURS_LIFETIME, 2000),
    (E.PLAYED_5000_HOURS_LIFETIME, 5000),
    (E.PLAYED_10000_HOURS_LIFETIME, 10000),
)
LIFETIME_TOTAL_DAYS = (
    (E.PLAYED_100_DAYS_LIFETIME, 100),
    (E.PLAYED_200_DAYS_LIFETIME, 200),
    (E.PLAYED_500_DAYS_LIFETIME, 500),
    (E.PLAYED_1000_DAYS_LIFETIME, 1000),
    (E.PLAYED_2000_DAYS_LIFETIME, 2000),
    (E.PLAYED_5000_DAYS_LIFETIME, 5000),
)
LIFETIME_PLAYED_GAMES = (
    (E.PLAYED_100_GAMES_LIFETIME, 100),
    (E.PLAYED_200_GAMES_LIFETIME, 200),
    (E.PLAYED_500_GAMES_LIFETIME, 500),
    (E.PLAYED_1000_GAMES_LIFETIME, 1000),
)
LIFETIME_COMPLETED_GAMES = (
    (E.COMPLETED_100_GAMES_LIFETIME, 100),
    (E.COMPLETED_200_GAMES_LIFETIME, 200),
    (E.COMPLETED_500_GAMES_LIFETIME, 500),
    (E.COMPLETED_1000_GAMES_LIFETIME, 1000),
)
LIFETIME_HOURS_IN_A_GAME = ((E.PLAYED_1000_HOURS_GAME_LIFETIME, 1000),)
# "El hijo pródigo": days without playing, "Semana laboral": hours in a week, "Todos a una": players on a game
PRODIGAL_GAP_DAYS = 30
WORK_WEEK_HOURS = 40
ALL_TOGETHER_PLAYERS = 3
HOURS_IN_A_GAME = (
    (E.PLAYED_100_HOURS_GAME, 100),
    (E.PLAYED_500_HOURS_GAME, 500),
    (E.PLAYED_1000_HOURS_GAME, 1000),
)
# "Lo he abierto sin querer": a timer that was stopped within this many seconds
OPENED_BY_MISTAKE_SECONDS = 5 * 60
# "Justo a tiempo": the time played has to be this close (a fraction of it) to the HLTB average
JUST_IN_TIME_TOLERANCE = 0.05

######################
#### ACHIEVEMENTS ####
######################


class Award(NamedTuple):
    """An achievement a recalculation says a user deserves in a season."""

    user_id: int
    key: str
    date: datetime.date
    game_id: str | None


class Achievements:
    """The checks of every achievement.

    `season` (default: the running one) is the season they look at. An achievement that is not valid in it yet
    (`valid_from_season`) is not awarded. Over every season (seasons.ALL, see `lifetime_views`) `since` is the
    season the history counts from. With `collected` (a list) they only
    work out what a user deserves: each achievement is appended to the list as an `Award`, and nothing is
    written or announced, whatever `silent` says. That is how a recalculation reuses the very rules of the
    live checks without being able to notify anybody.
    """

    def __init__(
        self, silent: bool = False, season: int | None = None, collected: list | None = None, since: int | None = None
    ) -> None:
        self.silent = silent
        self.season = season
        self.collected = collected
        self.since = since

    @property
    def lifetime(self) -> bool:
        """Is this the view over the whole history (see lifetime_views)?"""
        return self.season == seasons.ALL

    def lifetime_views(self, db: Session) -> list["Achievements"]:
        """The same checks over every season, for the achievements with no season limit (their key ends in
        _LIFETIME): only the families that add something up have a table of them. There is one view for each season
        that the switched-on ones that have started to count begin to count from (usually a single one), because
        only what was done from that season on counts for them. None, while none is switched on, so it costs
        nothing. What they find is earned once, and they share `collected` with this one."""
        starts = (
            db.query(models.Achievement.valid_from_season)
            .filter(
                models.Achievement.key.like("%\\_LIFETIME", escape="\\"),
                models.Achievement.active == True,  # noqa: E712
                models.Achievement.valid_from_season <= seasons.current(),
            )
            .distinct()
            .all()
        )
        return [
            Achievements(silent=self.silent, season=seasons.ALL, since=since, collected=self.collected)
            for (since,) in sorted(starts)
        ]

    def _not_in_effect(self, season: int):
        """The condition (SQL) of the achievements that this view does not award in `season`: the ones that are
        switched off, the ones that are not valid yet and, over every season, the ones that count from another
        season than this view's."""
        a = models.Achievement
        if season == seasons.ALL:
            return or_(a.active == False, a.valid_from_season != (self.since or 0), a.valid_from_season > seasons.current())  # noqa: E712
        return or_(a.active == False, a.valid_from_season > season)  # noqa: E712

    def populate_achievements(self, db: Session):
        """Create the achievements of the code that the table does not have yet.

        Existing rows are left alone: from then on the database is the source of truth, so
        the title and message an admin edits (PATCH /manage/achievements) and whether it is active are kept.
        A new one is active and valid from the season its definition says (`since`; the first season of the app
        when it says nothing): the season is what keeps it from counting before its time.
        A row whose key the code no longer has (an achievement that was dropped) is switched off, never deleted:
        nothing can earn it any more, and whoever already has it keeps it.
        """
        existing = {key for (key,) in db.query(models.Achievement.key).all()}
        missing = [a for a in AchievementsElems if a.name not in existing]
        dropped = existing - {a.name for a in AchievementsElems}
        if not missing and not dropped:
            return
        try:
            if dropped:
                db.query(models.Achievement).filter(models.Achievement.key.in_(dropped)).update(
                    {models.Achievement.active: False}, synchronize_session=False
                )
            for achievement in missing:
                db.add(
                    models.Achievement(
                        key=achievement.name,
                        title=achievement.value["title"],
                        message=achievement.value["message"],
                        valid_from_season=first_season(achievement),
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
        """Which of the achievements `keys` need no award for the user in the season: the ones they already have
        and the ones nobody earns now (switched off, or not valid yet in it). One query."""
        keys = [str(key) for key in keys]
        if not keys:
            return set()
        season = seasons.or_current(season if season is not None else self.season)
        if self.collected is not None:
            off = {key for (key,) in db.query(models.Achievement.key).filter(models.Achievement.key.in_(keys), self._not_in_effect(season))}
            return off | {award.key for award in self.collected if award.user_id == user_id and award.key in keys}
        # over every season (the achievements with no season limit) it is once in a lifetime, in any of them
        of_the_season = [] if season == seasons.ALL else [models.UserAchievement.season == season]
        rows = (
            db.query(models.Achievement.key)
            .outerjoin(
                models.UserAchievement,
                and_(
                    models.UserAchievement.achievement_id == models.Achievement.id,
                    models.UserAchievement.user_id == user_id,
                    *of_the_season,
                ),
            )
            .filter(
                models.Achievement.key.in_(keys),
                or_(models.UserAchievement.id.isnot(None), self._not_in_effect(season)),
            )
            .distinct()
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
        if self.collected is not None:
            self._collect(user.id, ach, date, game_id)
            return
        silent = silent or self.silent
        logger.info("Set achievement " + ach.name)
        self.set_user_achievement(db, user.id, ach.name, game_id, date)
        msg = utils.get_ach_message(ach, user=user.name, db=db, game_id=game_id)
        await self._announce(db, ach, [user], msg, silent, self.get_image(db, ach.name)[0])

    def _flags(self, db: Session, key: str) -> tuple[bool, int]:
        """(secret, special level) of an achievement."""
        secret, special = db.query(models.Achievement.secret, models.Achievement.special).filter(models.Achievement.key == key).one()
        return bool(secret), special or 0

    async def _announce(
        self, db: Session, ach: AchievementsElems, players: list, message: str, silent: bool, image=None
    ):
        """Tell the group that `players` unlocked `ach`, with `message`. A special one says so, and its level. A
        secret one does not say which: the group only hears that they unlocked a hidden achievement (no
        picture), and each player gets `message` privately, on every channel they have (Telegram if linked, push
        if they have a device)."""
        silent = silent or self.silent
        secret, special = self._flags(db, ach.name)
        if special in SPECIAL_EMOJI:
            emoji = SPECIAL_EMOJI[special]
            message = f"{emoji} Logro especial de nivel {special} {emoji}\n{message}"
        if not secret:
            await utils.send_message(message, silent, image=image)
            return
        names = [utils.escape_markdown(player.name) for player in players]
        who = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " y " + names[-1]  # "Ana, Bob y Cris"
        verb = "ha" if len(names) == 1 else "han"
        await utils.send_message(f"🏆 Logro oculto 🏆\n*{who}* {verb} desbloqueado un logro oculto.", silent)
        if not silent:
            for player in players:
                await utils.send_message_to_user(player.telegram_id, message, user_id=player.id)

    def _collect(self, user_id: int, ach: AchievementsElems, date: str | None, game_id: str | None):
        """Note what a user deserves. Its date is the one that sets the season, so it is kept inside the
        season it is worked out for."""
        if date is None:
            raise ValueError("a recalculation needs the date of every achievement: " + ach.name)
        day = utils.convert_date_from_text(date).date()
        if not self.lifetime:
            season = seasons.or_current(self.season)
            day = min(max(day, datetime.date(season, 1, 1)), datetime.date(season, 12, 31))
        self.collected.append(Award(user_id, ach.name, day, game_id))

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
        self, db: Session, user: models.User, silent: bool = False
    ):
        """Dated the day the season's running total of hours crossed each threshold (over every season, the
        running total of the whole history)."""
        total = 0
        running = []
        for day, seconds in time_entries.get_played_time_by_day(db, user.id, self.season, self.since):
            total += seconds or 0
            running.append((day, total / 60 / 60))
        await self._unlock_first_day_reaching(db, user, running, LIFETIME_TOTAL_HOURS if self.lifetime else TOTAL_HOURS, silent)

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
            for day, seconds in time_entries.get_played_time_by_day(db, user.id, self.season)
        ]
        await self._unlock_first_day_reaching(db, user, days, HOURS_IN_A_DAY, silent)

    async def user_session_time(
        self, db: Session, user: models.User, silent: bool = False
    ):
        have = self.achieved_keys(
            db,
            user.id,
            [
                AchievementsElems.PLAYED_4_HOURS_SESSION.name,
                AchievementsElems.PLAYED_8_HOURS_SESSION.name,
            ],
        )
        # +4 and +8 hours
        for ach, hours in (
            (AchievementsElems.PLAYED_4_HOURS_SESSION, 4),
            (AchievementsElems.PLAYED_8_HOURS_SESSION, 8),
        ):
            if ach.name not in have:
                entry = time_entries.get_time_entry_by_time(db, user.id, hours * 60 * 60, 3, self.season)
                if entry is not None:
                    await self._award(db, user, ach, silent, date=str(entry.start), game_id=entry.game_id)

    async def opened_by_mistake(
        self,
        db: Session,
        user: models.User,
        game_id: str,
        start_time: datetime.datetime,
        duration_seconds: int | None,
        silent: bool = False,
    ):
        """A timer that was stopped within 5 minutes. Only a real timer earns it, so it is judged when
        the timer stops and never in the general check: a manual session or an edit cannot tell."""
        if duration_seconds is None or not 0 < duration_seconds <= OPENED_BY_MISTAKE_SECONDS:
            return
        await self._unlock_if_new(
            db, user, AchievementsElems.PLAYED_LESS_5_MIN_SESSION, silent, date=str(start_time), game_id=game_id
        )

    async def opened_by_mistake_from_sessions(self, db: Session, user: models.User, silent: bool = False):
        """The same achievement worked out from the sessions of the season, for a recalculation: the
        database cannot tell a timer that was really stopped from a manual session, so any session of 5
        minutes or less (and more than 0 s) earns it, the earliest one naming its game."""
        entry = time_entries.get_time_entry_by_time(db, user.id, OPENED_BY_MISTAKE_SECONDS, 2, self.season)
        if entry is not None:
            await self._unlock_if_new(
                db, user, AchievementsElems.PLAYED_LESS_5_MIN_SESSION, silent,
                date=str(entry.start), game_id=entry.game_id,
            )

    async def just_in_time_of_the_season(self, db: Session, user: models.User, silent: bool = False):
        """The games completed in the season, in order, against the average time stored for each game
        (a recalculation does not ask HLTB again)."""
        for day, game_id in users.completed_entries(db, user.id, self.season):
            played = sum(
                seconds or 0
                for _, seconds in time_entries.get_user_games_played_time(db, user.id, game_id, self.season)
            )
            game = games.get_game_by_id(db, game_id)
            await self.just_in_time(db, user, played, game.avg_time if game else None, game_id, date=str(day), silent=silent)

    async def prodigal_son(self, db: Session, user: models.User, played_days: list, silent: bool = False):
        """Back after 30 days or more without playing, inside the season. Dated the day they came back."""
        for before, after in zip(played_days, played_days[1:]):
            if (after - before).days - 1 >= PRODIGAL_GAP_DAYS:
                await self._unlock_if_new(db, user, AchievementsElems.PRODIGAL_SON, silent, date=str(after))
                return

    async def work_week(self, db: Session, user: models.User, silent: bool = False):
        """40 hours in one week (Monday to Sunday), each session counting for the day it began on. Dated
        the day the week got to them."""
        ach = AchievementsElems.WORK_WEEK
        if self.check_already_achieved(db, user.id, ach.name):
            return
        weeks: dict[datetime.date, int] = {}
        for day, seconds in time_entries.get_played_time_by_day(db, user.id, self.season):  # oldest first
            day = day if isinstance(day, datetime.date) else datetime.date.fromisoformat(day)
            monday = day - datetime.timedelta(days=day.weekday())
            weeks[monday] = weeks.get(monday, 0) + (seconds or 0)
            if weeks[monday] / 60 / 60 >= WORK_WEEK_HOURS:
                await self._award(db, user, ach, silent, date=str(day))
                return

    async def saved_by_the_bell(self, db: Session, user: models.User, silent: bool = False):
        """A session that was running when the year changed (31 December into 1 January). It belongs to the
        previous season by its start, so the achievement is dated 1 January: that is what sets its season."""
        new_year = datetime.datetime(seasons.or_current(self.season), 1, 1)
        entry = time_entries.get_first_time_entry_across(db, user.id, new_year)
        if entry is not None:
            await self._unlock_if_new(
                db, user, AchievementsElems.SAVED_BY_THE_BELL, silent, date=str(new_year), game_id=entry.game_id
            )

    async def completed_in_a_day(self, db: Session, user: models.User, silent: bool = False):
        """A game completed in a season whose sessions all began on the same day: the earliest one, dated
        the day it was completed."""
        for day, game_id in users.completed_entries(db, user.id, self.season):
            if len(time_entries.get_game_session_days(db, user.id, game_id, self.season)) == 1:
                await self._unlock_if_new(
                    db, user, AchievementsElems.COMPLETED_IN_A_DAY, silent, date=str(day), game_id=game_id
                )
                return

    async def release_day(self, db: Session, user: models.User, silent: bool = False):
        """A session of a game that began on the day the game came out (wished or not)."""
        entry = time_entries.get_first_time_entry_on_release_day(db, user.id, self.season)
        if entry is not None:
            await self._unlock_if_new(
                db, user, AchievementsElems.RELEASE_DAY, silent, date=str(entry.start), game_id=entry.game_id
            )

    async def all_together(self, db: Session, game_id: str, silent: bool = False):
        """Three or more players with a timer running on the same game: unlocked for every one of them, with
        one message. It is judged when a timer starts (the third player's), so only real timers count."""
        running = time_entries.active_timer_user_ids_of_game(db, game_id)
        playing: List[models.User] = [user for user in users.get_users(db) if user.id in running]
        if len(playing) < ALL_TOGETHER_PLAYERS:
            return
        ach = AchievementsElems.ALL_TOGETHER
        new = [player for player in playing if not self.check_already_achieved(db, player.id, ach.name)]
        if not new:
            return
        for player in new:
            logger.info("Set 'All together' achievement for " + player.name)
            self.set_user_achievement(db, player.id, ach.name, game_id)
        # "Ana, Bob y Cris"
        names = ", ".join(player.name for player in playing).rsplit(",", 1)
        msg = utils.get_ach_message(ach, user=" y".join(names), db=db, game_id=game_id)
        await self._announce(db, ach, new, msg, silent, self.get_image(db, ach.name)[0])

    async def user_played_total_days(
        self, db: Session, user: models.User, total_days: list, silent: bool = False
    ):
        await self._unlock_reached(
            db, user, len(total_days), LIFETIME_TOTAL_DAYS if self.lifetime else TOTAL_DAYS, silent,
            date_for=lambda needed: str(total_days[needed - 1]),
        )

    async def user_played_hours_game_day(
        self, db: Session, user: models.User, silent: bool = False
    ):
        ach = AchievementsElems.PLAYED_8_HOURS_GAME_DAY
        if self.check_already_achieved(db, user.id, ach.name):
            return
        # the first day it happened, whatever order the database returns the days in
        reached = [
            (date, game_id)
            for date, game_id, duration in time_entries.get_played_time_by_game_and_day(db, user.id, self.season)
            if duration is not None and game_id is not None and duration / 60 / 60 >= 8
        ]
        if reached:
            date, game_id = min(reached)
            await self._award(db, user, ach, silent, date=str(date), game_id=game_id)

    async def user_played_games_per_day(
        self, db: Session, user: models.User, silent: bool = False
    ):
        days = time_entries.get_played_games_count_by_day(db, user.id, self.season)
        await self._unlock_first_day_reaching(db, user, [tuple(row) for row in days], GAMES_IN_A_DAY, silent)

    async def user_played_total_games(
        self, db: Session, user: models.User, silent: bool = False
    ):
        """Distinct games of the season (of every season, in the view of the whole history), dated the day the
        Nth one began."""
        dates = users.played_game_dates(db, user.id, self.season, self.since)
        await self._unlock_reached(
            db, user, len(dates), LIFETIME_PLAYED_GAMES if self.lifetime else PLAYED_GAMES, silent,
            date_for=lambda needed: str(dates[needed - 1]),
        )

    async def user_completed_total_games(
        self, db: Session, user: models.User, silent: bool = False
    ):
        """Dated the day the Nth game was completed (over every season, a game counts once)."""
        dates = users.completed_game_dates(db, user.id, self.season, self.since)
        await self._unlock_reached(
            db, user, len(dates), LIFETIME_COMPLETED_GAMES if self.lifetime else COMPLETED_GAMES, silent,
            date_for=lambda needed: str(dates[needed - 1]),
        )

    async def user_played_hours_game(
        self, db: Session, user: models.User, silent: bool = False
    ):
        """100, 500 and 1000 h in one game this season, each dated the day it crossed them. With several
        games over a line, the one that crossed first is the one named. Over every season, the hours of a game
        are all the ones it has had."""
        table = LIFETIME_HOURS_IN_A_GAME if self.lifetime else HOURS_IN_A_GAME
        have = self.achieved_keys(db, user.id, [ach.name for ach, _ in table])
        pending = [(ach, hours) for ach, hours in table if ach.name not in have]
        if not pending:
            return
        totals: dict[str, float] = {}
        first: dict[int, tuple] = {}  # hours -> (day it crossed, game_id)
        for day, game_id, seconds in sorted(
            (row for row in time_entries.get_played_time_by_game_and_day(db, user.id, self.season, self.since) if row[1] is not None),
            key=lambda row: row[0],
        ):
            totals[game_id] = totals.get(game_id, 0) + (seconds or 0)
            for _, hours in pending:
                if totals[game_id] / 60 / 60 >= hours and (hours not in first or (day, game_id) < first[hours]):
                    first[hours] = (day, game_id)
        for ach, hours in pending:
            if hours in first:
                day, game_id = first[hours]
                await self._award(db, user, ach, silent, date=str(day), game_id=game_id)

    async def happy_new_year(
        self,
        db: Session,
        user: models.User,
        silent: bool = False,
        season: int = None,
    ):
        new_year = datetime.datetime(seasons.or_current(season if season is not None else self.season), 1, 1)
        entry = time_entries.get_first_time_entry_on_day(db, user.id, new_year.date())
        if entry is not None:
            # a session that began on 31 December is dated 1 January: the date is what sets the season,
            # and an achievement of the previous season would never be seen as earned in this one
            earned = max(entry.start, new_year)
            await self._unlock_if_new(
                db, user, AchievementsElems.HAPPY_NEW_YEAR, silent, date=str(earned)
            )

    async def user_streak(
        self, db: Session, user: models.User, played_days: list, silent: bool = False
    ):
        """`played_days` of the season, oldest first. Each streak is dated the day a run got to its length."""
        reached = streaks.streak_reach_dates(played_days, [needed for _, needed in STREAKS])
        if not reached:
            return  # the common case costs no query at all
        have = self.achieved_keys(db, user.id, [ach.name for ach, needed in STREAKS if needed in reached])
        for ach, needed in STREAKS:
            if needed in reached and ach.name not in have:
                await self._award(db, user, ach, silent, date=str(reached[needed]))

    async def teamwork(self, db: Session, silent: bool):
        active = time_entries.active_timer_user_ids(db)
        playing: List[models.User] = [user for user in users.get_users(db) if user.id in active]
        if len(playing) < 4:
            return
        logger.info("4 or more users are playing!")
        ach = AchievementsElems.TEAMWORK
        new = []
        for player in playing:
            if not self.check_already_achieved(db, player.id, ach.name):
                new.append(player)
                logger.info("Set 'Teamwork' achievement for " + player.name)
                self.set_user_achievement(db, player.id, ach.name)
        if not new:
            logger.info("All users unlocked this achievement")
            return
        # "Ana, Bob y Cris"
        names = ", ".join(player.name for player in playing).rsplit(",", 1)
        msg = utils.get_ach_message(ach, user=" y".join(names))
        await self._announce(db, ach, new, msg, silent, self.get_image(db, ach.name)[0])

    async def timer_started(
        self,
        db: Session,
        user: models.User,
        start_time: datetime.datetime,
        game_id: str | None = None,
        silent: bool = False,
    ):
        """Achievements decided by the moment a timer starts (early riser, nocturnal, new year and playing
        a game on its release day)."""
        for ach, first_hour, last_hour in (
            (AchievementsElems.EARLY_RISER, 5, 6),
            (AchievementsElems.NOCTURNAL, 2, 5),
        ):
            if first_hour <= start_time.hour < last_hour:
                await self._unlock_if_new(db, user, ach, silent, date=str(start_time))
        if (start_time.month, start_time.day) == (1, 1):
            await self._unlock_if_new(db, user, AchievementsElems.HAPPY_NEW_YEAR, silent, date=str(start_time))
        game = games.get_game_by_id(db, game_id) if game_id else None
        if game is not None and game.release_date == start_time.date():
            await self._unlock_if_new(
                db, user, AchievementsElems.RELEASE_DAY, silent, date=str(start_time), game_id=game_id
            )

    async def early_riser(self, db: Session, user: models.User, silent: bool):
        entry = time_entries.get_first_time_entry_between_hours(db, user.id, 5, 6, self.season)
        if entry is not None:
            await self._unlock_if_new(
                db, user, AchievementsElems.EARLY_RISER, silent, date=str(entry.start)
            )

    async def nocturnal(self, db: Session, user: models.User, silent: bool):
        entry = time_entries.get_first_time_entry_between_hours(db, user.id, 2, 5, self.season)
        if entry is not None:
            await self._unlock_if_new(
                db, user, AchievementsElems.NOCTURNAL, silent, date=str(entry.start)
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
        # Both played_time and avg_time (HLTB comp_main) are in seconds. An exact match is
        # unreachable, so it is enough to be within a few percent of the average.
        if abs(played_time - avg_time) <= avg_time * JUST_IN_TIME_TOLERANCE:
            await self._unlock_if_new(
                db, user, AchievementsElems.JUST_IN_TIME, silent, date=date, game_id=game_id
            )
