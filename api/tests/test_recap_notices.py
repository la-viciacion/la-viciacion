"""The notices of the recap: what they say, who they go to and the month the monthly job reports on."""
import datetime
import unittest
from unittest import mock

from fastapi import HTTPException

from src.crud import recap
from src.database import models
from src.routers.manage import notices
from src.utils import ai_prompts, recap_notices
from tests.sqlite_db import make_session

HOUR = 3600
D = datetime.datetime
APRIL = recap.parse_period("2026-04")


def session(user, game, start, hours):
    return models.GameTimer(
        user_id=user, game_id=game, start_time=start, end_time=start + datetime.timedelta(hours=hours),
        duration_seconds=hours * HOUR, is_active=False,
    )


class LabelTests(unittest.TestCase):
    def test_a_month_and_a_season(self):
        self.assertEqual(recap_notices.period_label(APRIL), "abril de 2026")
        self.assertEqual(recap_notices.period_label(recap.parse_period("2026")), "la temporada 2026")

    def test_the_job_reports_on_the_month_before_its_slot(self):
        self.assertEqual(recap_notices.previous_month(datetime.date(2026, 10, 1)).key, "2026-09")
        self.assertEqual(recap_notices.previous_month(datetime.date(2027, 1, 1)).key, "2026-12")


class RecapData(unittest.IsolatedAsyncioTestCase):
    """A month of sessions in a database and the senders replaced by mocks."""

    def setUp(self):
        self.db = make_session()
        self.db.add_all([
            models.User(id=1, name="Ana_", username="ana", is_active=1, telegram_id=11),
            models.User(id=2, name="Biel", username="biel", is_active=1, telegram_id=None),
            models.User(id=3, name="Cris", username="cris", is_active=1, telegram_id=33),
            models.Game(id="doom", name="Doom"),
            session(1, "doom", D(2026, 4, 10, 20), 3),
            session(2, "doom", D(2026, 4, 10, 21), 1),
            session(1, "doom", D(2026, 3, 5, 20), 2),
        ])
        self.db.commit()
        self.group = mock.AsyncMock()
        self.private = mock.AsyncMock()
        for target, replacement in (
            (recap_notices.utils, {"send_message": self.group, "send_message_to_user": self.private}),
            (recap_notices.actions, {"push_has_devices": mock.Mock(return_value=False)}),
        ):
            for name, value in replacement.items():
                patcher = mock.patch.object(target, name, value)
                patcher.start()
                self.addCleanup(patcher.stop)



class NoticeTests(RecapData):
    def test_the_group_message_has_the_title_the_hours_the_podium_and_the_game(self):
        text = recap_notices.group_message(recap.build_recap(self.db, APRIL), APRIL)
        for wanted in ("*Resumen de abril de 2026*", "04h00m", "+02h00m", "🥇 Ana\\_ — 03h00m", "🥈 Biel — 01h00m", "*Doom*", "10 abr"):
            self.assertIn(wanted, text)

    def test_the_player_message_is_about_them(self):
        text = recap_notices.player_message(recap.build_recap(self.db, APRIL, 1), APRIL)
        for wanted in ("*Tu resumen de abril de 2026*", "Horas: 03h00m", "puesto 1º", "*Doom*", "Biel"):
            self.assertIn(wanted, text)

    def test_the_link_is_there_only_with_a_public_address(self):
        data = recap.build_recap(self.db, APRIL)
        with mock.patch.object(recap_notices.config, "PUBLIC_URL", "https://viciacion.example"):
            self.assertIn("[Ver tu resumen en historias](https://viciacion.example/#/story/2026-04)", recap_notices.group_message(data, APRIL))
        with mock.patch.object(recap_notices.config, "PUBLIC_URL", ""):
            self.assertNotIn("](", recap_notices.group_message(data, APRIL))

    async def test_it_goes_to_the_group_with_the_ai_and_privately_to_who_played_and_can_be_reached(self):
        result = await recap_notices.announce_recap(self.db, APRIL)
        self.assertEqual(result, {"empty": False, "group": True, "players": 1})
        self.group.assert_awaited_once()
        self.assertEqual(self.group.await_args.kwargs["ai_use"], "monthly_recap")
        # the app's devices get a short "it is ready" notice that opens the story, not the long text
        payload = self.group.await_args.kwargs["push_payload"]
        self.assertEqual((payload["url"], payload["tag"]), ("#/story/2026-04", "recap"))
        self.assertEqual(payload["title"], "🎬 Ya está disponible tu resumen de abril de 2026")
        self.assertEqual(self.private.await_args.kwargs["push_payload"], payload)
        # Ana can be reached and played; Biel played but has no Telegram nor devices; Cris did not play
        self.private.assert_awaited_once()
        self.assertEqual(self.private.await_args.args[0], 11)
        self.assertEqual(self.private.await_args.kwargs["user_id"], 1)

    async def test_only_one_user_and_no_group_for_a_test_to_an_admin(self):
        user = self.db.get(models.User, 1)
        result = await recap_notices.announce_recap(self.db, APRIL, group=False, only=user)
        self.assertEqual(result, {"empty": False, "group": False, "players": 1})
        self.group.assert_not_awaited()
        self.assertEqual(self.private.await_count, 1)

    async def test_only_the_group(self):
        result = await recap_notices.announce_recap(self.db, APRIL, players=False)
        self.assertEqual(result, {"empty": False, "group": True, "players": 0})
        self.private.assert_not_awaited()

    async def test_a_month_nobody_played_sends_nothing(self):
        result = await recap_notices.announce_recap(self.db, recap.parse_period("2026-01"))
        self.assertEqual(result, {"empty": True, "group": False, "players": 0})
        self.group.assert_not_awaited()
        self.private.assert_not_awaited()
        self.assertEqual(recap_notices.describe(result), "nobody played")

    def test_the_status_of_a_run(self):
        self.assertEqual(recap_notices.describe({"empty": False, "group": True, "players": 3}), "group and 3 users")
        self.assertEqual(recap_notices.describe({"empty": False, "group": False, "players": 1}), "1 user")


