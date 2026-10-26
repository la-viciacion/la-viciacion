"""The text of the notices about the challenges and the defaults of who gets them (pure: no database, no clock)."""
import datetime
import types
import unittest

from src.utils import challenge_notices as notices
from src.utils import challenges, my_utils, user_settings
from tests.sqlite_db import make_session


def challenge(title="Juego del mes: Hades", scope="group"):
    return types.SimpleNamespace(title=title, scope=scope)


class MessageTests(unittest.TestCase):
    def test_a_duel_invitation_says_who_challenged_until_when_and_how_long_it_can_be_turned_down(self):
        text = notices.duel_invite_message("Ana", "Duelo de horas", datetime.date(2026, 10, 31), 48)
        self.assertEqual(text.splitlines()[0], "⚔️ *Ana* te ha retado a un duelo")
        self.assertIn("31 de octubre", text)
        self.assertIn("próximas 48 horas", text)

    def test_names_and_titles_are_escaped_for_telegram(self):
        self.assertIn(r"*A\_na*", notices.duel_declined_message("A_na", "Duelo en Hades"))
        self.assertIn("ha rechazado tu duelo", notices.duel_declined_message("Bea", "Duelo de horas"))

    def test_a_proposal_decided_says_it_and_carries_the_note(self):
        approved = notices.proposal_decided_message("Temático: Horror", True, None)
        self.assertEqual(approved.splitlines()[0], "✅ Tu propuesta se ha aprobado")
        rejected = notices.proposal_decided_message("Temático: Horror", False, "Mejor en noviembre")
        self.assertEqual(rejected.splitlines()[0], "❌ Tu propuesta se ha rechazado")
        self.assertIn("Nota: Mejor en noviembre", rejected)
        self.assertNotIn("Nota", notices.proposal_decided_message("x", False, None))

    def test_a_new_proposal_names_who_made_it(self):
        self.assertIn("*Bea* ha propuesto un reto", notices.proposal_arrived_message("Bea", "Temático: Horror"))

    def test_what_a_player_lacks_is_said_in_hours_games_or_debt(self):
        self.assertEqual(notices.remaining_text({"seconds": 3600, "target_seconds": 9000}), "te faltan 1,5 h")
        self.assertEqual(notices.remaining_text({"count": 0, "target_count": 1}), "te falta 1 juego")
        self.assertEqual(notices.remaining_text({"count": 1, "target_count": 4, "unit": "days"}), "te faltan 3 días")
        self.assertEqual(notices.remaining_text({"count": 0, "target_count": 2, "unit": "sessions"}), "te faltan 2 sesiones")
        self.assertEqual(notices.remaining_text({"percent": 12.5, "target_percent": 25}), "te falta saldar un 12,5 % más")

    def test_a_digest_has_a_header_that_counts_and_one_line_per_challenge(self):
        one = notices.results_message(["✅ *A*: cumpliste tu parte"])
        self.assertEqual(one.splitlines()[0], "🏁 Ha terminado uno de tus retos")
        two = notices.results_message(["a", "b"])
        self.assertEqual(two.splitlines(), ["🏁 Han terminado 2 de tus retos", "a", "b"])
        self.assertEqual(notices.reminders_message(["x"]).splitlines()[0], "⏰ Te quedan 2 días en un reto")
        self.assertEqual(notices.reminders_message(["x", "y", "z"]).splitlines()[0], "⏰ Te quedan 2 días en 3 retos")

    def test_names_are_joined_in_spanish(self):
        self.assertEqual([my_utils.join_names(n) for n in (["A"], ["A", "B"], ["A", "B", "C"])], ["A", "A y B", "A, B y C"])


