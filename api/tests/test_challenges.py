"""The templates of the challenges that need no database (utils/challenges.py): periods, numbers, the progress of a
game of the month, the notice texts and what makes two challenges the same."""
import datetime
import hashlib
import json
import types
import unittest
from unittest import mock

from src.utils import challenges
from src.utils.challenges import Built, ChallengeError


def built(**changes):
    values = dict(title="t", params={"min_hours_each": 5, "min_hours_total": 30}, starts_on=datetime.date(2026, 10, 1),
                  ends_on=datetime.date(2026, 10, 31), game_id="hades")
    return Built(**{**values, **changes})


class PeriodTests(unittest.TestCase):
    def test_a_month_runs_from_its_first_to_its_last_day(self):
        self.assertEqual(challenges.month_period("2026-10"), (datetime.date(2026, 10, 1), datetime.date(2026, 10, 31)))
        self.assertEqual(challenges.month_period("2026-12"), (datetime.date(2026, 12, 1), datetime.date(2026, 12, 31)))
        self.assertEqual(challenges.month_period("2028-02")[1], datetime.date(2028, 2, 29))

    def test_a_month_that_is_not_one_is_refused(self):
        for bad in (None, "", "2026", "2026-13", "x-y", 5):
            with self.assertRaises(ChallengeError, msg=repr(bad)):
                challenges.month_period(bad)

    def test_the_status_follows_the_period(self):
        challenge = types.SimpleNamespace(starts_on=datetime.date(2026, 10, 10), ends_on=datetime.date(2026, 10, 20))
        status = lambda day: challenges.status_of(challenge, datetime.date(2026, 10, day))  # noqa: E731
        self.assertEqual([status(9), status(10), status(20), status(21)], ["upcoming", "active", "active", "finished"])


class LaunchMomentTests(unittest.TestCase):
    DAY = datetime.date(2026, 10, 15)
    LAUNCHED = datetime.datetime(2026, 10, 15, 13, 30)

    def challenge(self, scope=challenges.USER, created_at=LAUNCHED):
        return types.SimpleNamespace(scope=scope, starts_on=self.DAY, ends_on=self.DAY + datetime.timedelta(days=6), created_at=created_at)

    def test_a_personal_challenge_or_a_duel_counts_from_the_moment_it_was_launched(self):
        for scope in (challenges.USER, challenges.DUEL):
            self.assertEqual(challenges.starts_at(self.challenge(scope)), self.LAUNCHED)

    def test_a_group_challenge_counts_its_whole_first_day(self):
        self.assertEqual(challenges.starts_at(self.challenge(challenges.GROUP)), datetime.datetime(2026, 10, 15))

    def test_the_window_runs_from_the_launch_to_the_first_instant_after_the_last_day(self):
        self.assertEqual(challenges._window(self.challenge()), (self.LAUNCHED, datetime.datetime(2026, 10, 22)))

    def test_one_that_begins_after_it_was_launched_waits_for_its_first_day(self):
        later = self.challenge()
        later.starts_on = self.DAY + datetime.timedelta(days=2)
        self.assertEqual(challenges.starts_at(later), datetime.datetime(2026, 10, 17))

    def test_a_date_on_the_launch_day_counts_only_when_the_game_was_played_since(self):
        challenge = self.challenge()
        self.assertTrue(challenges.counts_from_launch(challenge, self.DAY, "hades", {"hades"}))
        self.assertFalse(challenges.counts_from_launch(challenge, self.DAY, "hades", {"celeste"}))
        self.assertTrue(challenges.counts_from_launch(challenge, self.DAY + datetime.timedelta(days=1), "hades", set()))

    def test_a_group_challenge_and_a_missing_date_have_no_such_limit(self):
        self.assertTrue(challenges.counts_from_launch(self.challenge(challenges.GROUP), self.DAY, "hades", None))
        self.assertTrue(challenges.counts_from_launch(self.challenge(), None, "hades", set()))


