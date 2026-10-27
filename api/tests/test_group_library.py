"""The lists of the group's library, from plain facts (pure: no database)."""
import unittest

from src.crud import group_library as gl


def facts(**over):
    base = {"owners": {}, "seconds": {}, "scores": {}, "abandoned_by": {}, "completed": {}, "genres": {}, "platforms": {}}
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


class RaritiesAndDustTests(unittest.TestCase):
    def test_a_rarity_has_one_owner_and_the_most_played_come_first(self):
        f = facts(owners={"a": {1}, "b": {2}, "c": {1, 2}}, seconds={"a": 5, "b": 50})
        self.assertEqual([(g["game_id"], g["owner"], g["seconds"]) for g in gl.rarities(f)], [("b", 2, 50), ("a", 1, 5)])

    def test_dust_is_a_game_somebody_has_and_nobody_played_the_most_owned_first(self):
        f = facts(owners={"a": {1}, "b": {1, 2, 3}, "c": {1, 2}, "d": {1}}, seconds={"a": 60, "c": 0})
        self.assertEqual([(g["game_id"], g["players"]) for g in gl.untouched(f)], [("b", 3), ("c", 2), ("d", 1)])


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
        self.assertEqual([gl.hidden_gems(empty), gl.graveyard(empty), gl.rarities(empty), gl.untouched(empty), gl.by_genre(empty), gl.by_platform(empty)], [[]] * 6)


if __name__ == "__main__":
    unittest.main()
