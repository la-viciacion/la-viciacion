"""What each notice that the AI rewrites tells it, against what its prompt asks the AI to keep.

The AI only knows what the message of the notice says, and only does what its prompt asks: a figure missing from
either side is a figure missing from the notice. These tests pin both sides together for every use of ai_prompts."""
import datetime
import unittest
from unittest import mock

from src.crud import users  # noqa: F401  (the app's modules import each other: this order resolves it)
from src.crud.users import completion_message, new_game_message
from src.utils import actions, ai_prompts


class CompletionNoticeTests(unittest.TestCase):
    def test_it_says_how_long_it_took_the_player_and_the_average_apart(self):
        msg = completion_message("Toni", 1, "Tomodachi Life", 12 * 3600 + 30 * 60, 36 * 3600 + 24 * 60)
        self.assertEqual(msg, "Toni acaba de completar su juego número 1: *Tomodachi Life* en 12h30m. La media está en 36h24m.")

    def test_the_game_links_to_its_page_in_the_app_when_the_address_is_known(self):
        with mock.patch.object(users.utils.config, "PUBLIC_URL", "https://viciacion.test"):
            msg = completion_message("Toni", 1, "Doom", 7200, None, "doom-id")
            self.assertIn("[Doom](https://viciacion.test/#/game/doom-id) en 02h00m.", msg)
            self.assertIn("*Doom*", completion_message("Toni", 1, "Doom", 7200, None))
        with mock.patch.object(users.utils.config, "PUBLIC_URL", ""):
            self.assertIn("*Doom* en", completion_message("Toni", 1, "Doom", 7200, None, "doom-id"))

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
        msg = actions.wishlist_eve_message([("Hades II", ["Ana", "Bea"], None), ("Silksong", ["Cai"], None)])
        self.assertTrue(msg.startswith("📅 *Mañana salen 2 juegos*"))  # the prompt asks to keep the first line
        for name in ("Hades II", "Silksong", "Ana y Bea", "Cai"):
            self.assertIn(name, msg)


class WishlistWeekNoticeTests(unittest.TestCase):
    def test_it_names_each_game_with_its_weekday_and_everybody_who_waits_for_it(self):
        msg = actions.wishlist_week_message([
            ("Hades II", datetime.date(2026, 3, 9), ["Ana", "Bea"], None),
            ("Silksong", datetime.date(2026, 3, 15), ["Cai"], None),
        ])
        plain = msg.replace("*", "")
        self.assertIn("Lunes 9: Hades II", plain)
        self.assertIn("Domingo 15: Silksong", plain)
        self.assertIn("Ana y Bea", msg)
        self.assertIn("Cai", msg)
        self.assertTrue(msg.startswith("📅 *Esta semana salen 2 juegos*"))  # the prompt asks to keep the first line


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

    def test_every_prompt_asks_to_be_brief_and_to_start_with_the_message_itself(self):
        for use in ("new_game", "completed_game", "completed_game_recommendation", "ranking_players", "ranking_games", "wishlist_release", "wishlist_day", "wishlist_week"):
            text = self.prompt(use)
            if use == "completed_game_recommendation":
                self.assertIn("No te alargues", text, use)  # it only adds one last short sentence
                continue
            self.assertIn("Empieza por lo importante", text, use)
            self.assertTrue("Sé breve" in text or "corta" in text, use)

    def test_the_rankings_put_the_list_before_the_comment_and_keep_the_comment_to_one_sentence(self):
        for use in ("ranking_players", "ranking_games"):
            text = self.prompt(use)
            self.assertLess(text.index("clasificación original sin modificar"), text.index("Después de la clasificación"), use)
            self.assertIn("una sola frase corta", text, use)

    def test_completed_game_does_not_ask_for_an_average_that_may_not_be_there(self):
        self.assertNotIn("Debes añadir, además, la media", self.prompt("completed_game"))

    def test_new_game_asks_for_the_name_the_game_the_link_and_the_count(self):
        text = self.prompt("new_game")
        for wanted in ("nombre del usuario", "nombre del juego", "enlace", "cantidad de juegos empezados"):
            self.assertIn(wanted, text)

    def test_the_rankings_ask_to_keep_their_title_and_the_original_list(self):
        for use in ("ranking_players", "ranking_games"):
            text = self.prompt(use)
            self.assertIn("debe empezar con '📣", text)
            self.assertIn("clasificación original sin modificar", text)

    def test_the_wishlist_asks_for_every_game_every_person_and_tomorrow(self):
        text = self.prompt("wishlist_release")
        for wanted in ("primera línea del mensaje original", "nombre de cada juego", "todas las personas", "mañana", "todos"):
            self.assertIn(wanted, text)

    def test_the_same_day_wishlist_asks_for_every_game_every_person_and_today(self):
        text = self.prompt("wishlist_day")
        for wanted in ("primera línea del mensaje original", "nombre de cada juego", "todas las personas", "hoy", "todos"):
            self.assertIn(wanted, text)

    def test_the_weekly_wishlist_asks_for_every_game_every_person_and_the_weekday(self):
        text = self.prompt("wishlist_week")
        for wanted in ("primera línea del mensaje original", "nombre de cada juego", "todas las personas", "día de la semana", "todos"):
            self.assertIn(wanted, text)

    def test_the_recommendation_asks_for_the_game_alone_never_for_who_has_it(self):
        text = self.prompt("completed_game_recommendation")
        self.assertIn("nombre del juego", text)
        self.assertIn("no menciones a ningún jugador", text)
        self.assertNotIn("Jugado por", text)
        self.assertNotIn("la persona indicada", text)


if __name__ == "__main__":
    unittest.main()