class HoursTests(unittest.TestCase):
    def test_hours_are_rounded_to_a_tenth_and_kept_within_limits(self):
        self.assertEqual(challenges.hours("2.55", "x"), 2.5)  # round() on a float, banker's rounding is fine
        self.assertEqual(challenges.hours(5, "x"), 5.0)
        for bad in (0, 0.4, -1, challenges.MAX_HOURS + 1, "abc", None):
            with self.assertRaises(ChallengeError, msg=repr(bad)):
                challenges.hours(bad, "Las horas")

    def test_the_texts(self):
        self.assertEqual(challenges.hours_text(5.0), "5")
        self.assertEqual(challenges.hours_text(2.5), "2,5")
        self.assertEqual(challenges.spanish_date(datetime.date(2026, 10, 31)), "31 de octubre")


class FingerprintTests(unittest.TestCase):
    def test_equal_challenges_have_the_same_fingerprint_whatever_the_order_of_the_options(self):
        a = challenges.fingerprint("game_of_month", built(params={"min_hours_each": 5, "min_hours_total": 30}), None)
        b = challenges.fingerprint("game_of_month", built(params={"min_hours_total": 30, "min_hours_each": 5}), None)
        self.assertEqual(a, b)
        self.assertEqual(len(a), 64)

    def test_anything_that_differs_changes_it(self):
        base = challenges.fingerprint("game_of_month", built(), None)
        for other in (
            challenges.fingerprint("game_of_month", built(game_id="celeste"), None),
            challenges.fingerprint("game_of_month", built(params={"min_hours_each": 6, "min_hours_total": 30}), None),
            challenges.fingerprint("game_of_month", built(starts_on=datetime.date(2026, 11, 1), ends_on=datetime.date(2026, 11, 30)), None),
            challenges.fingerprint("game_of_month", built(), 7),  # a personal one of somebody
            challenges.fingerprint("themed", built(), None),
        ):
            self.assertNotEqual(base, other)


class GameOfMonthProgressTests(unittest.TestCase):
    NAMES = {1: "Ana", 2: "Bea", 3: "Cai"}

    def test_each_player_has_their_own_part_and_the_group_a_total(self):
        result = challenges.game_of_month_result({1: 7 * 3600, 2: 3 * 3600}, self.NAMES, 5, 30)
        self.assertEqual([(p["name"], p["seconds"], p["done"]) for p in result["players"]], [("Ana", 25200, True), ("Bea", 10800, False), ("Cai", 0, False)])
        self.assertEqual((result["total_seconds"], result["total_target_seconds"], result["total_done"]), (36000, 108000, False))

    def test_the_total_is_reached_whoever_contributes_it(self):
        result = challenges.game_of_month_result({1: 30 * 3600}, self.NAMES, 5, 30)
        self.assertTrue(result["total_done"])
        self.assertEqual([p["done"] for p in result["players"]], [True, False, False])

    def test_a_player_reaches_their_part_exactly_at_the_minimum(self):
        self.assertTrue(challenges.game_of_month_result({1: 5 * 3600}, {1: "Ana"}, 5, 5)["players"][0]["done"])
        self.assertFalse(challenges.game_of_month_result({1: 5 * 3600 - 1}, {1: "Ana"}, 5, 5)["players"][0]["done"])

    def test_nobody_taking_part_never_reaches_the_total(self):
        self.assertFalse(challenges.game_of_month_result({}, {}, 5, 0.5)["total_done"])


class NoticeTests(unittest.TestCase):
    def challenge(self):
        return types.SimpleNamespace(
            params=json.dumps({"min_hours_each": 5, "min_hours_total": 30}), starts_on=datetime.date(2026, 10, 1), ends_on=datetime.date(2026, 10, 31),
        )

    def test_the_launch_says_what_is_asked_and_until_when(self):
        text = challenges.TEMPLATES["game_of_month"].summary(self.challenge())
        self.assertEqual(text, "Mínimo 5 h cada uno y 30 h entre todos, del 1 de octubre al 31 de octubre.")

    def test_the_total_notice_says_how_many_met_their_part(self):
        progress = challenges.game_of_month_result({1: 20 * 3600, 2: 10 * 3600}, {1: "Ana", 2: "Bea", 3: "Cai"}, 5, 30)
        text = challenges.TEMPLATES["game_of_month"].reached(self.challenge(), progress)
        self.assertEqual(text, "Entre todos habéis llegado a las 30 h. 2 de 3 ya habéis cumplido vuestro mínimo.")


