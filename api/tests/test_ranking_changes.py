import unittest

from src.utils import actions


def player(user_id, name, seconds):
    return {"user_id": user_id, "name": name, "played_time": seconds}


def game(game_id, name, seconds):
    return {"game_id": game_id, "name": name, "played_time": seconds}


class PositionTests(unittest.TestCase):
    def test_climbing_falling_and_staying(self):
        self.assertEqual(actions.position_change(3, 1), (2, "↑2"))
        self.assertEqual(actions.position_change(1, 2), (-1, "↓1"))
        self.assertEqual(actions.position_change(2, 2), (0, "="))

    def test_decorations(self):
        self.assertEqual(actions.decorate_name("Ana", 0), "Ana")
        self.assertEqual(actions.decorate_name("Ana", 1), "⬆️ *Ana*")
        self.assertEqual(actions.decorate_name("Ana", 3), "🔥 *Ana*")
        self.assertEqual(actions.decorate_name("Ana", -1), "⬇️ *Ana*")
        self.assertEqual(actions.decorate_name("Ana", -2), "🔻 *Ana*")

    def test_order_changed_ignores_players_who_were_not_there(self):
        self.assertFalse(actions.order_changed([1, 2, 3], [1, 2, 3, 4]))
        self.assertTrue(actions.order_changed([1, 2, 3], [2, 1, 3]))


class PlayersMessageTests(unittest.TestCase):
    def test_no_message_when_the_order_is_the_same(self):
        self.assertIsNone(actions.players_ranking_message([1, 2], [player(1, "Ana", 100), player(2, "Bob", 50)]))

    def test_overtaking_is_announced_with_arrows(self):
        message = actions.players_ranking_message([1, 2], [player(2, "Bob", 4000), player(1, "Ana", 3600)])
        self.assertIn("1. ⬆️ *Bob*", message)
        self.assertIn("(↑1)", message)
        self.assertIn("2. ⬇️ *Ana*", message)
        self.assertIn("(↓1)", message)

    def test_a_new_player_does_not_count_as_a_change(self):
        players = [player(1, "Ana", 100), player(2, "Bob", 50), player(3, "Eva", 0)]
        self.assertIsNone(actions.players_ranking_message([1, 2], players))


class GamesMessageTests(unittest.TestCase):
    def games(self, order):
        return [game(g, f"G{g}", 1000 - i) for i, g in enumerate(order)]

    def test_no_message_when_the_top_10_is_the_same(self):
        order = list(range(1, 13))
        self.assertIsNone(actions.games_ranking_message(order, self.games(order)))

    def test_change_below_the_top_10_is_not_announced(self):
        before = list(range(1, 13))
        after = list(range(1, 11)) + [12, 11]
        self.assertIsNone(actions.games_ranking_message(before, self.games(after)))

    def test_new_entry_in_the_top_10_and_the_game_that_falls_out(self):
        before = list(range(1, 12))  # 1..11
        after = [11] + list(range(1, 11))  # 11 jumps to the top, 10 becomes 11th
        message = actions.games_ranking_message(before, self.games(after))
        self.assertIn("1. 🔥 *G11*", message)
        self.assertIn("(↑10)", message)
        self.assertIn("----------\n11. G10", message)
        self.assertIn("(💀)", message)

    def test_a_game_that_was_not_ranked_before_counts_as_new_at_its_place(self):
        before = list(range(1, 11))
        after = [99] + list(range(1, 10))
        message = actions.games_ranking_message(before, self.games(after))
        self.assertIn("1. G99", message)


if __name__ == "__main__":
    unittest.main()
