"""Messages and reminders the application sends on its own (MariaDB required, see api_support.py): Telegram
delivery with retries, forgotten timers, the pinned notification of a running timer and the weekly summary.
Telegram is replaced by a fake bot, push by recorders: the real code decides what is sent and to whom."""
import asyncio
import datetime
from datetime import timedelta
from unittest import mock

import telegram
from sqlalchemy import text

from src.database import database, models
from src.utils import actions, ai, my_utils, push, user_settings
from tests.api_support import ApiTestCase

TOKEN = "123456789:" + "A" * 30
GROUP = "-100123"


class FakeBot:
    """A stand-in for telegram.Bot: records what it is asked to send and fails as scripted."""

    sent: list = []
    failures: list = []  # exceptions raised by the next sends, in order

    def __init__(self, token):
        self.token = token

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def _next_failure(self):
        if FakeBot.failures:
            raise FakeBot.failures.pop(0)

    async def send_message(self, text, chat_id, parse_mode=None):
        self._next_failure()
        FakeBot.sent.append({"kind": "text", "chat_id": chat_id, "text": text, "parse_mode": parse_mode})

    async def send_photo(self, chat_id, photo, caption, parse_mode=None):
        self._next_failure()
        FakeBot.sent.append({"kind": "photo", "chat_id": chat_id, "photo": photo, "text": caption, "parse_mode": parse_mode})