class NewGenreTests(unittest.TestCase):
    def test_the_genres_of_a_game_are_split_whatever_the_spacing(self):
        self.assertEqual(challenges.split_genres("Action, RPG,Indie"), ["Action", "RPG", "Indie"])
        for nothing in (None, "", " , "):
            self.assertEqual(challenges.split_genres(nothing), [], repr(nothing))

    def test_the_durations_count_the_day_it_starts(self):
        self.assertEqual(challenges.DURATIONS, {"week": 7, "month": 30, "quarter": 90})
        self.assertEqual(challenges.DEFAULT_HOURS, 2)

    def test_playing_is_done_at_the_hours_asked_and_not_before(self):
        below = challenges.new_genre_result(1, "Ana", "play", 7199, 2)["players"][0]
        self.assertEqual((below["seconds"], below["target_seconds"], below["done"]), (7199, 7200, False))
        self.assertTrue(challenges.new_genre_result(1, "Ana", "play", 7200, 2)["players"][0]["done"])

    def test_completing_asks_for_one_game(self):
        none = challenges.new_genre_result(1, "Ana", "complete", 0, None)["players"][0]
        one = challenges.new_genre_result(1, "Ana", "complete", 1, None)["players"][0]
        self.assertEqual((none["count"], none["target_count"], none["done"], one["done"]), (0, 1, False, True))

    def test_a_personal_challenge_has_no_group_total(self):
        self.assertNotIn("total_done", challenges.new_genre_result(1, "Ana", "play", 0, 2))
        self.assertEqual(challenges.new_genre_result(None, "", "play", 0, 2), {"players": []})


class ThemedTests(unittest.TestCase):
    NAMES = {1: "Ana", 2: "Bea", 3: "Cai"}

    def test_playing_is_each_players_hours_with_an_optional_group_total(self):
        params = {"min_hours_each": 2, "min_hours_total": 5}
        result = challenges.themed_result(self.NAMES, "play", {1: 3 * 3600, 2: 3600}, params)
        self.assertEqual([(p["name"], p["seconds"], p["done"]) for p in result["players"]], [("Ana", 10800, True), ("Bea", 3600, False), ("Cai", 0, False)])
        self.assertEqual((result["total_seconds"], result["total_target_seconds"], result["total_done"]), (14400, 18000, False))
        self.assertTrue(challenges.themed_result(self.NAMES, "play", {1: 5 * 3600}, params)["total_done"])

    def test_without_a_total_there_is_none_to_reach(self):
        for mode, params in (("play", {"min_hours_each": 2}), ("complete", {})):
            result = challenges.themed_result(self.NAMES, mode, {1: 99}, params)
            self.assertFalse({"total_done", "total_seconds", "total_count"} & set(result), mode)

    def test_completing_asks_one_game_each_and_a_count_between_everybody(self):
        result = challenges.themed_result(self.NAMES, "complete", {1: 2, 2: 1}, {"min_games_total": 4})
        self.assertEqual([(p["name"], p["count"], p["target_count"], p["done"]) for p in result["players"]], [("Ana", 2, 1, True), ("Bea", 1, 1, True), ("Cai", 0, 1, False)])
        self.assertEqual((result["total_count"], result["total_target_count"], result["total_done"]), (3, 4, False))
        self.assertTrue(challenges.themed_result(self.NAMES, "complete", {1: 2, 2: 2}, {"min_games_total": 4})["total_done"])

    def test_nobody_taking_part_never_reaches_a_total(self):
        self.assertFalse(challenges.themed_result({}, "play", {}, {"min_hours_each": 1, "min_hours_total": 1})["total_done"])

    def test_the_notices(self):
        challenge = types.SimpleNamespace(starts_on=datetime.date(2026, 10, 1), ends_on=datetime.date(2026, 10, 31))
        template = challenges.TEMPLATES["themed"]
        play = types.SimpleNamespace(**vars(challenge), params=json.dumps({"tag": "Horror", "mode": "play", "min_hours_each": 2, "min_hours_total": 10}))
        self.assertEqual(template.summary(play), "Jugar al menos 2 h a juegos de Horror, cada uno y 10 h entre todos, del 1 de octubre al 31 de octubre.")
        done = types.SimpleNamespace(**vars(challenge), params=json.dumps({"tag": "Horror", "mode": "complete"}))
        self.assertEqual(template.summary(done), "Completar al menos un juego de Horror, del 1 de octubre al 31 de octubre.")
        with_total = types.SimpleNamespace(**vars(challenge), params=json.dumps({"tag": "Horror", "mode": "complete", "min_games_total": 5}))
        self.assertIn("(y 5 entre todos)", template.summary(with_total))
        progress = challenges.themed_result({1: "Ana", 2: "Bea"}, "complete", {1: 3, 2: 2}, {"min_games_total": 5})
        self.assertEqual(template.reached(with_total, progress), "Entre todos habéis llegado a los 5 juegos completados de Horror. 2 de 2 ya habéis cumplido vuestra parte.")


