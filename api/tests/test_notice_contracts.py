"""What each notice that the AI rewrites tells it, against what its prompt asks the AI to keep.

The AI only knows what the message of the notice says, and only does what its prompt asks: a figure missing from
either side is a figure missing from the notice. These tests pin both sides together for every use of ai_prompts."""
import unittest

from src.crud import users  # noqa: F401  (the app's modules import each other: this order resolves it)
from src.crud.users import completion_message, new_game_message
from src.utils import actions, ai_prompts


class CompletionNoticeTests(unittest.TestCase):
    def test_it_says_how_long_it_took_the_player_and_the_average_apart(self):
        msg = completion_message("Toni", 1, "Tomodachi Life", 12 * 3600 + 30 * 60, 36 * 3600 + 24 * 60)
        self.assertEqual(msg, "Toni acaba de completar su juego número 1: *Tomodachi Life* en 12h30m. La media está en 36h24m.")

    def test_the_player_time_comes_before_the_average(self):
        msg = completion_message("Toni", 3, "Doom", 7200, 36000)
        self.assertLess(msg.index("02h00m"), msg.index("10h00m"))

    def test_without_a_known_average_it_does_not_invent_one(self):
        for average in (None, 0):
            msg = completion_message("Toni", 2, "Doom", 7200, average)
            self.assertIn("en 02h00m.", msg)
            self.assertNotIn("media", msg)

    def test_the_time_survives_the_decimals_sql_returns(self):
        from decimal import Decimal

        self.assertIn("en 01h02m.", completion_message("Ana", 1, "Doom", Decimal("3725"), None))

    def test_names_cannot_break_the_markdown(self):
        msg = completion_message("A_n*a", 1, "Do[om]_", 60, None)
        self.assertIn("A\\_n\\*a", msg)
        self.assertIn("Do\\[om]\\_", msg)


class NewGameNoticeTests(unittest.TestCase):
    def test_it_has_who_which_game_with_its_link_and_how_many(self):
        msg = new_game_message("Ana", "Hades", "hades", 7)
        self.assertEqual(msg, "*Ana* acaba de empezar [Hades](https://rawg.io/games/hades), su juego número 7 de este año.")

    def test_a_game_without_a_slug_has_no_link(self):
        self.assertNotIn("](", new_game_message("Ana", "Hades", None, 1))


class RankingNoticeTests(unittest.TestCase):
    def test_the_hours_ranking_has_every_player_with_hours_and_movement(self):
        players = [{"user_id": 2, "name": "Bea", "played_time": 7200}, {"user_id": 1, "name": "Ana", "played_time": 3600}]
        msg = actions.players_ranking_message([1, 2], players)
        self.assertTrue(msg.startswith("📣 Actualización del ránking de horas 📣"))  # the prompt asks to start with it
        self.assertIn("1.", msg)
        self.assertIn("Bea", msg)
        self.assertIn("02h00m", msg)
        self.assertIn("↑1", msg)
        self.assertIn("↓1", msg)

    def test_the_games_ranking_has_every_game_with_hours_and_movement(self):
        games = [{"game_id": "b", "name": "Hades", "played_time": 7200}, {"game_id": "a", "name": "Doom", "played_time": 3600}]
        msg = actions.games_ranking_message(["a", "b"], games)
        self.assertTrue(msg.startswith("📣 Actualización del ránking de juegos 📣"))
        self.assertIn("Hades", msg)
        self.assertIn("02h00m", msg)
        self.assertIn("↑1", msg)


class WishlistNoticeTests(unittest.TestCase):
    def test_it_names_each_game_and_everybody_who_waits_for_it_and_says_tomorrow(self):
        msg = actions.wishlist_eve_message([("Hades II", ["Ana", "Bea"]), ("Silksong", ["Cai"])])
        self.assertEqual(msg.count("Mañana sale"), 2)
        for name in ("Hades II", "Silksong", "Ana y Bea", "Cai"):
            self.assertIn(name, msg)


class PromptsAskForWhatTheNoticesCarryTests(unittest.TestCase):
    """The prompt of each use asks the AI to keep what its message holds."""

    def prompt(self, use):
        return ai_prompts.USES[use].default

    def test_completed_game_asks_for_the_player_time_and_for_the_average_when_there_is_one(self):
        text = self.prompt("completed_game")
        for wanted in ("el nombre del usuario", "el nombre del juego", "cantidad de juegos completados",
                       "tiempo que le ha costado al usuario", "tras la palabra \"en\"", "Si el mensaje original indica la media",
                       "Si el mensaje no indica la media, no la menciones", "No te inventes ninguna cifra"):
            self.assertIn(wanted, text)

    def test_the_completed_notice_goes_to_the_group_so_it_asks_for_the_third_person(self):
        self.assertIn("tercera persona", self.prompt("completed_game"))
        self.assertIn("sin dirigirte a él", self.prompt("completed_game"))
        self.assertIn("tercera persona", self.prompt("completed_game_recommendation"))

    def test_completed_game_does_not_ask_for_an_average_that_may_not_be_there(self):
        self.assertNotIn("Debes añadir, además, la media", self.prompt("completed_game"))

    def test_new_game_asks_for_the_name_the_game_the_link_and_the_count(self):
        text = self.prompt("new_game")
        for wanted in ("nombre del usuario", "nombre del juego", "enlace", "cantidad de juegos empezados"):
            self.assertIn(wanted, text)

    def test_the_rankings_ask_to_keep_their_title_and_the_original_list(self):
        for use in ("ranking_players", "ranking_games"):
            text = self.prompt(use)
            self.assertIn("Debes empezar el mensaje con '📣", text)
            self.assertIn("clasificación original sin modificar", text)

    def test_the_wishlist_asks_for_every_game_every_person_and_tomorrow(self):
        text = self.prompt("wishlist_release")
        for wanted in ("nombre de cada juego", "todas las personas", "mañana", "todos"):
            self.assertIn(wanted, text)

    def test_the_recommendation_asks_for_the_game_and_the_person(self):
        text = self.prompt("completed_game_recommendation")
        self.assertIn("nombre del juego", text)
        self.assertIn("persona", text)


if __name__ == "__main__":
    unittest.main()
