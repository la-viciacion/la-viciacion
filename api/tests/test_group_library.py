"""The lists of the group's library, from plain facts (pure: no database)."""
import datetime
import unittest

from src.crud import group_library as gl


def facts(**over):
    base = {
        "owners": {}, "seconds": {}, "scores": {}, "abandoned_by": {}, "completed": {}, "genres": {}, "platforms": {},
        "wishes": {}, "released": {}, "played_by": {}, "seconds_by": {}, "franchises": {},
    }
    base.update(over)
    return base


class HiddenGemsTests(unittest.TestCase):
    def test_few_owners_and_well_rated_the_best_first(self):
        f = facts(
            owners={"a": {1}, "b": {1, 2}, "c": {1, 2, 3}, "d": {1}, "e": {2}},
            scores={"a": [90], "b": [90, 100], "c": [99, 99], "d": [60], "e": []},
        )
        found = gl.hidden_gems(f)
        self.assertEqual([g["game_id"] for g in found], ["b", "a"])  # c has too many owners, d is rated badly, e is not rated
        self.assertEqual((found[0]["score_mean"], found[0]["score_count"], found[0]["players"]), (95.0, 2, 2))

    def test_a_tie_goes_to_the_one_with_fewer_owners_and_the_edges_count(self):
        f = facts(owners={"x": {1, 2}, "y": {1}}, scores={"x": [80], "y": [80]})
        self.assertEqual([g["game_id"] for g in gl.hidden_gems(f)], ["y", "x"])  # exactly 80 and exactly 2 owners still count


class GraveyardTests(unittest.TestCase):
    def test_the_most_abandoned_first_then_the_most_played(self):
        f = facts(owners={"a": {1, 2, 3}, "b": {1}, "c": {1, 2}}, seconds={"a": 10, "b": 500, "c": 20},
                  abandoned_by={"a": {1, 2}, "b": {1}, "c": {2}, "d": set()})
        found = gl.graveyard(f)
        self.assertEqual([(g["game_id"], g["abandoned_by"], g["players"]) for g in found], [("a", [1, 2], 3), ("b", [1], 1), ("c", [2], 2)])


class RaritiesTests(unittest.TestCase):
    def test_a_rarity_has_one_owner_and_the_most_played_come_first(self):
        f = facts(owners={"a": {1}, "b": {2}, "c": {1, 2}}, seconds={"a": 5, "b": 50})
        self.assertEqual([(g["game_id"], g["owner"], g["seconds"]) for g in gl.rarities(f)], [("b", 2, 50), ("a", 1, 5)])


class CoverageTests(unittest.TestCase):
    def test_a_game_counts_in_each_of_its_genres_with_its_hours_players_and_completions(self):
        f = facts(
            owners={"a": {1, 2}, "b": {2}, "c": {3}},
            seconds={"a": 100, "b": 50, "c": 7},
            completed={"a": {1}, "b": {2}},
            genres={"a": ["RPG", "Indie"], "b": ["RPG"], "c": ["Indie"]},
        )
        rows = {r["genre"]: r for r in gl.by_genre(f)}
        self.assertEqual(rows["RPG"], {"genre": "RPG", "games": 2, "players": 2, "seconds": 150, "completed": 2})
        self.assertEqual(rows["Indie"], {"genre": "Indie", "games": 2, "players": 3, "seconds": 107, "completed": 1})
        self.assertEqual(gl.by_genre(f)[0]["genre"], "RPG")  # same games: the one with more hours first

    def test_platforms_count_games_and_players(self):
        f = facts(platforms={"pc": {"a": {1, 2}, "b": {1}}, "switch": {"a": {3}}, "ps5": {}})
        self.assertEqual(gl.by_platform(f), [{"platform": "pc", "games": 2, "players": 2}, {"platform": "switch", "games": 1, "players": 1}])

    def test_nothing_gives_empty_lists(self):
        empty = facts()
        self.assertEqual([gl.hidden_gems(empty), gl.graveyard(empty), gl.rarities(empty), gl.by_genre(empty), gl.by_platform(empty)], [[]] * 5)
        self.assertEqual([gl.most_wanted(empty), gl.played_together(empty), gl.finished_by_many(empty), gl.sagas(empty)], [[]] * 4)


if __name__ == "__main__":
    unittest.main()


class TogetherAndSagasTests(unittest.TestCase):
    def test_the_most_wished_first_then_the_soonest_release_and_games_without_a_date_last(self):
        day = datetime.date
        f = facts(wishes={"a": [1], "b": [1, 2], "c": [1], "d": [], "e": [3]},
                  released={"a": day(2027, 5, 1), "b": None, "c": day(2027, 2, 1), "e": None})
        self.assertEqual([(g["game_id"], g["wanters"]) for g in gl.most_wanted(f)], [("b", [1, 2]), ("c", [1]), ("a", [1]), ("e", [3])])

    def test_played_together_needs_two_players_in_one_season_and_shows_the_fullest_one(self):
        f = facts(
            played_by={"a": {2025: {1, 2}, 2026: {1}}, "b": {2025: {1}, 2026: {2}}, "c": {2025: {1, 2, 3}, 2026: {1, 2}}, "d": {2026: {1, 2}}},
            seconds={"a": 10, "c": 5, "d": 50},
        )
        self.assertEqual([(g["game_id"], g["players"], g["season"]) for g in gl.played_together(f)], [("c", 3, 2025), ("d", 2, 2026), ("a", 2, 2025)])

    def test_finished_by_many_needs_two_completions_and_averages_the_time_of_those_who_finished(self):
        f = facts(
            owners={"a": {1, 2, 3}, "b": {1, 2}, "c": {1}, "d": {1, 2}},
            completed={"a": {1, 2}, "b": {1, 2}, "c": {1}, "d": {1, 2}},
            seconds_by={"a": {1: 100, 2: 300, 3: 9000}, "b": {1: 60}},
        )
        found = {g["game_id"]: g for g in gl.finished_by_many(f)}
        self.assertEqual(set(found), {"a", "b", "d"})
        self.assertEqual((found["a"]["mean_seconds"], found["a"]["players"]), (200, 3))  # the third player did not finish it: not in the mean
        self.assertEqual(found["b"]["mean_seconds"], 60)
        self.assertIsNone(found["d"]["mean_seconds"])
        self.assertEqual([g["game_id"] for g in gl.finished_by_many(f)], ["b", "d", "a"])  # same completions: the fewest owners first

    def test_a_saga_has_two_games_or_more_in_the_libraries(self):
        f = facts(
            owners={"a": {1, 2}, "b": {2}, "c": {1}, "d": {3}},
            seconds={"a": 100, "b": 50, "c": 10},
            franchises={"a": ["Zelda"], "b": ["Zelda", "Link"], "c": ["Mario"], "d": ["Mario"], "e": ["Zelda"]},  # e is in nobody's library
        )
        self.assertEqual(gl.sagas(f), [{"saga": "Zelda", "games": 2, "players": 2, "seconds": 150}, {"saga": "Mario", "games": 2, "players": 2, "seconds": 10}])