class DebtReductionTests(unittest.TestCase):
    START = {"a": 10 * 3600, "b": 5 * 3600, "c": 0}  # what was left of each open game when it began

    def result(self, params, played=None, completed=()):
        return challenges.debt_reduction_result(1, "Ana", params, self.START, played or {}, set(completed))["players"][0]

    def test_playing_pays_what_was_played_up_to_what_was_left(self):
        part = self.result({"mode": "percent", "percent": 50}, {"a": 3 * 3600, "b": 9 * 3600})
        self.assertEqual((part["paid_seconds"], part["initial_seconds"], part["percent"], part["done"]), (8 * 3600, 15 * 3600, 53.3, True))

    def test_completing_pays_all_that_was_left_and_a_game_played_but_not_in_the_debt_pays_nothing(self):
        part = self.result({"mode": "percent", "percent": 10}, {"zzz": 99 * 3600}, completed={"a"})
        self.assertEqual((part["paid_seconds"], part["done"]), (10 * 3600, True))
        self.assertEqual(self.result({"mode": "percent", "percent": 10}, {"zzz": 99 * 3600})["paid_seconds"], 0)

    def test_the_target_is_reached_exactly_at_the_percentage(self):
        self.assertTrue(self.result({"mode": "percent", "percent": 20}, {"a": 3 * 3600})["done"])  # 3 of 15 h
        self.assertFalse(self.result({"mode": "percent", "percent": 20}, {"a": 3 * 3600 - 1})["done"])

    def test_nothing_owed_is_never_done(self):
        part = challenges.debt_reduction_result(1, "Ana", {"mode": "percent", "percent": 1}, {"a": 0}, {}, set())["players"][0]
        self.assertEqual((part["percent"], part["done"]), (0.0, False))

    def test_closing_counts_the_completed_games_that_were_open(self):
        part = self.result({"mode": "games", "games": 2}, completed={"a", "c", "new"})
        self.assertEqual((part["count"], part["target_count"], part["done"]), (2, 2, True))
        self.assertFalse(self.result({"mode": "games", "games": 2}, completed={"a", "new"})["done"])

    def test_nobody_taking_part_has_no_progress(self):
        self.assertEqual(challenges.debt_reduction_result(None, "", {"mode": "games", "games": 1}, {}, {}, set()), {"players": []})


