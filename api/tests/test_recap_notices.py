"""The notice of the recap: what it says, where it goes, and the periods the jobs report on."""
import datetime
import unittest
from unittest import mock

from fastapi import HTTPException

from src.crud import recap
from src.database import models
from src.routers.manage import notices
from src.utils import recap_notices, scheduler
from tests.sqlite_db import make_session

HOUR = 3600
D = datetime.datetime
APRIL = recap.parse_period("2026-04")  # the pinned clock is in June 2026: April is over


def session(user, game, start, hours):
    return models.GameTimer(
        user_id=user, game_id=game, start_time=start, end_time=start + datetime.timedelta(hours=hours),
        duration_seconds=hours * HOUR, is_active=False,
    )


class PeriodTests(unittest.TestCase):
    def test_a_month_and_a_season_are_named(self):
        self.assertEqual(recap_notices.period_label(APRIL), "abril de 2026")
        self.assertEqual(recap_notices.period_label(recap.parse_period("2026")), "temporada 2026")

    def test_the_monthly_job_reports_on_the_month_before_its_slot(self):
        self.assertEqual(recap_notices.previous_month(datetime.date(2026, 10, 1)).key, "2026-09")
        self.assertEqual(recap_notices.previous_month(datetime.date(2027, 1, 1)).key, "2026-12")

    def test_the_annual_job_reports_on_the_running_season_in_december_and_the_one_that_ended_in_january(self):
        self.assertEqual(recap_notices.annual_period(datetime.date(2026, 12, 24)).key, "2026")
        self.assertEqual(recap_notices.annual_period(datetime.date(2027, 1, 3)).key, "2026")
        self.assertEqual(recap_notices.annual_period(datetime.date(2026, 12, 20)).kind, "year")


class RecapData(unittest.IsolatedAsyncioTestCase):
    """A month of sessions in a database and the senders replaced by mocks."""

    def setUp(self):
        self.db = make_session()
        self.db.add_all([
            models.User(id=1, name="Ana_", username="ana", is_active=1, telegram_id=11),
            models.User(id=2, name="Biel", username="biel", is_active=1, telegram_id=None),
            models.Game(id="doom", name="Doom"),
            session(1, "doom", D(2026, 4, 10, 20), 3),
            session(2, "doom", D(2026, 4, 10, 21), 1),
        ])
        self.db.commit()
        self.group = mock.AsyncMock()
        self.private = mock.AsyncMock()
        for name, value in (("send_message", self.group), ("send_message_to_user", self.private)):
            patcher = mock.patch.object(recap_notices.utils, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)


class NoticeTests(RecapData):
    def test_the_telegram_text_says_it_is_ready_and_links_to_the_story_without_any_figure(self):
        with mock.patch.object(recap_notices.config, "PUBLIC_URL", "https://viciacion.example"):
            text = recap_notices.telegram_text(APRIL)
        self.assertEqual(
            text,
            "🎬 *Ya está disponible el resumen mensual*\n\n[Descubre cómo ha ido el mes](https://viciacion.example/#/story/2026-04)",
        )
        self.assertNotRegex(text, r"\d\dh\d\d")  # no hours, no names, no podium

    def test_without_a_public_address_there_is_no_link(self):
        with mock.patch.object(recap_notices.config, "PUBLIC_URL", ""):
            text = recap_notices.telegram_text(APRIL)
        self.assertNotIn("](", text)
        self.assertIn("Ya está disponible el resumen mensual", text)

    def test_the_push_is_the_same_notice_and_opens_the_story(self):
        payload = recap_notices.push_payload(APRIL)
        self.assertEqual(payload["title"], "🎬 Ya está disponible el resumen mensual")
        self.assertEqual((payload["url"], payload["tag"]), ("#/story/2026-04", "recap-2026-04"))

    def test_a_season_says_annual_and_neither_notice_names_the_period(self):
        season = recap.parse_period("2026")
        self.assertIn("resumen anual", recap_notices.telegram_text(season))
        self.assertIn("resumen anual", recap_notices.push_payload(season)["title"])
        self.assertEqual(recap_notices.push_payload(season)["body"], "Descubre cómo ha ido el año")
        with mock.patch.object(recap_notices.config, "PUBLIC_URL", "https://viciacion.example"):
            self.assertIn("[Descubre cómo ha ido el año](https://viciacion.example/#/story/2026)", recap_notices.telegram_text(season))
        for period in (APRIL, season):
            for text in (recap_notices.telegram_text(period).split("\n")[0], recap_notices.push_payload(period)["title"]):
                self.assertNotRegex(text, r"\d{4}|abril|temporada", period.key)
            self.assertIn(period.key, recap_notices.push_payload(period)["url"])  # the link still says which one it is

    async def test_it_goes_once_to_the_group_with_the_push_notice_and_to_nobody_in_private(self):
        result = await recap_notices.announce_recap(self.db, APRIL)
        self.assertEqual(result, {"empty": False})
        self.group.assert_awaited_once()
        self.assertEqual(self.group.await_args.args[0], recap_notices.telegram_text(APRIL))
        self.assertEqual(self.group.await_args.kwargs["push_payload"], recap_notices.push_payload(APRIL))
        self.assertNotIn("ai_use", self.group.await_args.kwargs)  # the AI does not touch it: there is nothing to word
        self.private.assert_not_awaited()

    async def test_a_test_goes_to_the_admin_alone_by_telegram_and_push(self):
        admin = self.db.get(models.User, 1)
        result = await recap_notices.announce_recap(self.db, APRIL, only=admin)
        self.assertEqual(result, {"empty": False})
        self.group.assert_not_awaited()
        self.private.assert_awaited_once()
        self.assertEqual(self.private.await_args.args, (11, recap_notices.telegram_text(APRIL)))
        self.assertEqual(self.private.await_args.kwargs, {"user_id": 1, "push_payload": recap_notices.push_payload(APRIL)})

    async def test_a_period_nobody_played_sends_nothing(self):
        result = await recap_notices.announce_recap(self.db, recap.parse_period("2026-01"))
        self.assertEqual(result, {"empty": True})
        self.group.assert_not_awaited()
        self.private.assert_not_awaited()
        self.assertEqual(recap_notices.describe(result), "nobody played")

    async def test_only_the_emergency_accounts_sessions_are_not_somebody_playing(self):
        self.db.add(models.User(id=9, name="Admin", username=models.GOD_USERNAME, is_active=1))
        self.db.add(session(9, "doom", D(2026, 3, 5, 20), 5))
        self.db.commit()
        self.assertFalse(recap.anyone_played(self.db, recap.parse_period("2026-03")))
        self.assertTrue(recap.anyone_played(self.db, APRIL))

    def test_the_status_of_a_run(self):
        self.assertEqual(recap_notices.describe({"empty": False}), "sent to the group")
        self.assertEqual(recap_notices.describe({"empty": False}, only=True), "sent to the admin")


