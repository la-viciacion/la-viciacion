"""How alike two players are (crud/affinity.score): the three parts, what is left out and when it is too soon to say."""
import unittest

from src.crud import affinity


def taste(games, scores=None, genre_time=None):
    return {"games": set(games), "scores": scores or {}, "genre_time": genre_time or {}}


class ScoreTests(unittest.TestCase):
    def test_the_same_taste_is_a_hundred_percent(self):
        both = taste("abc", {"a": 70}, {"RPG": 3600})
        self.assertEqual(affinity.score(both, both), {"percent": 100, "shared_games": 3, "shared_rated": 1})

    def test_fewer_than_three_games_in_common_is_too_soon_to_say(self):
        result = affinity.score(taste("abx"), taste("aby"))
        self.assertEqual(result, {"percent": None, "shared_games": 2, "shared_rated": 0})

    def test_without_ratings_or_time_only_the_games_in_common_count(self):
        # 3 shared of 5 in either: 60 %
        self.assertEqual(affinity.score(taste("abcd"), taste("abce"))["percent"], 60)

    def test_ratings_far_apart_pull_it_down_and_close_ones_barely_move_it(self):
        base = ("abc", "abc")
        far = affinity.score(taste(base[0], {"a": 1}), taste(base[1], {"a": 100}))["percent"]
        near = affinity.score(taste(base[0], {"a": 80}), taste(base[1], {"a": 82}))["percent"]
        # the games part is 1.0 in both; the ratings part is 0 (1 against 100) or 0.98
        self.assertEqual(far, 62)  # (0.5 * 1 + 0.3 * 0) / 0.8
        self.assertEqual(near, 99)  # (0.5 + 0.3 * 0.9798) / 0.8

    def test_the_genres_count_by_the_share_of_the_time_played_in_each(self):
        same_games = "abc"
        mine = taste(same_games, genre_time={"RPG": 3600, "Action": 3600})
        theirs = taste(same_games, genre_time={"RPG": 3600})
        # overlap: min(0.5, 1) = 0.5; games part 1.0 -> (0.5 + 0.2 * 0.5) / 0.7
        self.assertEqual(affinity.score(mine, theirs)["percent"], 86)

    def test_a_player_who_never_played_leaves_the_genres_out(self):
        self.assertEqual(affinity.score(taste("abc", genre_time={"RPG": 10}), taste("abc"))["percent"], 100)


if __name__ == "__main__":
    unittest.main()