class StreakTests(unittest.TestCase):
    DAYS = [datetime.date(2026, 10, d) for d in (1, 2, 3, 5, 6, 9)]

    def test_consecutive_counts_the_longest_run_and_days_counts_every_one(self):
        run = challenges.streak_result(1, "Ana", "consecutive", 4, self.DAYS, datetime.date(2026, 10, 31))
        self.assertEqual(run["players"][0], {"user_id": 1, "name": "Ana", "count": 3, "target_count": 4, "unit": "days", "done": False})
        days = challenges.streak_result(1, "Ana", "days", 6, self.DAYS, datetime.date(2026, 10, 31))
        self.assertEqual((days["players"][0]["count"], days["players"][0]["done"]), (6, True))

    def test_no_day_played_is_a_zero(self):
        self.assertEqual(challenges.streak_result(1, "Ana", "consecutive", 2, [], datetime.date(2026, 10, 31))["players"][0]["count"], 0)

    def test_the_options_are_checked_against_the_length_of_the_period(self):
        today = datetime.date(2026, 10, 1)
        week = challenges.build_streak(None, {"mode": "consecutive", "days": 7, "duration": "week"}, today)
        self.assertEqual((week.title, week.ends_on), ("Racha de 7 días", datetime.date(2026, 10, 7)))
        self.assertEqual(challenges.build_streak(None, {"mode": "days", "days": "10"}, today).title, "Jugar 10 días distintos")
        for options in ({"mode": "x", "days": 3}, {"mode": "days", "days": 1}, {"mode": "days", "days": 8, "duration": "week"},
                        {"mode": "days", "days": 2.5}, {"mode": "days", "days": True}, {"mode": "days", "days": 3, "duration": "year"}):
            with self.assertRaises(ChallengeError, msg=options):
                challenges.build_streak(None, options, today)


class LongSessionsTests(unittest.TestCase):
    def test_the_title_says_how_many_and_how_long(self):
        today = datetime.date(2026, 10, 1)
        self.assertEqual(challenges.build_long_sessions(None, {"sessions": 1, "minutes": 90}, today).title, "1 sesión de 90 min o más")
        self.assertEqual(challenges.build_long_sessions(None, {"sessions": 3, "minutes": 60, "duration": "quarter"}, today).ends_on, datetime.date(2026, 12, 29))

    def test_the_limits(self):
        for options in ({"sessions": 0, "minutes": 60}, {"sessions": 101, "minutes": 60}, {"sessions": 2, "minutes": 14}, {"sessions": 2, "minutes": 601}, {"sessions": 2}):
            with self.assertRaises(ChallengeError, msg=options):
                challenges.build_long_sessions(None, options, datetime.date(2026, 10, 1))


class VarietyTests(unittest.TestCase):
    def test_a_games_time_counts_in_each_of_its_genres_and_a_genre_needs_the_minimum(self):
        rows = [("Action, RPG", 3600), ("action", 1800), ("Puzzle", 600), (None, 99999), ("", 99999)]
        self.assertEqual(challenges.genres_reached(rows, 3600), 2)  # Action 5400, RPG 3600; Puzzle falls short
        self.assertEqual(challenges.genres_reached(rows, 1), 3)
        self.assertEqual(challenges.genres_reached(rows, 6000), 0)
        self.assertEqual(challenges.genres_reached([], 1), 0)


