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
from ..utils.clockify_api import ClockifyApi
from ..utils.logger import LogManager

log_manager = LogManager()
logger = log_manager.get_logger()

clockify = ClockifyApi()
config = Config()

######################
#### ACHIEVEMENTS ####
######################


class Achievements:
    from ..utils.achievements import AchievementsElems
    season = datetime.datetime.now().year

    def __init__(self, silent: bool = False) -> None:
        self.silent = silent

    def populate_achievements(self, db: Session):
        # logger.debug("Populating achievements")
        for achievement in list(AchievementsElems):
            key = achievement.name
            title = achievement.value["title"]
            message = achievement.value["message"]
            ach_db = (
                db.query(models.Achievement)
                .filter(models.Achievement.key == key)
                .first()
            )
            if ach_db is None:
                try:
                    achievement = models.Achievement(
                        key=key, title=title, message=message
                    )
                    db.add(achievement)
                    db.commit()
                    # db.refresh(achievement)
                except SQLAlchemyError as e:
                    db.rollback()
                    logger.error("Error adding achievement: " + str(e))
            else:
                # logger.info("Updating achievement")
                stmt = (
                    update(models.Achievement)
                    .where(models.Achievement.key == key)
                    .values(title=title, message=message)
                )
                db.execute(stmt)
                db.commit()
            # print(achievement, "->", achievement.value)

    def get_achievements_list(self, db: Session) -> list[models.Achievement]:
        return db.query(models.Achievement)

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

    def check_already_achieved(
        self, db: Session, user_id: int, key: str, season: int = season
    ) -> bool:
        ach_id = self.get_ach_by_key(db, str(key))
        already_achieved = (
            db.query(models.UserAchievement)
            .filter(
                models.UserAchievement.user_id == user_id,
                models.UserAchievement.achievement_id == ach_id[0],
                models.UserAchievement.season == season,
            )
            .first()
        )
        if already_achieved is None:
            return False
        return True

    def set_user_achievement(
        self,
        db: Session,
        user_id: int,
        key: str,
        game_id: str = None,
        date: str = None,
        season: int = season,
    ):
        if date is None:
            date = datetime.datetime.now()
        else:
            date = utils.convert_date_from_text(date)
        ach_id = self.get_ach_by_key(db, key)
        user_achievement = models.UserAchievement(
            user_id=user_id,
            achievement_id=ach_id[0],
            season=season,
            date=date,
            game_id=game_id,
        )
        db.add(user_achievement)
        db.commit()
        # return

    ######################
    ##### ACH CHECKS #####
    ######################

    async def user_played_total_time(
        self,
        db: Session,
        user: models.User,
        played_time: int,
        date: str = None,
        silent: bool = False,
    ):
        # logger.debug("Check total played time achievements...")
        if played_time is None:
            return
        played_time = played_time / 60 / 60
        # To create messages, use the follow example, and adapt to every message
        # user = user.name
        # msg = AchievementsElems.PLAYED_100_HOURS.value["message"].format(name)
        # 100 h
        # logger.info("Check total played time achievements")
        ach = AchievementsElems.PLAYED_100_HOURS
        if played_time >= 100 and not self.check_already_achieved(
            db, user.id, ach.name
        ):
            logger.info("Set achievement 100h")
            self.set_user_achievement(db, user.id, ach.name, date)
            msg = utils.get_ach_message(ach, user=user.name)
            await utils.send_message(
                msg,
                silent,
                image=self.get_image(db, ach.name)[0],
            )

        # 200 h
        ach = AchievementsElems.PLAYED_200_HOURS
        if played_time >= 200 and not self.check_already_achieved(
            db, user.id, ach.name
        ):
            logger.info("Set achievement 200h")
            self.set_user_achievement(db, user.id, ach.name, date)
            msg = utils.get_ach_message(ach, user=user.name)
            await utils.send_message(
                msg,
                silent,
                image=self.get_image(db, ach.name)[0],
            )

        # 500 h
        ach = AchievementsElems.PLAYED_500_HOURS
        if played_time >= 500 and not self.check_already_achieved(
            db, user.id, ach.name
        ):
            logger.info("Set achievement 500h")
            self.set_user_achievement(db, user.id, ach.name, date)
            msg = utils.get_ach_message(ach, user=user.name)
            await utils.send_message(
                msg,
                silent,
                image=self.get_image(db, ach.name)[0],
            )

        # 1000 h
        ach = AchievementsElems.PLAYED_1000_HOURS
        if played_time >= 1000 and not self.check_already_achieved(
            db, user.id, ach.name
        ):
            logger.info("Set achievement 1000h")
            self.set_user_achievement(db, user.id, ach.name, date)
            msg = utils.get_ach_message(ach, user=user.name)
            await utils.send_message(
                msg,
                silent,
                image=self.get_image(db, ach.name)[0],
            )

    async def user_played_day_time(
        self,
        db: Session,
        user: models.User,
        silent: bool = False,
    ):
        # logger.debug("Check played time in one day achievements...")
        played_days = time_entries.get_played_time_by_day(db, user.id)
        for played_day in played_days:
            date = str(played_day[0])
            if played_day[1] is None:
                continue
            played_time = played_day[1] / 60 / 60
            # 4 hours
            ach = AchievementsElems.PLAYED_4_HOURS_DAY
            if played_time >= 4 and not self.check_already_achieved(
                db, user.id, ach.name
            ):
                logger.info("Set achievement 4 hours day")
                self.set_user_achievement(db, user.id, ach.name, date=date)
                msg = utils.get_ach_message(ach, user=user.name)
                await utils.send_message(
                    msg,
                    silent,
                    image=self.get_image(db, ach.name)[0],
                )

            # 8 hours
            ach = AchievementsElems.PLAYED_8_HOURS_DAY
            if played_time >= 8 and not self.check_already_achieved(
                db, user.id, ach.name
            ):
                logger.info("Set achievement 8 hours day")
                self.set_user_achievement(db, user.id, ach.name, date=date)
                msg = utils.get_ach_message(ach, user=user.name)
                await utils.send_message(
                    msg,
                    silent,
                    image=self.get_image(db, ach.name)[0],
                )

            # 12 hour
            ach = AchievementsElems.PLAYED_12_HOURS_DAY
            if played_time >= 12 and not self.check_already_achieved(
                db, user.id, ach.name
            ):
                logger.info("Set achievement 12 hours day")
                self.set_user_achievement(db, user.id, ach.name, date=date)
                msg = utils.get_ach_message(ach, user=user.name)
                await utils.send_message(
                    msg,
                    silent,
                    image=self.get_image(db, ach.name)[0],
                )

            # 16 hours
            ach = AchievementsElems.PLAYED_16_HOURS_DAY
            if played_time >= 16 and not self.check_already_achieved(
                db, user.id, ach.name
            ):
                logger.info("Set achievement 16 hours day")
                self.set_user_achievement(db, user.id, ach.name, date=date)
                msg = utils.get_ach_message(ach, user=user.name)
                await utils.send_message(
                    msg,
                    silent,
                    image=self.get_image(db, ach.name)[0],
                )

    async def user_session_time(
        self, db: Session, user: models.User, silent: bool = False
    ):
        # logger.debug("Check session played time achievements...")
        # -5 min
        ach = AchievementsElems.PLAYED_LESS_5_MIN_SESSION
        if not self.check_already_achieved(db, user.id, ach.name):
            time_entry = time_entries.get_time_entry_by_time(db, user.id, 5 * 60, 2)
            if time_entry is not None and time_entry.duration > 0:
                logger.info("Set achievement less 5 minutes session")
                self.set_user_achievement(
                    db,
                    user.id,
                    ach.name,
                    game_id=time_entry.project_clockify_id,
                    date=str(time_entry.start),
                )
                msg = utils.get_ach_message(
                    ach,
                    user=user.name,
                    db=db,
                    game_id=time_entry.project_clockify_id,
                )
                await utils.send_message(
                    msg,
                    silent,
                    image=self.get_image(db, ach.name)[0],
                )

        # +4 hours
        ach = AchievementsElems.PLAYED_4_HOURS_SESSION
        if not self.check_already_achieved(db, user.id, ach.name):
            time_entry = time_entries.get_time_entry_by_time(
                db, user.id, 4 * 60 * 60, 3
            )
            if time_entry is not None:
                logger.info("Set achievement 4 hours session")
                self.set_user_achievement(
                    db,
                    user.id,
                    ach.name,
                    game_id=time_entry.project_clockify_id,
                    date=str(time_entry.start),
                )
                msg = utils.get_ach_message(
                    ach,
                    user=user.name,
                    db=db,
                    game_id=time_entry.project_clockify_id,
                )
                await utils.send_message(
                    msg,
                    silent,
                    image=self.get_image(db, ach.name)[0],
                )

        # +8 hours
        ach = AchievementsElems.PLAYED_8_HOURS_SESSION
        if not self.check_already_achieved(db, user.id, ach.name):
            time_entry = time_entries.get_time_entry_by_time(
                db, user.id, 8 * 60 * 60, 3
            )
            if time_entry is not None:
                logger.info("Set achievement 8 hours session")
                self.set_user_achievement(
                    db,
                    user.id,
                    ach.name,
                    game_id=time_entry.project_clockify_id,
                    date=str(time_entry.start),
                )
                msg = utils.get_ach_message(
                    ach,
                    user=user.name,
                    db=db,
                    game_id=time_entry.project_clockify_id,
                )
                await utils.send_message(
                    msg,
                    silent,
                    image=self.get_image(db, ach.name)[0],
                )

    async def user_played_total_days(
        self, db: Session, user: models.User, total_days: list, silent: bool = False
    ):
        # logger.debug(
        #    "Check total played days achievements (" + str(len(total_days)) + ")..."
        # )
        # achieved_date = total_days[1]
        # 7 days
        ach = AchievementsElems.PLAYED_7_DAYS
        if len(total_days) >= 7 and not self.check_already_achieved(
            db, user.id, ach.name
        ):
            logger.info("Set achievement played 7 days")
            # logger.info(total_days[6])
            self.set_user_achievement(
                db,
                user.id,
                ach.name,
                date=str(total_days[6]),
            )
            msg = utils.get_ach_message(ach, user=user.name)
            await utils.send_message(
                msg,
                silent,
                image=self.get_image(db, ach.name)[0],
            )
        # 15 days
        ach = AchievementsElems.PLAYED_15_DAYS
        if len(total_days) >= 15 and not self.check_already_achieved(
            db, user.id, ach.name
        ):
            logger.info("Set achievement played 15 days")
            self.set_user_achievement(
                db,
                user.id,
                ach.name,
                date=str(total_days[14]),
            )
            msg = utils.get_ach_message(ach, user=user.name)
            await utils.send_message(
                msg,
                silent,
                image=self.get_image(db, ach.name)[0],
            )
        # 30 days
        ach = AchievementsElems.PLAYED_30_DAYS
        if len(total_days) >= 30 and not self.check_already_achieved(
            db, user.id, ach.name
        ):
            logger.info("Set achievement played 30 days")
            self.set_user_achievement(
                db,
                user.id,
                ach.name,
                date=str(total_days[29]),
            )
            msg = utils.get_ach_message(ach, user=user.name)
            await utils.send_message(
                msg,
                silent,
                image=self.get_image(db, ach.name)[0],
            )
        # 60 days
        ach = AchievementsElems.PLAYED_60_DAYS
        if len(total_days) >= 60 and not self.check_already_achieved(
            db, user.id, ach.name
        ):
            logger.info("Set achievement played 60 days")
            self.set_user_achievement(
                db,
                user.id,
                ach.name,
                date=str(total_days[59]),
            )
            msg = utils.get_ach_message(ach, user=user.name)
            await utils.send_message(
                msg,
                silent,
                image=self.get_image(db, ach.name)[0],
            )
        # 100 days
        ach = AchievementsElems.PLAYED_100_DAYS
        if len(total_days) >= 100 and not self.check_already_achieved(
            db, user.id, ach.name
        ):
            logger.info("Set achievement played 100 days")
            self.set_user_achievement(
                db,
                user.id,
                ach.name,
                date=str(total_days[99]),
            )
            msg = utils.get_ach_message(ach, user=user.name)
            await utils.send_message(
                msg,
                silent,
                image=self.get_image(db, ach.name)[0],
            )
        # 200 days
        ach = AchievementsElems.PLAYED_200_DAYS
        if len(total_days) >= 200 and not self.check_already_achieved(
            db, user.id, ach.name
        ):
            logger.info("Set achievement played 200 days")
            self.set_user_achievement(
                db,
                user.id,
                ach.name,
                date=str(total_days[199]),
            )
            msg = utils.get_ach_message(ach, user=user.name)
            await utils.send_message(
                msg,
                silent,
                image=self.get_image(db, ach.name)[0],
            )
        # 300 days
        ach = AchievementsElems.PLAYED_300_DAYS
        if len(total_days) >= 300 and not self.check_already_achieved(
            db, user.id, ach.name
        ):
            logger.info("Set achievement played 300 days")
            self.set_user_achievement(
                db,
                user.id,
                ach.name,
                date=str(total_days[299]),
            )
            msg = utils.get_ach_message(ach, user=user.name)
            await utils.send_message(
                msg,
                silent,
                image=self.get_image(db, ach.name)[0],
            )
        # 365 days
        ach = AchievementsElems.PLAYED_365_DAYS
        if len(total_days) >= 365 and not self.check_already_achieved(
            db, user.id, ach.name
        ):
            logger.info("Set achievement played 365 days")
            self.set_user_achievement(
                db,
                user.id,
                ach.name,
                date=str(total_days[364]),
            )
            msg = utils.get_ach_message(ach, user=user.name)
            await utils.send_message(
                msg,
                silent,
                image=self.get_image(db, ach.name)[0],
            )

    async def user_played_total_games(
        self, db: Session, user: models.User, date: str = None, silent: bool = False
    ):
        # logger.debug("Check total played games achievements...")
        played_games = users.get_games(db, user.id)
        # 10
        # logger.info("Played games for " + user.name + ": " + str(len(played_games)))
        ach = AchievementsElems.PLAYED_10_GAMES
        if len(played_games) >= 10 and not self.check_already_achieved(
            db, user.id, ach.name
        ):
            logger.info("Set achievement played 10 games")
            self.set_user_achievement(db, user.id, ach.name)
            msg = utils.get_ach_message(ach, user=user.name)
            await utils.send_message(
                msg,
                silent,
                image=self.get_image(db, ach.name)[0],
            )
        # 42
        ach = AchievementsElems.PLAYED_42_GAMES
        if len(played_games) >= 42 and not self.check_already_achieved(
            db, user.id, ach.name
        ):
            logger.info("Set achievement played 42 games")
            self.set_user_achievement(db, user.id, ach.name)
            msg = utils.get_ach_message(ach, user=user.name)
            await utils.send_message(
                msg,
                silent,
                image=self.get_image(db, ach.name)[0],
            )
        # 50
        ach = AchievementsElems.PLAYED_50_GAMES
        if len(played_games) >= 50 and not self.check_already_achieved(
            db, user.id, ach.name
        ):
            logger.info("Set achievement played 50 games")
            self.set_user_achievement(db, user.id, ach.name)
            msg = utils.get_ach_message(ach, user=user.name)
            await utils.send_message(
                msg,
                silent,
                image=self.get_image(db, ach.name)[0],
            )
        # 100
        ach = AchievementsElems.PLAYED_100_GAMES
        if len(played_games) >= 100 and not self.check_already_achieved(
            db, user.id, ach.name
        ):
            logger.info("Set achievement played 100 games")
            self.set_user_achievement(db, user.id, ach.name)
            msg = utils.get_ach_message(ach, user=user.name)
            await utils.send_message(
                msg,
                silent,
                image=self.get_image(db, ach.name)[0],
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
        played_time = int(played_time / 60 / 60)
        # 100 h
        ach = AchievementsElems.PLAYED_100_HOURS_GAME
        if played_time >= 100 and not self.check_already_achieved(
            db, user.id, ach.name
        ):
            game = games.get_game_by_id(db, game_id)
            logger.info(
                "Set achievement played 100 hours game: "
                + game.name
                + " ("
                + str(played_time)
                + ")"
            )
            self.set_user_achievement(db, user.id, ach.name, game_id)
            msg = utils.get_ach_message(ach=ach, user=user.name, db=db, game_id=game_id)
            await utils.send_message(
                msg,
                silent,
                image=self.get_image(db, ach.name)[0],
            )

        # The following are not activated yet
        # # 500 h
        # ach = AchievementsElems.PLAYED_500_HOURS_GAME
        # if played_time >= 500 and not self.check_already_achieved(
        #     db, user.id, ach.name
        # ):
        #     game = games.get_game_by_id(db, game_id)
        #     logger.info(
        #         "Set achievement played 500 hours game: "
        #         + game.name
        #         + " ("
        #         + str(played_time)
        #         + ")"
        #     )
        #     self.set_user_achievement(db, user.id, ach.name, game_id)
        #     msg = utils.get_ach_message(ach=ach, user=user.name, db=db, game_id=game_id)
        #     await utils.send_message(
        #         msg,
        #         silent,
        #         image=self.get_image(db, ach.name)[0],
        #     )

        # # 1000 h
        # ach = AchievementsElems.PLAYED_1000_HOURS_GAME
        # if played_time >= 1000 and not self.check_already_achieved(
        #     db, user.id, ach.name
        # ):
        #     game = games.get_game_by_id(db, game_id)
        #     logger.info(
        #         "Set achievement played 1000 hours game: "
        #         + game.name
        #         + " ("
        #         + str(played_time)
        #         + ")"
        #     )
        #     self.set_user_achievement(db, user.id, ach.name, game_id)
        #     msg = utils.get_ach_message(ach=ach, user=user.name, db=db, game_id=game_id)
        #     await utils.send_message(
        #         msg,
        #         silent,
        #         image=self.get_image(db, ach.name)[0],
        #     )
        return

    async def happy_new_year(
        self,
        db: Session,
        user: models.User,
        silent: bool = False,
        season: int = season,
    ):
        current_season = str(season)
        new_year = current_season + "-01-01"
        time_entry = time_entries.get_time_entry_by_date(db, user.id, new_year, 1)
        ach = AchievementsElems.HAPPY_NEW_YEAR
        if time_entry.count() > 0 and not self.check_already_achieved(
            db, user.id, ach.name
        ):
            logger.info("Set achievement happy new year")
            self.set_user_achievement(
                db,
                user.id,
                ach.name,
                date=str(time_entry[0].start),
            )
            msg = utils.get_ach_message(ach, user=user.name)
            await utils.send_message(
                msg,
                silent,
                image=self.get_image(db, ach.name)[0],
            )

    async def user_streak(
        self,
        db: Session,
        user: models.User,
        streak: int,
        date: datetime.datetime = None,
        silent: bool = False,
    ):
        # logger.debug("Check streaks achievements...")
        if date is not None:
            date = date.strftime("%Y-%m-%d %H:%M:%S")
        # 7 days
        ach = AchievementsElems.STREAK_7_DAYS
        if streak >= 7 and not self.check_already_achieved(db, user.id, ach.name):
            logger.info("Set achievement streak 7 days")
            self.set_user_achievement(db, user.id, ach.name, date=date)
            msg = utils.get_ach_message(ach, user=user.name)
            await utils.send_message(
                msg,
                silent,
                image=self.get_image(db, ach.name)[0],
            )
        # 15 days
        ach = AchievementsElems.STREAK_15_DAYS
        if streak >= 15 and not self.check_already_achieved(db, user.id, ach.name):
            logger.info("Set achievement streak 15 days")
            self.set_user_achievement(db, user.id, ach.name, date=date)
            msg = utils.get_ach_message(ach, user=user.name)
            await utils.send_message(
                msg,
                silent,
                image=self.get_image(db, ach.name)[0],
            )
        # 30 days
        ach = AchievementsElems.STREAK_30_DAYS
        if streak >= 30 and not self.check_already_achieved(db, user.id, ach.name):
            logger.info("Set achievement streak 30 days")
            self.set_user_achievement(db, user.id, ach.name, date=date)
            msg = utils.get_ach_message(ach, user=user.name)
            await utils.send_message(
                msg,
                silent,
                image=self.get_image(db, ach.name)[0],
            )
        # 60 days
        ach = AchievementsElems.STREAK_60_DAYS
        if streak >= 60 and not self.check_already_achieved(db, user.id, ach.name):
            logger.info("Set achievement streak 60 days")
            self.set_user_achievement(db, user.id, ach.name, date=date)
            msg = utils.get_ach_message(ach, user=user.name)
            await utils.send_message(
                msg,
                silent,
                image=self.get_image(db, ach.name)[0],
            )
        # 100 days
        ach = AchievementsElems.STREAK_100_DAYS
        if streak >= 100 and not self.check_already_achieved(db, user.id, ach.name):
            logger.info("Set achievement streak 100 days")
            self.set_user_achievement(db, user.id, ach.name, date=date)
            msg = utils.get_ach_message(ach, user=user.name)
            await utils.send_message(
                msg,
                silent,
                image=self.get_image(db, ach.name)[0],
            )
        # 200 days
        ach = AchievementsElems.STREAK_200_DAYS
        if streak >= 200 and not self.check_already_achieved(db, user.id, ach.name):
            logger.info("Set achievement streak 200 days")
            self.set_user_achievement(db, user.id, ach.name, date=date)
            msg = utils.get_ach_message(ach, user=user.name)
            await utils.send_message(
                msg,
                silent,
                image=self.get_image(db, ach.name)[0],
            )
        # 300 days
        ach = AchievementsElems.STREAK_300_DAYS
        if streak >= 300 and not self.check_already_achieved(db, user.id, ach.name):
            logger.info("Set achievement streak 300 days")
            self.set_user_achievement(db, user.id, ach.name, date=date)
            msg = utils.get_ach_message(ach, user=user.name)
            await utils.send_message(
                msg,
                silent,
                image=self.get_image(db, ach.name)[0],
            )
        # 365 days
        ach = AchievementsElems.STREAK_365_DAYS
        if streak >= 365 and not self.check_already_achieved(db, user.id, ach.name):
            logger.info("Set achievement streak 365 days")
            self.set_user_achievement(db, user.id, ach.name, date=date)
            msg = utils.get_ach_message(ach, user=user.name)
            await utils.send_message(
                msg,
                silent,
                image=self.get_image(db, ach.name)[0],
            )

    async def teamwork(self, db: Session, silent: bool):
        # logger.debug("Checking teamwork achievement...")
        user_list = users.get_users(db)
        playing: List[models.User] = []
        for user in user_list:
            has_active_time_entry = time_entries.get_active_time_entry_by_user(db, user)
            if has_active_time_entry is not None:
                playing.append(user)
        # logger.debug(
        #    "Playing users: " + str(len(playing)) + "/" + str(user_list.count())
        # )
        ach = AchievementsElems.TEAMWORK
        if len(playing) >= 4:  # and notification_sent is None:
            logger.info("4 or more users are playing!")
            someone_not_achieved = False
            players = ""
            for player in playing:
                players += player.name + ", "
                if not self.check_already_achieved(db, player.id, ach.name):
                    someone_not_achieved = True
                    logger.info("Set 'Teamwork' achievement for " + player.name)
                    self.set_user_achievement(db, player.id, ach.name)
            if someone_not_achieved:
                players = players[:-2]
                players = players.rsplit(",", 1)
                players = " y".join(players)
                msg = utils.get_ach_message(ach, user=players)
                await utils.send_message(
                    msg,
                    silent,
                    image=self.get_image(db, ach.name)[0],
                )
            else:
                logger.info("All users unlocked this achievement")

    async def early_riser(self, db: Session, user: models.User, silent: bool):
        # logger.debug("Checking early riser achievement...")
        entries = time_entries.get_time_entry_between_hours(
            db, user.id, start_hour=5, end_hour=6
        )
        ach = AchievementsElems.EARLY_RISER
        if len(entries) > 0 and not self.check_already_achieved(db, user.id, ach.name):
            logger.info("Set achievement early riser")
            self.set_user_achievement(
                db,
                user.id,
                ach.name,
                date=str(entries[0].start),
            )
            msg = utils.get_ach_message(ach, user=user.name)
            await utils.send_message(
                msg,
                silent,
                image=self.get_image(db, ach.name)[0],
            )

    async def nocturnal(self, db: Session, user: models.User, silent: bool):
        # logger.debug("Checking nocturnal achievement...")
        entries = time_entries.get_time_entry_between_hours(
            db, user.id, start_hour=2, end_hour=5
        )
        ach = AchievementsElems.NOCTURNAL
        if len(entries) > 0 and not self.check_already_achieved(db, user.id, ach.name):
            logger.info("Set achievement nocturnal")
            self.set_user_achievement(
                db,
                user.id,
                ach.name,
                date=str(entries[0].start),
            )
            msg = utils.get_ach_message(ach, user=user.name)
            await utils.send_message(
                msg,
                silent,
                image=self.get_image(db, ach.name)[0],
            )

    def get_weekly_achievements(
        self, db: Session, user: models.User, weeks_ago: int = 0
    ):
        """_summary_

        Args:
            db (Session): _description_
            user (models.User): _description_
            mode (int, optional): 0 = last week. 1 = current week. Defaults to 0.

        Returns:
            _type_: _description_
        """
        # if mode == 0:
        #     first_day, last_day = utils.get_last_week_range_dates()
        # else:
        #     first_day, last_day = utils.get_current_week_range_dates()
        first_day, last_day = utils.get_week_range_dates(weeks_ago)
        weekly_achievements = (
            db.query(func.count(models.UserAchievement.id))
            .filter(models.UserAchievement.user_id == user.id)
            .filter(func.DATE(models.UserAchievement.date) >= first_day)
            .filter(func.DATE(models.UserAchievement.date) <= last_day)
            .all()
        )
        return weekly_achievements

    def just_in_time(
        self,
        db: Session,
        user: models.User,
        played_time: int,
        avg_time: int,
        game_id: str,
        date: str = None,
    ):
        return