class EndpointTests(RecapData):
    """The routes over the same data (called as functions: the router-level security is in test_endpoint_security)."""

    def test_the_preview_gives_the_texts_without_sending_anything(self):
        got = notices.recap_preview("2026-04", 1, self.db)
        self.assertEqual((got["period"], got["label"], got["nobody_played"]), ("2026-04", "abril de 2026", False))
        self.assertIn("Resumen de abril", got["group_message"])
        self.assertIn("Tu resumen", got["player_message"])
        self.group.assert_not_awaited()

    def test_the_preview_of_a_quiet_month_says_so(self):
        self.assertTrue(notices.recap_preview("2026-01", None, self.db)["nobody_played"])
        self.assertIsNone(notices.recap_preview("2026-04", None, self.db)["player_message"])

    def test_a_wrong_or_future_period_is_refused(self):
        for period in ("2026-13", "x"):
            with self.assertRaises(HTTPException) as refused:
                notices.recap_preview(period, None, self.db)
            self.assertEqual(refused.exception.status_code, 400)
        with self.assertRaises(HTTPException):
            notices.recap_preview(str(datetime.date.today().year + 1), None, self.db)

    def test_an_unknown_user_is_not_found(self):
        with self.assertRaises(HTTPException) as refused:
            notices.recap_preview("2026-04", 99, self.db)
        self.assertEqual(refused.exception.status_code, 404)

    async def test_sending_to_me_reaches_only_the_admin(self):
        admin = self.db.get(models.User, 1)
        got = await notices.recap_send(notices.RecapSendBody(period="2026-04", audience="me"), admin, self.db)
        self.assertEqual((got["group"], got["players"]), (False, 1))
        self.group.assert_not_awaited()

    async def test_sending_to_me_without_a_way_to_receive_it_is_a_conflict(self):
        admin = self.db.get(models.User, 2)
        with self.assertRaises(HTTPException) as refused:
            await notices.recap_send(notices.RecapSendBody(period="2026-04", audience="me"), admin, self.db)
        self.assertEqual(refused.exception.status_code, 409)

    async def test_sending_to_everybody_and_to_a_quiet_month(self):
        admin = self.db.get(models.User, 1)
        got = await notices.recap_send(notices.RecapSendBody(period="2026-04", audience="all"), admin, self.db)
        self.assertEqual((got["group"], got["players"]), (True, 1))
        with self.assertRaises(HTTPException) as refused:
            await notices.recap_send(notices.RecapSendBody(period="2026-01", audience="group"), admin, self.db)
        self.assertEqual(refused.exception.status_code, 409)

    def test_the_audience_is_one_of_three(self):
        with self.assertRaises(ValueError):
            notices.RecapSendBody(period="2026-04", audience="everyone")


class PromptTests(unittest.TestCase):
    def test_it_asks_the_ai_to_keep_the_figures_the_names_and_the_link(self):
        text = ai_prompts.USES["monthly_recap"].default
        for wanted in ("tercera persona", "todas las cifras", "sin inventarte ninguna", "nombre de cada persona del podio", "enlace"):
            self.assertIn(wanted, text)


if __name__ == "__main__":
    unittest.main()