class VersusTests(unittest.TestCase):
    def test_the_positions_are_shared_on_a_tie_and_only_the_first_with_something_done_wins(self):
        players = challenges.rank_players([{"seconds": 3600}, {"seconds": 7200}, {"seconds": 3600}, {"seconds": 0}])
        self.assertEqual([(p["position"], p["winner"]) for p in players], [(2, False), (1, True), (2, False), (3, False)])

    def test_nobody_wins_when_nothing_was_done(self):
        players = challenges.rank_players([{"count": 0}, {"count": 0}])
        self.assertEqual([(p["position"], p["winner"]) for p in players], [(1, False), (1, False)])

    def test_it_ranks_counts_and_shares_of_the_debt_too(self):
        self.assertEqual([p["position"] for p in challenges.rank_players([{"count": 1}, {"count": 3}])], [2, 1])
        self.assertEqual([p["position"] for p in challenges.rank_players([{"percent": 50.0}, {"percent": 12.5}])], [1, 2])

    def test_a_group_challenge_is_a_contest_only_when_it_says_so(self):
        self.assertEqual(challenges._versus({"versus": True}), {"versus": True})
        self.assertEqual(challenges._versus({"versus": "true"}), {"versus": True})
        self.assertEqual(challenges._versus({"versus": False}), {})
        self.assertEqual(challenges._versus({}), {})


class DuelTests(unittest.TestCase):
    NAMES = {1: "Ana", 2: "Bea"}

    def test_whoever_played_more_wins_and_the_bar_is_against_the_leader(self):
        result = challenges.duel_result(self.NAMES, {1: 3600, 2: 7200})
        self.assertEqual([(p["name"], p["position"], p["done"], p["target_seconds"], p["versus"]) for p in result["players"]],
                         [("Bea", 1, True, 7200, True), ("Ana", 2, False, 7200, True)])

    def test_a_tie_is_won_by_both_but_not_when_nobody_played(self):
        tie = challenges.duel_result(self.NAMES, {1: 600, 2: 600})
        self.assertEqual([p["done"] for p in tie["players"]], [True, True])
        nothing = challenges.duel_result(self.NAMES, {})
        self.assertEqual([(p["seconds"], p["done"]) for p in nothing["players"]], [(0, False), (0, False)])

    def test_a_duel_declined_has_one_player_who_wins_nothing_by_default(self):
        self.assertEqual([p["done"] for p in challenges.duel_result({1: "Ana"}, {1: 0})["players"]], [False])

    def test_the_duel_templates_are_the_only_ones_of_that_scope(self):
        self.assertEqual({k for k, t in challenges.TEMPLATES.items() if t.scope == challenges.DUEL}, {"duel_hours", "duel_game", "duel_completed"})


class DuelCompletedTests(unittest.TestCase):
    NAMES = {1: "Ana", 2: "Bea"}

    def test_whoever_completed_more_games_wins_and_the_parts_are_counts(self):
        result = challenges.duel_result(self.NAMES, {1: 1, 2: 3}, counted=True)
        self.assertEqual([(p["name"], p["position"], p["done"], p["count"], p["target_count"], p["unit"]) for p in result["players"]],
                         [("Bea", 1, True, 3, 3, "games"), ("Ana", 2, False, 1, 3, "games")])
        self.assertFalse(any("seconds" in p for p in result["players"]))

    def test_a_tie_with_something_completed_is_won_by_both_and_nobody_wins_with_nothing(self):
        self.assertEqual([p["done"] for p in challenges.duel_result(self.NAMES, {1: 2, 2: 2}, counted=True)["players"]], [True, True])
        self.assertEqual([p["done"] for p in challenges.duel_result(self.NAMES, {}, counted=True)["players"]], [False, False])

    def test_it_is_built_like_the_other_duels(self):
        today = datetime.date(2026, 10, 1)
        db = types.SimpleNamespace(get=lambda model, user_id: types.SimpleNamespace(is_active=True, username="bea"))
        built_duel = challenges.build_duel_completed(db, {"opponent_id": 2, "duration": "week"}, today, 1)
        self.assertEqual((built_duel.title, built_duel.params, built_duel.ends_on), ("Duelo de completados", {"opponent_id": 2, "duration": "week"}, datetime.date(2026, 10, 7)))
        with self.assertRaises(ChallengeError):
            challenges.build_duel_completed(db, {"opponent_id": 1}, today, 1)  # not against yourself


