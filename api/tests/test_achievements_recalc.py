import datetime
import unittest
from unittest import mock

from src.utils import actions  # noqa: F401  (imported first: the crud and utils modules import each other)
from src.crud import achievements as ach_module
from src.crud import achievements_recalc as recalc
from src.crud.achievements import Achievements, Award
from src.database import models
from tests.sqlite_db import make_session

YEAR = datetime.date.today().year
PAST = YEAR - 1
D = datetime.date


def at(year, month, day, hour=10, minute=0):
    return datetime.datetime(year, month, day, hour, minute)


class RecalculationTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        self.db.add_all([
            models.User(id=1, name="Ana", username="ana", is_active=1),
            models.User(id=2, name="Bea", username="bea", is_active=0),  # not playing any more, played then
            models.User(id=9, name="Dios", username="admin", is_active=1, is_admin=1),  # the emergency account
            models.Game(id="g1", name="Doom", avg_time=7200),
        ])
        self.db.commit()
        Achievements().populate_achievements(self.db)
        self.sent = mock.AsyncMock()
        patcher = mock.patch.object(ach_module.utils, "send_message", self.sent)
        patcher.start()
        self.addCleanup(patcher.stop)

    def play(self, user_id, start, minutes=60, game="g1", running=False):
        self.db.add(models.GameTimer(
            user_id=user_id, game_id=game, start_time=start, is_active=running,
            end_time=None if running else start + datetime.timedelta(minutes=minutes),
            duration_seconds=None if running else minutes * 60,
        ))
        self.db.commit()

    def play_days(self, user_id, year, days, month=3):
        for day in range(1, days + 1):
            self.play(user_id, at(year, month, day))

    def award(self, user_id, key, date, game_id=None):
        achievement_id = self.db.query(models.Achievement.id).filter_by(key=key).scalar()
        self.db.add(models.UserAchievement(user_id=user_id, achievement_id=achievement_id, date=date, game_id=game_id))
        self.db.commit()

    def stored(self, user_id=1):
        rows = (
            self.db.query(models.Achievement.key, models.UserAchievement.date, models.UserAchievement.game_id)
            .join(models.UserAchievement, models.UserAchievement.achievement_id == models.Achievement.id)
            .filter(models.UserAchievement.user_id == user_id)
            .order_by(models.UserAchievement.id)
            .all()
        )
        return [tuple(row) for row in rows]

    def changes(self, **kwargs):
        return {(c.action, c.user_id, c.season, c.key): c for c in recalc.plan(self.db, **kwargs)}

    def test_it_adds_what_a_past_season_earned_dated_the_day_it_was_reached(self):
        self.play_days(1, PAST, 7)
        got = self.changes()
        self.assertEqual({key for action, _, season, key in got if action == "add" and season == PAST}, {"PLAYED_7_DAYS", "STREAK_7_DAYS"})
        self.assertEqual(got[("add", 1, PAST, "PLAYED_7_DAYS")].date_after, D(PAST, 3, 7))
        self.assertEqual({action for action, *_ in got}, {"add"})

    def test_it_corrects_dates_revokes_what_does_not_hold_and_removes_repeats(self):
        self.play_days(1, PAST, 7)
        self.award(1, "PLAYED_7_DAYS", D(PAST, 6, 20))  # a wrong date
        self.award(1, "PLAYED_30_DAYS", D(PAST, 6, 20))  # never reached
        self.award(1, "STREAK_7_DAYS", D(PAST, 3, 7))
        self.award(1, "STREAK_7_DAYS", D(PAST, 3, 7))  # repeated
        got = self.changes()
        self.assertEqual(got[("date", 1, PAST, "PLAYED_7_DAYS")].date_before, D(PAST, 6, 20))
        self.assertEqual(got[("date", 1, PAST, "PLAYED_7_DAYS")].date_after, D(PAST, 3, 7))
        self.assertIn(("revoke", 1, PAST, "PLAYED_30_DAYS"), got)
        self.assertEqual(len([key for key in got if key[0] == "revoke" and key[3] == "STREAK_7_DAYS"]), 1)
        self.assertNotIn(("add", 1, PAST, "PLAYED_7_DAYS"), got)

    def test_applying_it_leaves_nothing_more_to_change(self):
        self.play_days(1, PAST, 7)
        self.award(1, "PLAYED_7_DAYS", D(PAST, 6, 20))
        self.award(1, "PLAYED_30_DAYS", D(PAST, 6, 20))
        recalc.apply(self.db, recalc.plan(self.db))
        self.assertEqual(sorted(self.stored()), [("PLAYED_7_DAYS", D(PAST, 3, 7), None), ("STREAK_7_DAYS", D(PAST, 3, 7), None)])
        self.assertEqual(recalc.plan(self.db), [])

    def test_the_preview_changes_nothing(self):
        self.play_days(1, PAST, 7)
        self.award(1, "PLAYED_30_DAYS", D(PAST, 6, 20))
        before = self.stored()
        got = recalc.preview(self.db)
        self.assertEqual(self.stored(), before)
        self.assertEqual(got["counts"], {"add": 2, "date": 0, "revoke": 1})
        self.assertEqual(len(got["changes"]), 3)

    def test_nothing_is_ever_announced(self):
        self.play_days(1, PAST, 7)
        self.play(1, at(PAST, 3, 8, 5, 30))
        self.award(1, "PLAYED_30_DAYS", D(PAST, 6, 20))
        recalc.apply(self.db, recalc.plan(self.db))
        self.sent.assert_not_awaited()

    def test_a_check_in_collect_mode_cannot_announce_even_when_asked_to(self):
        import asyncio

        collected = []
        checks = Achievements(silent=False, season=PAST, collected=collected)
        self.play_days(1, PAST, 7)
        user = self.db.get(models.User, 1)
        asyncio.run(checks.user_played_total_days(self.db, user, [D(PAST, 3, d) for d in range(1, 8)], silent=False))
        self.assertEqual([a.key for a in collected], ["PLAYED_7_DAYS"])
        self.sent.assert_not_awaited()
        self.assertEqual(self.stored(), [])

    def test_players_who_are_no_longer_active_count_and_the_emergency_account_does_not(self):
        self.play_days(2, PAST, 7)
        self.play_days(9, PAST, 7)
        got = self.changes()
        self.assertIn(("add", 2, PAST, "PLAYED_7_DAYS"), got)
        self.assertEqual({user_id for _, user_id, *_ in got}, {2})

    def test_one_user_can_be_recalculated_alone(self):
        self.play_days(1, PAST, 7)
        self.play_days(2, PAST, 7)
        self.assertEqual({user_id for _, user_id, *_ in self.changes(user_ids=[2])}, {2})

    def test_some_players_and_some_seasons_can_be_chosen(self):
        self.play_days(1, PAST, 7)
        self.play_days(1, PAST - 1, 7)
        self.play_days(2, PAST, 7)
        got = self.changes(user_ids=[1, 2], season_list=[PAST])
        self.assertEqual({(user_id, season) for _, user_id, season, _ in got}, {(1, PAST), (2, PAST)})
        self.assertEqual({(user_id, season) for _, user_id, season, _ in self.changes(season_list=[PAST - 1])}, {(1, PAST - 1)})
        self.assertEqual(self.changes(user_ids=[1], season_list=[YEAR]), {})

    def test_every_season_is_worked_out_on_its_own(self):
        self.play_days(1, PAST, 7)
        self.play_days(1, YEAR, 3)
        got = self.changes()
        self.assertIn(("add", 1, PAST, "PLAYED_7_DAYS"), got)
        self.assertFalse([key for key in got if key[2] == YEAR])

    def test_an_award_of_the_wrong_season_is_replaced_in_its_own(self):
        self.play_days(1, PAST, 7)
        self.award(1, "PLAYED_7_DAYS", D(YEAR, 2, 1))  # filed under another season
        got = self.changes()
        self.assertIn(("revoke", 1, YEAR, "PLAYED_7_DAYS"), got)
        self.assertIn(("add", 1, PAST, "PLAYED_7_DAYS"), got)

    def test_just_in_time_and_opened_by_mistake_are_worked_out_from_the_season(self):
        self.db.add(models.UserGame(user_id=1, game_id="g1", started_date=D(PAST, 3, 1), platform=None, completed=1, completed_date=D(PAST, 3, 3)))
        self.play(1, at(PAST, 3, 1, 12), minutes=120)  # the 2 h of the average time
        self.play(1, at(PAST, 3, 2, 12), minutes=3)  # and a session of 3 minutes: 2 h 3 min is within 5 %
        self.db.commit()
        got = self.changes()
        self.assertEqual(got[("add", 1, PAST, "JUST_IN_TIME")].date_after, D(PAST, 3, 3))
        self.assertEqual(got[("add", 1, PAST, "JUST_IN_TIME")].game_after, "g1")
        self.assertEqual(got[("add", 1, PAST, "PLAYED_LESS_5_MIN_SESSION")].date_after, D(PAST, 3, 2))

    def test_a_session_that_was_deleted_takes_what_it_earned_with_it_in_that_season_only(self):
        import asyncio

        self.play_days(1, PAST, 7)
        self.award(1, "PLAYED_7_DAYS", D(PAST, 3, 7))
        self.award(1, "PLAYED_30_DAYS", D(YEAR, 6, 20))  # not earned either, but in another season
        self.db.query(models.GameTimer).filter(models.GameTimer.start_time == at(PAST, 3, 7)).delete()
        self.db.commit()
        asyncio.run(recalc.recalculate_user(self.db, 1, [PAST]))
        self.assertEqual(self.stored(), [("PLAYED_30_DAYS", D(YEAR, 6, 20), None)])
        self.sent.assert_not_awaited()

    def test_the_date_stays_in_its_season(self):
        collected = []
        checks = Achievements(season=PAST, collected=collected)
        checks._collect(1, ach_module.E.PLAYED_7_DAYS, f"{YEAR}-02-01", None)
        self.assertEqual(collected, [Award(1, "PLAYED_7_DAYS", D(PAST, 12, 31), None)])

    def test_a_recalculation_needs_the_date_of_everything(self):
        with self.assertRaises(ValueError):
            Achievements(season=PAST, collected=[])._collect(1, ach_module.E.PLAYED_7_DAYS, None, None)


class TeamworkDatesTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        self.db.add_all([models.User(id=i, name=f"P{i}", username=f"p{i}", is_active=1 if i < 4 else 0) for i in range(1, 6)])
        self.db.add(models.User(id=9, name="Dios", username="admin", is_active=1, is_admin=1))
        self.db.add(models.Game(id="g1", name="Doom"))
        self.db.commit()

    def play(self, user_id, start, hours=2, running=False):
        self.db.add(models.GameTimer(
            user_id=user_id, game_id="g1", start_time=start, is_active=running,
            end_time=None if running else start + datetime.timedelta(hours=hours),
            duration_seconds=None if running else hours * 3600,
        ))
        self.db.commit()

    def test_four_players_playing_at_once_all_get_the_day_they_met(self):
        for user_id, hour in ((1, 20), (2, 20), (3, 21), (4, 21)):
            self.play(user_id, at(YEAR, 3, 5, hour))
        self.assertEqual(recalc.teamwork_dates(self.db, YEAR), {1: D(YEAR, 3, 5), 2: D(YEAR, 3, 5), 3: D(YEAR, 3, 5), 4: D(YEAR, 3, 5)})

    def test_three_players_or_sessions_that_do_not_overlap_are_not_a_team(self):
        for user_id, hour in ((1, 20), (2, 20), (3, 20)):
            self.play(user_id, at(YEAR, 3, 5, hour))
        self.play(4, at(YEAR, 3, 5, 22), hours=1)  # starts when the others have finished
        self.assertEqual(recalc.teamwork_dates(self.db, YEAR), {})

    def test_the_same_player_twice_is_one_player(self):
        for hour in (20, 20, 21, 21):
            self.play(1, at(YEAR, 3, 5, hour))
        self.assertEqual(recalc.teamwork_dates(self.db, YEAR), {})

    def test_players_who_are_no_longer_active_and_running_timers_count_but_not_the_emergency_account(self):
        self.play(1, at(YEAR, 3, 5, 20))
        self.play(5, at(YEAR, 3, 5, 20))  # inactive today
        self.play(2, at(YEAR, 3, 5, 20), running=True)
        self.play(9, at(YEAR, 3, 5, 20))  # the emergency account
        self.assertEqual(recalc.teamwork_dates(self.db, YEAR, now=at(YEAR, 3, 5, 21)), {})
        self.play(3, at(YEAR, 3, 6, 20))
        self.play(4, at(YEAR, 3, 6, 20))
        self.play(5, at(YEAR, 3, 6, 20))
        got = recalc.teamwork_dates(self.db, YEAR, now=at(YEAR, 3, 6, 22))
        self.assertEqual(set(got), {2, 3, 4, 5})
        self.assertEqual(set(got.values()), {D(YEAR, 3, 6)})

    def test_it_only_looks_at_the_season(self):
        for user_id in (1, 2, 3, 4):
            self.play(user_id, at(YEAR - 1, 3, 5, 20))
        self.assertEqual(recalc.teamwork_dates(self.db, YEAR), {})
        self.assertEqual(set(recalc.teamwork_dates(self.db, YEAR - 1)), {1, 2, 3, 4})

    def test_three_players_on_the_same_game_at_once_get_it_with_the_game(self):
        self.db.add(models.Game(id="g2", name="Quake"))
        for user_id, game, hour in ((1, "g1", 20), (2, "g1", 20), (3, "g1", 21), (4, "g2", 21)):
            self.db.add(models.GameTimer(
                user_id=user_id, game_id=game, start_time=at(YEAR, 3, 5, hour), end_time=at(YEAR, 3, 5, hour + 2), duration_seconds=7200, is_active=False,
            ))
        self.db.commit()
        got = recalc.all_together_days(self.db, YEAR)
        self.assertEqual(got, {1: (D(YEAR, 3, 5), "g1"), 2: (D(YEAR, 3, 5), "g1"), 3: (D(YEAR, 3, 5), "g1")})  # not the one on another game

    def test_two_players_or_three_on_different_games_are_not_all_together(self):
        self.db.add(models.Game(id="g2", name="Quake"))
        for user_id, game in ((1, "g1"), (2, "g1"), (3, "g2")):
            self.db.add(models.GameTimer(
                user_id=user_id, game_id=game, start_time=at(YEAR, 3, 5, 20), end_time=at(YEAR, 3, 5, 22), duration_seconds=7200, is_active=False,
            ))
        self.db.commit()
        self.assertEqual(recalc.all_together_days(self.db, YEAR), {})

    def test_it_is_part_of_the_recalculation(self):
        for user_id in (1, 2, 3, 4):
            self.play(user_id, at(YEAR - 1, 3, 5, 20))
        Achievements().populate_achievements(self.db)
        with mock.patch.object(ach_module.utils, "send_message", mock.AsyncMock()):
            got = {(c.action, c.user_id, c.key): c for c in recalc.plan(self.db)}
        for user_id in (1, 2, 3, 4):
            self.assertEqual(got[("add", user_id, "TEAMWORK")].date_after, D(YEAR - 1, 3, 5))


if __name__ == "__main__":
    unittest.main()
