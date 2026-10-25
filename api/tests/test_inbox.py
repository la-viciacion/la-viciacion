import datetime
import unittest
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src import auth
from src.database import models
from src.routers import notifications
from src.utils import inbox, my_utils, push, settings
from tests import clock
from tests.sqlite_db import make_session

NOW = clock.PIN


def add_user(db, user_id, username, active=True):
    db.add(models.User(id=user_id, username=username, name=username, email=f"{username}@x.test", is_active=1 if active else 0))
    db.commit()


def titles(db, user_id):
    rows = db.query(models.UserNotification).filter_by(user_id=user_id).order_by(models.UserNotification.id).all()
    return [r.title for r in rows]


class PayloadTests(unittest.TestCase):
    def test_a_message_is_shown_as_push_shows_it(self):
        got = inbox.payload_of("🏆 *Logro*\nAna ha ganado algo")
        self.assertEqual(got, {"title": "🏆 Logro", "body": "Ana ha ganado algo", "url": "/"})

    def test_a_tap_on_a_push_opens_the_inbox_but_the_inbox_does_not_link_to_itself(self):
        self.assertEqual(push.build_payload("hola")["url"], "#/notifications")
        self.assertEqual(inbox.payload_of("hola")["url"], "/")

    def test_a_one_line_message_gets_the_app_name_as_title(self):
        self.assertEqual(inbox.payload_of("Ana empieza Hades")["title"], "La Viciación")

    def test_a_push_payload_wins_over_the_text_and_keeps_its_link(self):
        got = inbox.payload_of("texto de telegram", {"title": "Resumen", "body": "Míralo", "url": "#/story", "tag": "recap"})
        self.assertEqual(got, {"title": "Resumen", "body": "Míralo", "url": "#/story"})


class GameLinksTests(unittest.TestCase):
    RAWG = "[Hades](https://rawg.io/games/hades)"

    def test_the_game_links_of_a_notice_stay_in_the_body(self):
        got = inbox.payload_of(f"*Ana* acaba de empezar {self.RAWG}, su juego número 3 de este año.")
        self.assertEqual(got["body"], f"Ana acaba de empezar {self.RAWG}, su juego número 3 de este año.")

    def test_a_link_in_the_title_line_is_left_to_the_title(self):
        got = inbox.payload_of(f"¡Hoy sale {self.RAWG}! Estaba en tu lista.\nTambién lo espera Bea.")
        self.assertEqual((got["title"], got["body"]), ("¡Hoy sale Hades! Estaba en tu lista.", "También lo espera Bea."))

    def test_a_link_that_is_not_to_a_game_is_not_kept(self):
        got = inbox.payload_of("Ana\n[Descubre el mes](https://viciacion.test/#/story)")
        self.assertEqual(got["body"], "Descubre el mes")

    def test_the_links_that_do_not_fit_go_back_to_plain_text(self):
        text = "Hola\n" +" ".join(f"[Juego{i}](https://rawg.io/games/juego-{i})" for i in range(8))
        body = inbox.payload_of(text)["body"]
        self.assertLessEqual(len(body), inbox.BODY_MAX)
        self.assertIn("Juego7", body)
        self.assertNotIn("[Juego7]", body)
        self.assertIn("[Juego0](", body)


class RecordTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        add_user(self.db, 1, "ana")
        add_user(self.db, 2, "beto")
        add_user(self.db, 3, "off", active=False)
        patcher = mock.patch.object(inbox, "SessionLocal", lambda: self.db)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_group_notice_reaches_every_active_player(self):
        inbox.record_group("Ana ha perdido la racha")
        self.assertEqual(titles(self.db, 1), ["La Viciación"])
        self.assertEqual(titles(self.db, 2), ["La Viciación"])
        self.assertEqual(titles(self.db, 3), [])

    def test_a_private_notice_reaches_only_its_player(self):
        inbox.record_user(2, "Tu resumen\nHoras: 3")
        self.assertEqual(titles(self.db, 1), [])
        self.assertEqual(titles(self.db, 2), ["Tu resumen"])

    def test_an_admin_notice_follows_the_audience_of_the_composer(self):
        notice = {"title": "Aviso", "body": "", "url": "/"}
        inbox.record_audience("me", 1, notice)
        self.assertEqual((len(titles(self.db, 1)), len(titles(self.db, 2))), (1, 0))
        inbox.record_audience("group", 1, notice)
        self.assertEqual((len(titles(self.db, 1)), len(titles(self.db, 2))), (2, 1))

    def test_a_failure_is_logged_and_never_raised(self):
        with mock.patch.object(inbox, "SessionLocal", side_effect=RuntimeError("db down")):
            inbox.record_group("hola")
            inbox.record_user(1, "hola")

    def test_purge_deletes_only_what_is_older_than_the_retention(self):
        for days in (20, 15, 13, 1):
            self.db.add(models.UserNotification(user_id=1, title=f"{days}d", created_at=NOW - datetime.timedelta(days=days)))
        self.db.commit()
        with mock.patch.object(settings, "get", return_value=14):
            self.assertEqual(inbox.purge(self.db, NOW), 2)
        self.assertEqual(titles(self.db, 1), ["13d", "1d"])

    def test_the_retention_is_a_whole_number_of_days_between_1_and_365(self):
        self.assertEqual(settings.coerce("inbox.retention_days", 30), 30)
        for bad in (0, 366, "x"):
            with self.assertRaises(ValueError):
                settings.coerce("inbox.retention_days", bad)
        self.assertEqual(settings.REGISTRY["inbox.retention_days"].default, 14)


class SenderTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        values = {"notifications.enabled": True, "telegram.token": None, "telegram.group_id": None}
        self.values = values
        for patcher in (
            mock.patch.object(settings, "get", side_effect=lambda key: self.values.get(key)),
            mock.patch.object(my_utils.push, "is_ready", return_value=True),
            mock.patch.object(my_utils.push, "notify_group", new=mock.AsyncMock()),
            mock.patch.object(my_utils.push, "notify_user", new=mock.AsyncMock()),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        group = mock.patch.object(inbox, "record_group")
        user = mock.patch.object(inbox, "record_user")
        self.record_group, self.record_user = group.start(), user.start()
        self.addCleanup(group.stop)
        self.addCleanup(user.stop)

    async def test_a_group_notice_is_recorded(self):
        await my_utils.send_message("hola", False)
        self.record_group.assert_called_once_with("hola", None)

    async def test_a_silent_group_notice_is_not(self):
        await my_utils.send_message("hola", True)
        self.record_group.assert_not_called()

    async def test_nothing_is_recorded_with_the_notifications_switch_off(self):
        self.values["notifications.enabled"] = False
        await my_utils.send_message("hola", False)
        await my_utils.send_message_to_user(None, "hola", user_id=1)
        self.record_group.assert_not_called()
        self.record_user.assert_not_called()

    async def test_a_private_notice_is_recorded_even_without_push_or_telegram(self):
        await my_utils.send_message_to_user(None, "hola", user_id=1, push_on=False, telegram_on=False)
        self.record_user.assert_called_once_with(1, "hola", None)

    async def test_a_notice_that_only_matters_now_is_not(self):
        await my_utils.send_message_to_user(None, "tu timer", user_id=1, in_inbox=False)
        self.record_user.assert_not_called()


class RouteTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session(threads=True)
        add_user(self.db, 1, "ana")
        add_user(self.db, 2, "beto")
        app = FastAPI()
        app.include_router(notifications.router)
        current = self.db.get(models.User, 1)
        app.dependency_overrides[auth.get_current_active_user] = lambda: current
        app.dependency_overrides[auth.get_db] = lambda: self.db
        self.client = TestClient(app)
        for user_id, title, days in ((1, "viejo", 2), (1, "nuevo", 1), (2, "de beto", 1)):
            self.db.add(models.UserNotification(user_id=user_id, title=title, created_at=NOW - datetime.timedelta(days=days)))
        self.db.commit()

    def test_it_lists_only_the_callers_notices_newest_first(self):
        data = self.client.get("/notifications/").json()
        self.assertEqual([i["title"] for i in data["items"]], ["nuevo", "viejo"])
        self.assertEqual(data["unread"], 2)

    def test_reading_clears_the_unread_count_but_keeps_the_notices(self):
        self.client.post("/notifications/read")
        data = self.client.get("/notifications/").json()
        self.assertEqual((data["unread"], len(data["items"])), (0, 2))
        self.assertEqual(self.client.get("/notifications/unread").json(), {"unread": 0})

    def test_one_notice_is_deleted_but_not_somebody_elses(self):
        mine = self.db.query(models.UserNotification).filter_by(title="nuevo").one().id
        theirs = self.db.query(models.UserNotification).filter_by(title="de beto").one().id
        self.assertEqual(self.client.delete(f"/notifications/{mine}").status_code, 200)
        self.assertEqual(self.client.delete(f"/notifications/{theirs}").status_code, 404)
        self.assertEqual(titles(self.db, 2), ["de beto"])

    def test_emptying_the_inbox_leaves_the_others_alone(self):
        self.assertEqual(self.client.delete("/notifications/").json(), {"deleted": 2})
        self.assertEqual(titles(self.db, 1), [])
        self.assertEqual(titles(self.db, 2), ["de beto"])


if __name__ == "__main__":
    unittest.main()