class GroupHoursTests(unittest.TestCase):
    NAMES = {1: "Ana", 2: "Bea", 3: "Cai"}
    HOUR = 3600

    def test_it_is_reached_between_everybody_and_met_by_whoever_put_something_in(self):
        result = challenges.group_hours_result({1: 6 * self.HOUR, 2: 4 * self.HOUR}, self.NAMES, 10)
        self.assertEqual((result["total_seconds"], result["total_target_seconds"], result["total_done"]), (10 * self.HOUR, 10 * self.HOUR, True))
        self.assertEqual([(p["name"], p["done"]) for p in result["players"]], [("Ana", True), ("Bea", True), ("Cai", False)])
        self.assertTrue(all(p["contribution"] and p["target_seconds"] == 10 * self.HOUR for p in result["players"]))

    def test_nobody_meets_a_part_while_the_group_falls_short(self):
        result = challenges.group_hours_result({1: 9 * self.HOUR}, self.NAMES, 10)
        self.assertEqual((result["total_done"], [p["done"] for p in result["players"]]), (False, [False, False, False]))

    def test_nobody_taking_part_reaches_nothing(self):
        self.assertFalse(challenges.group_hours_result({}, {}, 1)["total_done"])

    def test_the_options_are_checked(self):
        today = datetime.date(2026, 10, 15)
        built_group = challenges.build_group_hours(None, {"month": "2026-10", "min_hours_total": "40"}, today)
        self.assertEqual((built_group.title, built_group.params, built_group.game_id, built_group.ends_on), ("Sumar 40 h entre todos", {"min_hours_total": 40.0}, None, datetime.date(2026, 10, 31)))
        self.assertEqual(challenges.build_group_hours(None, {"month": "2026-11", "min_hours_total": 5, "versus": True}, today).params, {"min_hours_total": 5.0, "versus": True})
        for options in ({"month": "2026-09", "min_hours_total": 40}, {"month": "2026-10"}, {"month": "2026-10", "min_hours_total": 0.1}, {"min_hours_total": 40}):
            with self.assertRaises(ChallengeError, msg=options):
                challenges.build_group_hours(None, options, today)

    def test_the_notices_say_the_total(self):
        challenge = types.SimpleNamespace(params=json.dumps({"min_hours_total": 40.0}), starts_on=datetime.date(2026, 10, 1), ends_on=datetime.date(2026, 10, 31))
        self.assertEqual(challenges.summary_group_hours(challenge), "Jugar 40 h entre todos, a lo que sea, del 1 de octubre al 31 de octubre.")
        progress = challenges.group_hours_result({1: 3600 * 40}, {1: "Ana", 2: "Bea"}, 40)
        self.assertEqual(challenges.reached_group_hours(challenge, progress), "Entre todos habéis llegado a las 40 h. Han aportado 1 de 2.")


class FinishFirstTests(unittest.TestCase):
    def day(self, n):
        return datetime.date(2026, 10, n)

    def part(self, completed, started):
        return challenges.finish_first_result(1, "Ana", [self.day(n) for n in completed], [self.day(n) for n in started])["players"][0]

    def test_it_is_won_by_completing_an_open_game_without_starting_a_new_one_first(self):
        part = self.part([5], [])
        self.assertEqual((part["done"], part["failed"], part["count"], part["target_count"]), (True, False, 1, 1))

    def test_it_is_lost_by_starting_a_new_game_before_completing_one(self):
        for completed in ([], [8]):
            part = self.part(completed, [6])
            self.assertEqual((part["done"], part["failed"], part["count"]), (False, True, 0), msg=completed)

    def test_a_new_game_after_the_win_changes_nothing(self):
        part = self.part([5], [9, 10])
        self.assertEqual((part["done"], part["failed"]), (True, False))

    def test_on_the_same_day_the_completion_comes_first(self):
        part = self.part([6], [6])
        self.assertEqual((part["done"], part["failed"]), (True, False))

    def test_it_is_open_until_something_happens(self):
        part = self.part([], [])
        self.assertEqual((part["done"], part["failed"]), (False, False))

    def test_the_first_completion_and_the_first_start_are_the_ones_that_count(self):
        self.assertTrue(self.part([9, 4], [7])["done"])
        self.assertTrue(self.part([4, 9], [10, 7])["done"])
        self.assertTrue(self.part([8], [3, 7])["failed"])

    def test_it_needs_a_game_open_to_begin_with(self):
        today = datetime.date(2026, 10, 1)
        with mock.patch("src.crud.debt.open_games_at", return_value=set()):
            with self.assertRaises(ChallengeError):
                challenges.build_finish_first(None, {}, today, 1)
            with self.assertRaises(ChallengeError):
                challenges.build_finish_backlog(None, {"games": 1}, today, 1)
        with mock.patch("src.crud.debt.open_games_at", return_value={"a", "b"}):
            made = challenges.build_finish_first(None, {"duration": "week"}, today, 1)
            self.assertEqual((made.title, made.params, made.ends_on), ("Terminar antes de empezar otro", {"duration": "week"}, datetime.date(2026, 10, 7)))


