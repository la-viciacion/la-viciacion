import asyncio
import types
import unittest
from unittest import mock

from fastapi import HTTPException

from src.database import models
from src.routers import manage
from src.utils import my_utils
from tests.sqlite_db import make_session

ADMIN = types.SimpleNamespace(id=1, username="boss", telegram_id=111)


class TextTests(unittest.TestCase):
    def test_title_in_bold_then_the_message_with_markdown_escaped(self):
        self.assertEqual(my_utils.announcement_text("Hola_mundo", "un *aviso*"), "*Hola\_mundo*\n\nun \*aviso\*")

    def test_without_a_message_it_is_only_the_title(self):
        self.assertEqual(my_utils.announcement_text("Hola", None), "*Hola*")
        self.assertEqual(my_utils.announcement_text("Hola", "  "), "*Hola*")


class EndpointTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        self.db.add_all([
            models.User(id=2, name="Bob", username="bob", is_active=1, telegram_id=222),
            models.User(id=3, name="Cris", username="cris", is_active=1),
        ])
        self.db.commit()
        values = {"telegram.token": "tok", "telegram.group_id": "-100"}
        patch = mock.patch.object(manage.settings, "get", side_effect=lambda key: values.get(key))
        patch.start()
        self.addCleanup(patch.stop)
        self.values = values
        send = mock.patch.object(manage.my_utils, "send_announcement_to_chat", mock.AsyncMock(return_value=True))
        self.send = send.start()
        self.addCleanup(send.stop)

    def post(self, **body):
        body = manage.TelegramAnnouncementBody(title="Hola", **body)
        return asyncio.run(manage.send_telegram_announcement(body, ADMIN, self.db))

    def refused(self, status, **body):
        with self.assertRaises(HTTPException) as ctx:
            self.post(**body)
        self.assertEqual(ctx.exception.status_code, status, ctx.exception.detail)
        self.send.assert_not_called()

    def test_each_audience_goes_to_its_chat(self):
        for body, chat in (({"audience": "me"}, 111), ({"audience": "user", "user_id": 2}, 222), ({"audience": "group"}, "-100")):
            self.send.reset_mock()
            self.post(**body)
            self.assertEqual(self.send.call_args.args[0], chat)

    def test_without_a_bot_nothing_is_sent(self):
        del self.values["telegram.token"]
        self.refused(409, audience="group")

    def test_a_group_needs_its_id(self):
        del self.values["telegram.group_id"]
        self.refused(409, audience="group")

    def test_a_user_without_telegram_id_is_refused_by_name(self):
        with self.assertRaises(HTTPException) as ctx:
            self.post(audience="user", user_id=3)
        self.assertIn("cris", ctx.exception.detail)

    def test_a_user_must_be_chosen_and_exist(self):
        self.refused(400, audience="user")
        self.refused(404, audience="user", user_id=99)

    def test_telegram_refusing_the_message_is_reported(self):
        self.send.return_value = False
        with self.assertRaises(HTTPException) as ctx:
            self.post(audience="group")
        self.assertEqual(ctx.exception.status_code, 502)

    def test_the_composer_cannot_send_to_everybody_by_telegram(self):
        with self.assertRaises(ValueError):
            manage.TelegramAnnouncementBody(title="x", audience="all")


if __name__ == "__main__":
    unittest.main()