class ResultLineTests(unittest.TestCase):
    NAMES = {1: "Ana", 2: "Bea"}

    def test_a_met_part_and_one_that_was_not(self):
        progress = {"players": [{"user_id": 1, "done": True}, {"user_id": 2, "done": False}]}
        self.assertEqual(notices.result_line(challenge(scope="user"), progress, 1, self.NAMES), "✅ *Juego del mes: Hades*: cumpliste tu parte")
        self.assertEqual(notices.result_line(challenge(scope="user"), progress, 2, self.NAMES), "❌ *Juego del mes: Hades*: no se cumplió")

    def test_a_group_challenge_says_whether_the_group_reached_its_total_and_the_place_in_a_contest(self):
        progress = {"players": [{"user_id": 1, "done": True, "position": 2}], "total_done": True}
        line = notices.result_line(challenge(), progress, 1, self.NAMES)
        self.assertIn("cumpliste tu parte y el grupo llegó al total", line)
        self.assertTrue(line.endswith("(🥈)"))
        fourth = {"players": [{"user_id": 1, "done": False, "position": 4}]}
        self.assertTrue(notices.result_line(challenge(), fourth, 1, self.NAMES).endswith("(4º)"))

    def test_a_duel_is_told_from_each_side(self):
        duel = challenge("Duelo de horas", scope="duel")
        progress = {"players": [
            {"user_id": 1, "seconds": 7200, "done": True}, {"user_id": 2, "seconds": 3600, "done": False},
        ]}
        self.assertEqual(notices.result_line(duel, progress, 1, self.NAMES), "🥇 Ganaste el duelo a *Bea* (2 h frente a 1 h)")
        self.assertEqual(notices.result_line(duel, progress, 2, self.NAMES), "🥈 Perdiste el duelo contra *Ana* (1 h frente a 2 h)")

    def test_a_tie_and_a_duel_nobody_played(self):
        duel = challenge("Duelo de horas", scope="duel")
        tie = {"players": [{"user_id": 1, "seconds": 3600, "done": True}, {"user_id": 2, "seconds": 3600, "done": True}]}
        self.assertIn("empate (1 h frente a 1 h)", notices.result_line(duel, tie, 1, self.NAMES))
        nobody = {"players": [{"user_id": 1, "seconds": 0, "done": False}, {"user_id": 2, "seconds": 0, "done": False}]}
        self.assertIn("nadie jugó", notices.result_line(duel, nobody, 1, self.NAMES))

    def test_the_group_hears_how_many_met_it_the_total_and_who_won(self):
        progress = {
            "players": [{"name": "Ana", "done": True, "winner": True}, {"name": "Bea", "done": False, "winner": False}, {"name": "Cris", "done": True, "winner": False}],
            "total_done": False,
        }
        text = notices.group_result_message(challenge(), progress)
        self.assertEqual(text.splitlines()[0], "🏁 *Ha terminado el reto del grupo*")
        self.assertIn("2 de 3 habéis cumplido vuestra parte y el grupo no llegó al total.", text)
        self.assertIn("🥇 Gana *Ana*.", text)
        tie = {"players": [{"name": "Ana", "done": True, "winner": True}, {"name": "Bea", "done": True, "winner": True}]}
        self.assertIn("🥇 Ganan *Ana* y *Bea*.", notices.group_result_message(challenge(), tie))
        self.assertNotIn("🥇", notices.group_result_message(challenge(), {"players": [{"name": "Ana", "done": True}]}))
        self.assertNotIn("total", notices.group_result_message(challenge(), {"players": [{"name": "Ana", "done": True}]}))


class DefaultsTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()

    def test_what_concerns_a_player_is_on_and_the_reminders_are_off_until_they_ask(self):
        self.assertEqual(user_settings.challenge_notices_channels(self.db, 1), (True, True))
        self.assertEqual(user_settings.challenge_reminders_channels(self.db, 1), (False, False))
        defaults = user_settings.get(self.db, 1)["defaults"]
        self.assertEqual([defaults[k] for k in ("challenge_notices_telegram", "challenge_notices_push", "challenge_reminders_telegram", "challenge_reminders_push")], [True, True, False, False])

    def test_what_the_player_chose_wins_and_null_goes_back_to_the_default(self):
        user_settings.update(self.db, 1, {"challenge_reminders_push": True, "challenge_notices_telegram": False})
        self.assertEqual(user_settings.challenge_reminders_channels(self.db, 1), (False, True))
        self.assertEqual(user_settings.challenge_notices_channels(self.db, 1), (False, True))
        shown = user_settings.get(self.db, 1)
        self.assertEqual((shown["challenge_reminders_push"], shown["challenge_reminders_telegram"]), (True, None))
        user_settings.update(self.db, 1, {"challenge_reminders_push": None, "challenge_notices_telegram": None})
        self.assertEqual(user_settings.challenge_reminders_channels(self.db, 1), (False, False))
        self.assertEqual(user_settings.challenge_notices_channels(self.db, 1), (True, True))

    def test_the_reminder_is_two_days_before_the_end(self):
        self.assertEqual(notices.REMINDER_DAYS, 2)
        self.assertEqual(challenges.DECLINE_HOURS, 48)


if __name__ == "__main__":
    unittest.main()