class FinishBacklogTests(unittest.TestCase):
    def test_it_asks_for_no_more_games_than_the_player_has_open(self):
        today = datetime.date(2026, 10, 1)
        with mock.patch("src.crud.debt.open_games_at", return_value={"a", "b", "c"}):
            made = challenges.build_finish_backlog(None, {"games": 2, "duration": "quarter"}, today, 1)
            self.assertEqual((made.title, made.params, made.ends_on), ("Terminar 2 juegos empezados", {"games": 2, "duration": "quarter"}, datetime.date(2026, 12, 29)))
            self.assertEqual(challenges.build_finish_backlog(None, {"games": 1}, today, 1).title, "Terminar 1 juego empezado")
            for options in ({"games": 0}, {"games": 4}, {"games": 1.5}, {}, {"games": 1, "duration": "year"}):
                with self.assertRaises(ChallengeError, msg=options):
                    challenges.build_finish_backlog(None, options, today, 1)


class AuthoringTests(unittest.TestCase):
    def test_months_are_counted_across_the_year_end(self):
        self.assertEqual(challenges.month_start(datetime.date(2026, 10, 17)), datetime.date(2026, 10, 1))
        self.assertEqual(challenges.next_month(datetime.date(2026, 12, 31)), datetime.date(2027, 1, 1))
        self.assertEqual(challenges.next_month(datetime.date(2026, 1, 31)), datetime.date(2026, 2, 1))
        self.assertEqual(challenges.months_between(datetime.date(2026, 11, 1), datetime.date(2027, 2, 20)), 3)
        self.assertEqual(challenges.months_between(datetime.date(2026, 11, 1), datetime.date(2026, 10, 1)), -1)

    def test_only_the_options_a_group_template_knows_are_kept(self):
        kept = challenges.clean_options({"game_id": "hades", "month": "2026-10", "min_hours_each": 3, "tag": None, "owner_user_id": 5, "x": 1})
        self.assertEqual(kept, {"game_id": "hades", "month": "2026-10", "min_hours_each": 3})
        self.assertEqual(challenges.clean_options(None), {})

    def test_an_old_challenge_keeps_its_fingerprint_and_a_voluntary_one_has_another(self):
        one = built()
        usual = challenges.fingerprint("game_of_month", one, None)
        self.assertEqual(usual, challenges.fingerprint("game_of_month", one, None, "auto"))
        self.assertNotEqual(usual, challenges.fingerprint("game_of_month", one, None, "opt_in"))
        canonical = json.dumps(["game_of_month", one.params, one.game_id, one.starts_on.isoformat(), one.ends_on.isoformat(), None], sort_keys=True, ensure_ascii=False)
        self.assertEqual(usual, hashlib.sha256(canonical.encode("utf-8")).hexdigest())  # what was stored before the participation existed

    def test_a_conflict_is_a_challenge_error_too(self):
        self.assertTrue(issubclass(challenges.ChallengeConflict, ChallengeError))


if __name__ == "__main__":
    unittest.main()