class MessagingTestCase(ApiTestCase):
    def setUp(self):
        super().setUp()
        FakeBot.sent, FakeBot.failures = [], []
        self.push_calls = []

        async def notify_group(message):
            self.push_calls.append(("group", message))

        async def notify_user(user_id, message, tag=None):
            self.push_calls.append(("user", user_id, message, tag))

        for patcher in (
            mock.patch.object(telegram, "Bot", new=FakeBot),
            mock.patch.object(push, "notify_group", new=notify_group),
            mock.patch.object(push, "notify_user", new=notify_user),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.ana = self.user("ana", telegram_id=111)

    def configure_telegram(self, group=True):
        values = {"telegram.token": TOKEN}
        if group:
            values["telegram.group_id"] = GROUP
        self.set_settings(**values)

    async def say(self, message, silent=False, **kwargs):
        await my_utils.send_message(message, silent, **kwargs)

    def run_async(self, coroutine):
        return asyncio.run(coroutine)


class GroupMessageTests(MessagingTestCase):
    def test_a_notice_goes_to_the_group_as_markdown_and_to_the_devices(self):
        self.configure_telegram()
        self.run_async(self.say("*Hello* group"))
        self.assertEqual(FakeBot.sent, [{"kind": "text", "chat_id": GROUP, "text": "*Hello* group", "parse_mode": telegram.constants.ParseMode.MARKDOWN}])
        self.assertEqual(self.push_calls, [("group", "*Hello* group")])

    def test_a_silent_notice_is_not_sent_anywhere(self):
        self.configure_telegram()
        self.run_async(self.say("quiet", silent=True))
        self.assertEqual((FakeBot.sent, self.push_calls), ([], []))

    def test_the_general_switch_stops_everything(self):
        self.configure_telegram()
        self.set_settings(**{"notifications.enabled": False})
        self.run_async(self.say("nothing"))
        self.assertEqual((FakeBot.sent, self.push_calls), ([], []))

    def test_without_telegram_and_without_push_nothing_is_sent(self):
        self.run_async(self.say("nowhere to go"))
        self.assertEqual((FakeBot.sent, self.push_calls), ([], []))

    def test_with_push_only_the_devices_get_it(self):
        with mock.patch.object(push, "is_ready", return_value=True):
            self.run_async(self.say("push only"))
        self.assertEqual((FakeBot.sent, self.push_calls), ([], [("group", "push only")]))

    def test_an_image_is_sent_as_a_photo_with_the_text_as_caption(self):
        self.configure_telegram()
        self.run_async(self.say("🏆 title", image=b"\x89PNG..."))
        self.assertEqual((FakeBot.sent[0]["kind"], FakeBot.sent[0]["photo"], FakeBot.sent[0]["text"]), ("photo", b"\x89PNG...", "🏆 title"))

    def test_a_message_telegram_cannot_parse_is_sent_again_as_plain_text(self):
        self.configure_telegram()
        FakeBot.failures = [telegram.error.BadRequest("Can't parse entities")]
        self.run_async(self.say("broken *markdown"))
        self.assertEqual([(m["text"], m["parse_mode"]) for m in FakeBot.sent], [("broken *markdown", None)])

    def test_a_message_rejected_twice_is_dropped(self):
        self.configure_telegram()
        FakeBot.failures = [telegram.error.BadRequest("Can't parse entities"), telegram.error.BadRequest("chat not found")]
        self.run_async(self.say("hopeless"))
        self.assertEqual(FakeBot.sent, [])

    def test_a_network_error_is_retried_and_then_given_up_without_raising(self):
        self.configure_telegram()
        FakeBot.failures = [TimeoutError("slow")] * 3
        self.run_async(self.say("lost"))
        self.assertEqual(FakeBot.sent, [])
        FakeBot.failures = [TimeoutError("slow")]
        self.run_async(self.say("second time lucky"))
        self.assertEqual([m["text"] for m in FakeBot.sent], ["second time lucky"])

    def test_telegram_unreachable_when_the_session_opens_does_not_raise(self):
        self.configure_telegram()
        with mock.patch.object(telegram, "Bot", side_effect=OSError("no route")):
            self.run_async(self.say("still fine"))

    def test_a_recommended_game_is_added_as_a_line_when_the_ai_does_not_rewrite(self):
        self.configure_telegram()
        self.run_async(self.say("Ana completed it", new_game_recommended={"game": "Half_Life", "user": "Bea"}))
        text = FakeBot.sent[0]["text"]
        self.assertTrue(text.startswith("Ana completed it"))
        self.assertIn("¿Te apetece probar *Half\\_Life*? Lo tiene Bea.", text)  # underscores escaped for Markdown

    def test_the_ai_rewrites_the_notice_when_it_is_on_for_that_use_and_the_recommendation_goes_with_it(self):
        self.configure_telegram()
        with mock.patch.object(ai, "is_ready", return_value=True), mock.patch.object(ai, "prompt_for", return_value="prompt") as prompt, \
             mock.patch.object(ai, "complete", return_value="¡Rewritten!") as complete:
            self.run_async(self.say("original", ai_use="completed_game", new_game_recommended={"game": "Hades", "user": "Bea"}))
        self.assertEqual(FakeBot.sent[0]["text"], "¡Rewritten!")
        prompt.assert_called_once_with("completed_game", {"game": "Hades", "user": "Bea"})
        self.assertEqual(complete.call_args.args, ("prompt", "original"))

    def test_a_failing_ai_falls_back_to_the_original_text(self):
        self.configure_telegram()
        with mock.patch.object(ai, "is_ready", return_value=True), mock.patch.object(ai, "prompt_for", return_value="p"), \
             mock.patch.object(ai, "complete", side_effect=RuntimeError("quota")):
            self.run_async(self.say("original", ai_use="completed_game"))
        self.assertEqual(FakeBot.sent[0]["text"], "original")


class PrivateMessageTests(MessagingTestCase):
    def send(self, telegram_id=111, user_id=None, message="Hi"):
        self.run_async(my_utils.send_message_to_user(telegram_id, message, user_id=user_id))

    def test_a_private_notice_goes_to_the_user_s_chat_and_devices(self):
        self.configure_telegram()
        self.send(user_id=self.ana)
        self.assertEqual([(m["chat_id"], m["text"]) for m in FakeBot.sent], [(111, "Hi")])
        self.assertEqual(self.push_calls, [("user", self.ana, "Hi", "private")])

    def test_without_a_telegram_id_or_a_bot_only_the_devices_are_tried(self):
        self.configure_telegram()
        self.send(telegram_id=None, user_id=self.ana)
        self.assertEqual((FakeBot.sent, len(self.push_calls)), ([], 1))
        self.set_settings(**{"telegram.token": TOKEN})  # bot still configured; now remove the token
        with mock.patch.object(my_utils.settings, "get", side_effect=lambda key: {"notifications.enabled": True}.get(key)):
            self.send()
        self.assertEqual(FakeBot.sent, [])

    def test_the_general_switch_applies_to_private_notices_too(self):
        self.configure_telegram()
        self.set_settings(**{"notifications.enabled": False})
        self.send(user_id=self.ana)
        self.assertEqual((FakeBot.sent, self.push_calls), ([], []))


class AdminAlertTests(MessagingTestCase):
    def alert(self, message="boom"):
        async def run():
            with database.SessionLocal() as db:
                await my_utils.send_message_to_admins(db, message)
        self.run_async(run())

    def test_alerts_go_to_the_admins_that_have_a_telegram_id(self):
        self.configure_telegram()
        self.user("root", admin=True, telegram_id=777)
        self.user("boss", admin=True)  # an admin without Telegram
        self.alert()
        self.assertEqual([(m["chat_id"], m["text"]) for m in FakeBot.sent], [(777, "boom")])

    def test_players_do_not_receive_alerts(self):
        self.configure_telegram()
        self.alert()
        self.assertEqual(FakeBot.sent, [])

    def test_the_alerts_switch_and_the_missing_bot_stop_them(self):
        self.user("root", admin=True, telegram_id=777)
        self.alert()  # no token
        self.configure_telegram()
        self.set_settings(**{"notifications.admin_alerts": False})
        self.alert()
        self.assertEqual(FakeBot.sent, [])


class AnnouncementAndTestMessageTests(MessagingTestCase):
    def test_the_announcement_escapes_whatever_an_admin_types(self):
        self.assertEqual(my_utils.announcement_text("  Big_news  ", "A *bold* claim_"), "*Big\\_news*\n\nA \\*bold\\* claim\\_")
        self.assertEqual(my_utils.announcement_text("Only a title"), "*Only a title*")

    def test_an_announcement_goes_to_one_chat_even_with_the_switch_off(self):
        self.configure_telegram()
        self.set_settings(**{"notifications.enabled": False})
        self.assertTrue(self.run_async(my_utils.send_announcement_to_chat(GROUP, "Title", "Body")))
        self.assertEqual(FakeBot.sent[0]["chat_id"], GROUP)
        FakeBot.failures = [telegram.error.BadRequest("x"), telegram.error.BadRequest("y")]
        self.assertFalse(self.run_async(my_utils.send_announcement_to_chat(GROUP, "Title")))

    def test_the_test_message_needs_the_token_and_the_group_and_names_who_sent_it(self):
        with self.assertRaises(ValueError):
            self.run_async(my_utils.send_test_message("root"))
        self.configure_telegram()
        self.run_async(my_utils.send_test_message("root"))
        self.assertIn("enviado por root", FakeBot.sent[0]["text"])


class ForgottenTimerTests(MessagingTestCase):
    def setUp(self):
        super().setUp()
        self.configure_telegram()
        self.game("celeste", "Celeste")
        self.reminders = []
        self.channels = []

        async def to_user(telegram_id, message, user_id=None, telegram_on=True, push_on=True):
            self.reminders.append((telegram_id, message, user_id))
            self.channels.append((telegram_on, push_on))

        patcher = mock.patch.object(my_utils, "send_message_to_user", new=to_user)
        patcher.start()
        self.addCleanup(patcher.stop)

    def running_timer(self, hours_ago, user_id=None):
        with database.SessionLocal() as db:
            db.add(models.GameTimer(user_id=user_id or self.ana, game_id="celeste", start_time=datetime.datetime.now() - timedelta(hours=hours_ago),
                                    is_active=True, platform="pc"))
            db.commit()

    def check(self, username="ana"):
        async def run():
            with database.SessionLocal() as db:
                await actions.check_forgotten_timer(db, db.query(models.User).filter_by(username=username).one())
        self.run_async(run())

    def test_a_timer_that_crossed_the_default_limit_in_the_last_hour_is_reminded_once(self):
        self.running_timer(hours_ago=user_settings.DEFAULT_FORGOTTEN_TIMER_HOURS + 0.5)
        self.check()
        self.assertEqual(len(self.reminders), 1)
        telegram_id, message, user_id = self.reminders[0]
        self.assertEqual((telegram_id, user_id), (111, self.ana))
        self.assertIn("Hola, Ana", message)
        self.assertIn(f"más de {user_settings.DEFAULT_FORGOTTEN_TIMER_HOURS} horas", message)

    def test_a_timer_that_is_not_old_enough_or_was_already_reminded_about_is_left_alone(self):
        self.running_timer(hours_ago=1)
        self.check()
        self.assertEqual(self.reminders, [])
        with self.engine.begin() as conn:
            conn.execute(text("DELETE FROM game_timers"))
        self.running_timer(hours_ago=user_settings.DEFAULT_FORGOTTEN_TIMER_HOURS + 3)  # crossed the line hours ago
        self.check()
        self.assertEqual(self.reminders, [])

    def test_the_limit_is_the_user_s_own_and_one_hour_is_singular(self):
        self.api("PATCH", "/users/ana/settings", as_user="ana", json={"forgotten_timer_hours": 1})
        self.running_timer(hours_ago=1.5)
        self.check()
        self.assertIn("más de 1 hora.", self.reminders[0][1])

    def test_a_user_that_cannot_be_reached_is_not_checked(self):
        no_contact = self.user("loner")
        self.running_timer(hours_ago=user_settings.DEFAULT_FORGOTTEN_TIMER_HOURS + 0.5, user_id=no_contact)
        self.check("loner")
        self.assertEqual(self.reminders, [])

    def test_a_user_with_only_a_push_device_is_reminded(self):
        device_only = self.user("pushy")
        with self.engine.begin() as conn:
            conn.execute(text("INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth) VALUES (:u, 'https://p/x', 'k', 'a')"), {"u": device_only})
        self.running_timer(hours_ago=user_settings.DEFAULT_FORGOTTEN_TIMER_HOURS + 0.5, user_id=device_only)
        with mock.patch.object(push, "is_ready", return_value=True):
            self.check("pushy")
        self.assertEqual(len(self.reminders), 1)


    def device(self, user_id):
        with self.engine.begin() as conn:
            conn.execute(text("INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth) VALUES (:u, 'https://p/y', 'k', 'a')"), {"u": user_id})

    def test_the_notice_goes_only_through_the_channels_the_user_left_on(self):
        self.device(self.ana)
        self.api("PATCH", "/users/ana/settings", as_user="ana", json={"forgotten_timer_telegram": False})
        self.running_timer(hours_ago=user_settings.DEFAULT_FORGOTTEN_TIMER_HOURS + 0.5)
        with mock.patch.object(push, "is_ready", return_value=True):
            self.check()
        self.assertEqual(self.channels, [(False, True)])

    def test_with_both_channels_off_nothing_is_sent(self):
        self.api("PATCH", "/users/ana/settings", as_user="ana", json={"forgotten_timer_telegram": False, "forgotten_timer_push": False})
        self.running_timer(hours_ago=user_settings.DEFAULT_FORGOTTEN_TIMER_HOURS + 0.5)
        self.check()
        self.assertEqual(self.reminders, [])

    def test_a_channel_the_user_cannot_be_reached_by_does_not_count(self):
        self.api("PATCH", "/users/ana/settings", as_user="ana", json={"forgotten_timer_telegram": False})  # ana has no push device
        self.running_timer(hours_ago=user_settings.DEFAULT_FORGOTTEN_TIMER_HOURS + 0.5)
        self.check()
        self.assertEqual(self.reminders, [])


class TimerNoticeTests(MessagingTestCase):
    def setUp(self):
        super().setUp()
        self.game("celeste", "Celeste")
        self.notices = []

        async def notify_timer(user_id, game_name, start_time):
            self.notices.append((user_id, game_name, start_time))

        patcher = mock.patch.object(push, "notify_timer", new=notify_timer)
        patcher.start()
        self.addCleanup(patcher.stop)

    def running(self, user_id, minutes_ago, game="celeste"):
        started = datetime.datetime.now().replace(second=0, microsecond=0) - timedelta(minutes=minutes_ago)
        with database.SessionLocal() as db:
            db.add(models.GameTimer(user_id=user_id, game_id=game, start_time=started, is_active=True, platform="pc"))
            db.commit()
        return started

    def refresh(self, slot=None):
        async def run():
            with database.SessionLocal() as db:
                return await actions.refresh_timer_notices(db, slot or datetime.datetime.now().replace(second=0, microsecond=0))
        return self.run_async(run())

    def test_nothing_happens_while_push_is_not_ready(self):
        self.running(self.ana, 10)
        self.assertEqual(self.refresh(), "")
        self.assertEqual(self.notices, [])

    def test_a_timer_is_refreshed_every_interval_of_play_and_never_at_minute_zero(self):
        started = self.running(self.ana, 20)
        with mock.patch.object(push, "is_ready", return_value=True):
            self.assertEqual(self.refresh(started), "0 timers")  # the minute it started: shown by the start itself
            self.assertEqual(self.refresh(started + timedelta(minutes=10)), "1 timers")
            self.assertEqual(self.refresh(started + timedelta(minutes=15)), "0 timers")
            self.assertEqual(self.refresh(started + timedelta(minutes=20)), "1 timers")
        self.assertEqual([(n[0], n[1]) for n in self.notices], [(self.ana, "Celeste")] * 2)

    def test_each_user_has_their_own_interval(self):
        bea = self.user("bea")
        a = self.running(self.ana, 30)
        self.running(bea, 30)
        self.api("PATCH", "/users/bea/settings", as_user="bea", json={"timer_notice_minutes": 15})
        with mock.patch.object(push, "is_ready", return_value=True):
            self.refresh(a + timedelta(minutes=30))  # ana's default is 10: due; bea's 15: due (30 = 2 x 15)
            self.assertEqual({n[0] for n in self.notices}, {self.ana, bea})
            self.notices.clear()
            self.refresh(a + timedelta(minutes=10))  # due for ana (every 10), not for bea (every 15)
        self.assertEqual({n[0] for n in self.notices}, {self.ana})

    def test_a_single_notice_for_a_missing_timer_or_game_is_harmless(self):
        async def run():
            with database.SessionLocal() as db:
                await actions.send_timer_notice(db, None)
                started = datetime.datetime.now()
                await actions.send_timer_notice(db, models.GameTimer(user_id=self.ana, game_id="ghost", start_time=started))
        self.run_async(run())
        self.assertEqual([(n[0], n[1]) for n in self.notices], [(self.ana, "")])


class WeeklySummaryTests(MessagingTestCase):
    def setUp(self):
        super().setUp()
        self.game("celeste", "Celeste")
        self.game("hades", "Hades")
        self.private = []

        async def to_user(telegram_id, message, user_id=None):
            self.private.append((telegram_id, message, user_id))

        patcher = mock.patch.object(my_utils, "send_message_to_user", new=to_user)
        patcher.start()
        self.addCleanup(patcher.stop)

    def week_start(self, weeks_ago):
        first, _ = my_utils.get_week_range_dates(weeks_ago)
        return datetime.datetime.combine(first, datetime.time(20, 0))

    def summary(self, weeks_ago=1, silent=False):
        async def run():
            with database.SessionLocal() as db:
                user = db.query(models.User).filter_by(username="ana").one()
                return await actions.weekly_resume(db, user, weeks_ago=weeks_ago, silent=silent)
        return self.run_async(run())

    def test_the_summary_compares_a_week_with_the_one_before(self):
        last = self.week_start(1)
        self.session(self.ana, "celeste", last, 120)
        self.session(self.ana, "hades", last + timedelta(days=1), 60)
        before = self.week_start(2)
        self.session(self.ana, "celeste", before, 60)
        resume = self.summary(1)
        self.assertEqual(resume, {"hours": 10800, "sessions": "2", "games": "2", "achievements": "0"})
        telegram_id, message, user_id = self.private[0]
        self.assertEqual((telegram_id, user_id), (111, self.ana))
        self.assertIn("Horas: 03h00m (+02h00m)", message)
        self.assertIn("Sesiones: 2 (+1)", message)
        self.assertIn("Juegos: 2 (+1)", message)
        self.assertIn("Logros: 0 (=)", message)

    def test_a_worse_week_shows_negative_differences(self):
        self.session(self.ana, "celeste", self.week_start(1), 30)
        self.session(self.ana, "celeste", self.week_start(2), 120)
        self.session(self.ana, "hades", self.week_start(2) + timedelta(days=1), 60)
        self.summary(1)
        message = self.private[0][1]
        self.assertIn("Horas: 00h30m (-02h30m)", message)
        self.assertIn("Sesiones: 1 (-1)", message)
        self.assertIn("Juegos: 1 (-1)", message)

    def test_the_achievements_of_the_week_are_counted(self):
        self.session(self.ana, "celeste", self.week_start(1), 30)
        achievement = self.scalar("SELECT id FROM achievements ORDER BY id LIMIT 1")
        with self.engine.begin() as conn:
            conn.execute(text("INSERT INTO users_achievements (user_id, achievement_id, date) VALUES (:u, :a, :d)"),
                         {"u": self.ana, "a": achievement, "d": self.week_start(1).date()})
        self.assertEqual(self.summary(1)["achievements"], "1")
        self.assertIn("Logros: 1 (+1)", self.private[0][1])

    def test_a_quiet_week_is_all_zeros(self):
        resume = self.summary(1)
        self.assertEqual((resume["hours"], resume["sessions"], resume["games"]), (0, "0", "0"))
        self.assertIn("Horas: 00h00m (=)", self.private[0][1])

    def test_a_silent_summary_is_computed_but_not_sent(self):
        self.session(self.ana, "celeste", self.week_start(1), 30)
        self.assertEqual(self.summary(1, silent=True)["sessions"], "1")
        self.assertEqual(self.private, [])

    def test_a_failure_is_logged_not_raised(self):
        with mock.patch.object(actions.time_entries, "get_weekly_resume", side_effect=RuntimeError("db down")):
            self.assertIsNone(self.summary(1))
        self.assertEqual(self.private, [])