class JobTests(RecapData):
    """What the scheduler's jobs report on, with the notice itself replaced."""

    async def run_job(self, job, slot):
        sent = []

        async def fake(db, period, **kwargs):
            sent.append(period.key)
            return {"empty": False}

        with mock.patch.object(scheduler.recap_notices, "announce_recap", fake):
            status = await job(self.db, slot)
        return sent, status

    async def test_the_monthly_job_sends_the_month_before_its_slot(self):
        sent, status = await self.run_job(scheduler._monthly_recap, D(2026, 10, 1, 10))
        self.assertEqual((sent, status), (["2026-09"], "2026-09: sent to the group"))

    async def test_in_january_the_monthly_job_sends_only_december(self):
        sent, _ = await self.run_job(scheduler._monthly_recap, D(2027, 1, 1, 10))
        self.assertEqual(sent, ["2026-12"])

    async def test_the_annual_job_sends_the_season_in_december_and_in_january(self):
        december, _ = await self.run_job(scheduler._annual_recap, D(2026, 12, 24, 10))
        january, status = await self.run_job(scheduler._annual_recap, D(2027, 1, 2, 10))
        self.assertEqual((december, january), (["2026"], ["2026"]))
        self.assertEqual(status, "2026: sent to the group")


class EndpointTests(RecapData):
    """The admin routes over the same data (called as functions: the router-level security is in test_endpoint_security)."""

    def test_the_preview_gives_the_notice_without_sending_anything(self):
        got = notices.recap_preview("2026-04", self.db)
        self.assertEqual((got["period"], got["label"], got["nobody_played"]), ("2026-04", "abril de 2026", False))
        self.assertIn("Ya está disponible el resumen mensual", got["telegram"])
        self.assertEqual(got["push"]["url"], "#/story/2026-04")
        self.assertEqual(got["push"]["body"], "Descubre cómo ha ido el mes")
        self.group.assert_not_awaited()

    def test_the_preview_of_a_quiet_period_says_so(self):
        self.assertTrue(notices.recap_preview("2026-01", self.db)["nobody_played"])

    def test_a_wrong_or_future_period_is_refused(self):
        for period in ("2026-13", "x"):
            with self.assertRaises(HTTPException) as refused:
                notices.recap_preview(period, self.db)
            self.assertEqual(refused.exception.status_code, 400)
        with self.assertRaises(HTTPException):
            notices.recap_preview(str(datetime.date.today().year + 1), self.db)

    async def test_sending_to_me_reaches_only_the_admin(self):
        admin = self.db.get(models.User, 1)
        got = await notices.recap_send(notices.RecapSendBody(period="2026-04", audience="me"), admin, self.db)
        self.assertEqual(got["message"], "Enviado a ti")
        self.group.assert_not_awaited()
        self.private.assert_awaited_once()

    async def test_sending_to_me_without_a_way_to_receive_it_is_a_conflict(self):
        admin = self.db.get(models.User, 2)
        with mock.patch.object(notices.actions, "push_has_devices", return_value=False), self.assertRaises(HTTPException) as refused:
            await notices.recap_send(notices.RecapSendBody(period="2026-04", audience="me"), admin, self.db)
        self.assertEqual(refused.exception.status_code, 409)

    async def test_sending_to_the_group_and_to_a_quiet_period(self):
        admin = self.db.get(models.User, 1)
        got = await notices.recap_send(notices.RecapSendBody(period="2026-04", audience="group"), admin, self.db)
        self.assertEqual(got["message"], "Enviado al grupo")
        self.group.assert_awaited_once()
        with self.assertRaises(HTTPException) as refused:
            await notices.recap_send(notices.RecapSendBody(period="2026-01", audience="group"), admin, self.db)
        self.assertEqual(refused.exception.status_code, 409)

    def test_the_audience_is_me_or_the_group(self):
        for audience in ("all", "everyone", ""):
            with self.assertRaises(ValueError):
                notices.RecapSendBody(period="2026-04", audience=audience)


if __name__ == "__main__":
    unittest.main()
