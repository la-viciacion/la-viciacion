"""The admin panel's operations (overview, RAWG sync, settings, announcements, diagnostics) through real requests
(MariaDB required, see api_support.py). Its data routes are in test_mariadb_api_manage_data.py."""
import datetime
from datetime import timedelta
from unittest import mock

from src.clients.ai_error import AIError
from sqlalchemy import text

from src.database import database, models
from src.routers import manage
from src.utils import ai, email as mail, my_utils, push, rawg_sync, seasons, settings
from tests.api_support import ApiTestCase
from tests.app_routes import declared_routes, requestable

TOKEN = "123456789:" + "A" * 30
VAPID_PUBLIC = "B" * 87


def ago(**delta) -> datetime.datetime:
    return datetime.datetime.now().replace(microsecond=0) - timedelta(**delta)


class OpsTestCase(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.ana = self.user("ana")
        self.root = self.user("root", admin=True, email="root@example.com", telegram_id=777)
        self.game("celeste", "Celeste")

    def admin(self, method, path, **kwargs):
        return self.api(method, f"/manage{path}", as_user="root", **kwargs)


class EveryRouteIsAdminOnlyTests(OpsTestCase):
    """Runs every route of the panel without a token and as a player: the router-level dependency must hold."""

    def manage_routes(self):
        routes = [(m, p) for m, p in declared_routes() if p.startswith("/api/v1/manage/")]
        self.assertGreaterEqual(len(routes), 43)
        return routes

    def test_without_a_token_every_route_answers_401(self):
        for method, path in self.manage_routes():
            with self.subTest(route=f"{method} {path}"):
                self.assertEqual(self.client.request(method, requestable(path)).status_code, 401)

    def test_a_player_gets_403_on_every_route(self):
        for method, path in self.manage_routes():
            with self.subTest(route=f"{method} {path}"):
                response = self.client.request(method, requestable(path), headers=self.headers("ana"), json={})
                self.assertEqual(response.status_code, 403)

    def test_an_admin_that_was_demoted_loses_access_with_the_same_token(self):
        token = self.headers("root")
        self.assertEqual(self.api("GET", "/manage/overview", headers=token).status_code, 200)
        with self.engine.begin() as conn:
            conn.execute(text("UPDATE users SET is_admin = 0 WHERE username = 'root'"))
        self.assertEqual(self.api("GET", "/manage/overview", headers=token).status_code, 403)


class OverviewTests(OpsTestCase):
    def test_the_overview_counts_the_basics(self):
        self.session(self.ana, "celeste", ago(hours=4), 30)
        self.api("POST", "/timers/start", as_user="ana", json={"user_id": self.ana, "game_id": "celeste", "platform": "pc"})
        # starting the timer opened the library entry of that game
        self.assertEqual(self.admin("GET", "/overview").json(), {"users": 2, "games": 1, "timers": 2, "active_timers": 1, "library": 1})

    def test_attention_flags_forgotten_timers_players_without_telegram_and_games_without_rawg(self):
        self.session(self.ana, "celeste", ago(hours=30), 10)
        with database.SessionLocal() as db:
            db.add(models.GameTimer(user_id=self.ana, game_id="celeste", start_time=ago(hours=20), is_active=True, platform="pc"))
            db.commit()
        body = self.admin("GET", "/attention").json()
        self.assertEqual((body["stale_timer_hours"], body["stale_timers"]), (manage.STALE_TIMER_HOURS, 1))
        self.assertEqual((body["stale_timers_oldest"][0]["user"], body["stale_timers_oldest"][0]["game"]), ("ana", "Celeste"))
        self.assertEqual(body["users_without_telegram"], 1)  # ana; root has one
        self.assertEqual(body["games_without_rawg"], 1)

    def test_a_recent_timer_is_not_forgotten_and_the_emergency_account_is_ignored(self):
        self.api("POST", "/timers/start", as_user="ana", json={"user_id": self.ana, "game_id": "celeste", "platform": "pc"})
        self.user("admin", admin=True)  # the emergency account has no Telegram id either
        body = self.admin("GET", "/attention").json()
        self.assertEqual((body["stale_timers"], body["stale_timers_oldest"], body["users_without_telegram"]), (0, [], 1))

    def test_checking_the_achievements_runs_in_the_background(self):
        everybody = self.admin("POST", "/check-achievements", json={})
        self.assertEqual(everybody.status_code, 202)
        self.background["after_session_change"].assert_called_with(None, True)
        self.admin("POST", "/check-achievements", json={"user_id": self.ana, "silent": False})
        self.background["after_session_change"].assert_called_with(self.ana, False)

    def test_recalculating_the_achievements_needs_the_phrase_and_runs_in_the_background(self):
        recalculate = mock.patch.object(manage.achievements_recalc, "recalculate")
        with recalculate as run:
            for body in ({}, {"confirm": "si"}, {"confirm": "recalcular"}):
                self.assertIn(self.admin("POST", "/recalculate-achievements", json=body).status_code, (400, 422))
            run.assert_not_called()
            response = self.admin("POST", "/recalculate-achievements", json={"confirm": "RECALCULAR", "user_id": self.ana})
        self.assertEqual(response.status_code, 202)
        run.assert_called_once_with(self.ana)

    def test_the_preview_lists_the_changes_and_makes_none(self):
        for day in range(1, 8):
            self.session(self.ana, "celeste", datetime.datetime(seasons.current() - 1, 3, day, 10), 60)
        body = self.admin("GET", "/recalculate-achievements/preview").json()
        self.assertEqual(body["counts"], {"add": 2, "date": 0, "revoke": 0})
        self.assertEqual({c["key"] for c in body["changes"]}, {"PLAYED_7_DAYS", "STREAK_7_DAYS"})
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM users_achievements"), 0)


class RawgSyncTests(OpsTestCase):
    def test_the_estimate_counts_what_is_pending_without_calling_rawg(self):
        self.game("linked", "Linked", rawg_id=5, slug="linked", dev="Dev", release_date=datetime.date(2020, 1, 1),
                  image_url="https://i/x.jpg", genres="Indie", steam_id="1")
        body = self.admin("GET", "/rawg-sync/estimate").json()
        self.assertEqual((body["total_games"], body["without_rawg_id"], body["monthly_quota"]), (2, 1, 20000))
        self.assertGreaterEqual(body["estimated_calls"], 1)
        self.assertGreaterEqual(self.admin("GET", "/rawg-sync/estimate", params={"overwrite": True}).json()["pending_games"], body["pending_games"])

    def test_the_status_is_whatever_the_last_run_left(self):
        self.assertIsInstance(self.admin("GET", "/rawg-sync/status").json(), dict)

    def test_starting_needs_the_confirmation_phrase_and_a_sane_budget(self):
        self.assertEqual(self.admin("POST", "/rawg-sync/start", json={"confirm": "yes"}).status_code, 400)
        for calls in (0, 20001):
            self.assertEqual(self.admin("POST", "/rawg-sync/start", json={"confirm": "SINCRONIZAR", "max_calls": calls}).status_code, 400)

    def test_starting_reports_the_reasons_it_cannot(self):
        with mock.patch.object(rawg_sync, "start", side_effect=RuntimeError("No hay clave de RAWG configurada")):
            refused = self.admin("POST", "/rawg-sync/start", json={"confirm": "SINCRONIZAR"})
        self.assertEqual((refused.status_code, refused.json()["detail"]), (400, "No hay clave de RAWG configurada"))
        with mock.patch.object(rawg_sync, "start", return_value=False):
            self.assertEqual(self.admin("POST", "/rawg-sync/start", json={"confirm": "SINCRONIZAR"}).status_code, 409)

    def test_a_started_run_returns_its_status(self):
        with mock.patch.object(rawg_sync, "start", return_value=True) as start, \
             mock.patch.object(rawg_sync, "status", return_value={"state": "running"}):
            response = self.admin("POST", "/rawg-sync/start", json={"confirm": "SINCRONIZAR", "max_calls": 50, "overwrite": True})
        self.assertEqual((response.status_code, response.json()), (202, {"state": "running"}))
        start.assert_called_once_with(50, True)

    def test_cancelling_says_whether_something_was_running(self):
        with mock.patch.object(rawg_sync, "cancel", return_value=True):
            self.assertEqual(self.admin("POST", "/rawg-sync/cancel").json(), {"cancelling": True})
        with mock.patch.object(rawg_sync, "cancel", return_value=False):
            self.assertEqual(self.admin("POST", "/rawg-sync/cancel").json(), {"cancelling": False})

    def test_applying_one_game_maps_the_failures_to_status_codes(self):
        body = {"game_id": "celeste", "rawg_id": 101}
        cases = [(LookupError("Juego no encontrado"), 404), (ValueError("ya tiene otro RAWG"), 409),
                 (ConnectionError("sin red"), 502), (rawg_sync.RawgFatal("cuota agotada"), 502)]
        for error, status in cases:
            with self.subTest(error=type(error).__name__), mock.patch.object(rawg_sync, "apply_one", side_effect=error):
                response = self.admin("POST", "/rawg-sync/apply", json=body)
                self.assertEqual((response.status_code, response.json()["detail"]), (status, str(error)))
        with mock.patch.object(rawg_sync, "apply_one", return_value={"applied": ["slug"]}) as apply:
            self.assertEqual(self.admin("POST", "/rawg-sync/apply", json={**body, "overwrite": True}).json(), {"applied": ["slug"]})
        self.assertEqual(apply.call_args.args[1:], ("celeste", 101, True))


class SettingsTests(OpsTestCase):
    def test_the_settings_page_has_values_jobs_devices_mail_and_ai_uses_but_never_a_secret(self):
        self.set_settings(**{"telegram.token": TOKEN, "telegram.group_id": "-100123"})
        with database.SessionLocal() as db:
            db.add(models.JobRun(job="weekly_summary", last_run_at=ago(hours=1), last_status="ok"))
            db.commit()
        body = self.admin("GET", "/settings").json()
        self.assertEqual(body["values"]["telegram.group_id"], "-100123")
        self.assertEqual(body["values"]["telegram.token"], {"is_set": True, "hint": "…" + TOKEN[-4:]})
        self.assertNotIn(TOKEN, str(body))
        self.assertEqual(body["jobs"]["weekly_summary"]["last_status"], "ok")
        self.assertEqual(body["push_devices"], {"devices": 0, "users": 0})
        self.assertEqual(body["mail"]["test_recipient"], "root@example.com")
        self.assertTrue(body["ai_uses"])

    def test_the_telegram_settings_for_the_bot_include_the_token_and_a_version_that_follows_changes(self):
        self.set_settings(**{"telegram.token": TOKEN, "telegram.group_id": "-100123", "telegram.admin_chat_id": "42"})
        first = self.admin("GET", "/settings/telegram").json()
        self.assertEqual((first["token"], first["group_id"], first["admin_chat_id"]), (TOKEN, "-100123", "42"))
        self.set_settings(**{"telegram.group_id": "-100999"})
        self.assertNotEqual(self.admin("GET", "/settings/telegram").json()["version"], first["version"])

    def test_several_settings_change_at_once_and_only_the_changed_ones_are_reported(self):
        response = self.admin("PUT", "/settings", json={"values": {"weekly.weekday": 3, "weekly.time": "10:30", "weekly.enabled": True}})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(sorted(response.json()["changed"]), ["weekly.time", "weekly.weekday"])  # enabled was already true
        self.assertEqual((response.json()["values"]["weekly.weekday"], response.json()["values"]["weekly.time"]), (3, "10:30"))

    def test_one_invalid_value_stores_nothing(self):
        bad = self.admin("PUT", "/settings", json={"values": {"weekly.weekday": 5, "weekly.time": "25:99"}})
        self.assertEqual(bad.status_code, 400)
        self.assertIn("HH:MM", bad.json()["detail"])
        self.assertEqual(self.admin("GET", "/settings").json()["values"]["weekly.weekday"], 0)

    def test_unknown_keys_and_vapid_keys_cannot_be_written(self):
        self.assertEqual(self.admin("PUT", "/settings", json={"values": {"no.such": 1}}).status_code, 400)
        refused = self.admin("PUT", "/settings", json={"values": {"push.vapid_public": VAPID_PUBLIC}})
        self.assertEqual(refused.status_code, 400)
        self.assertIn("Generar claves", refused.json()["detail"])

    def test_a_secret_is_stored_encrypted(self):
        self.admin("PUT", "/settings", json={"values": {"telegram.token": TOKEN}})
        stored = self.scalar("SELECT value FROM app_settings WHERE `key` = 'telegram.token'")
        self.assertNotIn(TOKEN, stored)

    def test_a_resettable_prompt_goes_back_to_its_default_with_null(self):
        key = "ai.prompt." + self.admin("GET", "/settings").json()["ai_uses"][0]["id"]
        self.admin("PUT", "/settings", json={"values": {key: "Write it in pirate"}})
        self.assertEqual(self.admin("GET", "/settings").json()["values"][key], "Write it in pirate")
        self.assertEqual(self.admin("PUT", "/settings", json={"values": {key: None}}).json()["changed"], [key])
        self.assertNotEqual(self.admin("GET", "/settings").json()["values"][key], "Write it in pirate")

    def test_generating_the_push_keys(self):
        first = self.admin("POST", "/settings/push-keys")
        self.assertEqual(first.status_code, 200)
        self.assertTrue(first.json()["public_key"])
        self.assertEqual(self.admin("POST", "/settings/push-keys").status_code, 409)  # already there

    def test_replacing_the_push_keys_drops_every_subscribed_device(self):
        self.admin("POST", "/settings/push-keys")
        settings._cache.clear()
        self.api("POST", "/push/subscribe", as_user="ana",
                 json={"endpoint": "https://push.example/a", "keys": {"p256dh": "p", "auth": "a"}})
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM push_subscriptions"), 1)
        replaced = self.admin("POST", "/settings/push-keys", params={"replace": True})
        self.assertEqual(replaced.status_code, 200)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM push_subscriptions"), 0)


class PushAnnouncementTests(OpsTestCase):
    def enable_push(self):
        with database.SessionLocal() as db:
            push.ensure_vapid_keys(db)
        settings._cache.clear()

    def subscribe(self, user, endpoint, group=True):
        self.api("POST", "/push/subscribe", as_user=user, json={"endpoint": endpoint, "keys": {"p256dh": "p", "auth": "a"}, "receive_group": group})

    def announce(self, **body):
        return self.admin("POST", "/push/announce", json={"title": "Hello", **body})

    def test_the_audience_summary_without_push(self):
        body = self.admin("GET", "/push/audience").json()
        self.assertEqual((body["ready"], body["telegram"], body["all"], body["users"]), (False, {"ready": False, "group": False}, {"devices": 0, "users": 0}, {}))

    def test_the_audience_summary_counts_devices_users_and_group_preferences(self):
        self.enable_push()
        self.set_settings(**{"telegram.token": TOKEN, "telegram.group_id": "-100123"})
        self.subscribe("ana", "https://push.example/a1")
        self.subscribe("ana", "https://push.example/a2", group=False)
        self.subscribe("root", "https://push.example/r1")
        body = self.admin("GET", "/push/audience").json()
        self.assertTrue(body["ready"])
        self.assertEqual(body["telegram"], {"ready": True, "group": True})
        self.assertEqual((body["all"], body["group"]), ({"devices": 3, "users": 2}, {"devices": 2, "users": 2}))
        self.assertEqual(body["users"], {str(self.ana): 2, str(self.root): 1})

    def test_an_announcement_needs_push_to_be_ready(self):
        self.assertEqual(self.announce().status_code, 409)

    def test_it_is_validated_before_anything_is_sent(self):
        self.enable_push()
        with mock.patch.object(push, "deliver") as deliver:
            self.assertEqual(self.announce(title="x" * 81).status_code, 422)
            self.assertEqual(self.announce(url="https://evil.example/").status_code, 400)
            self.assertEqual(self.announce(image="http://insecure.example/i.png").status_code, 400)
            self.assertEqual(self.announce(audience="everyone").status_code, 422)
            self.assertEqual(self.announce(audience="user").status_code, 400)  # missing user
            self.assertEqual(self.announce(audience="user", user_id=9999).status_code, 404)
        deliver.assert_not_called()

    def test_it_goes_to_the_chosen_audience_and_reports_what_happened(self):
        self.enable_push()
        with mock.patch.object(push, "deliver", new=mock.AsyncMock(return_value=(2, 1))) as deliver:
            done = self.announce(audience="group", body="Plain text", url="#/profile")
        self.assertEqual((done.status_code, done.json()), (200, {"sent": 2, "failed": 1}))
        payload, audience, user_id = deliver.call_args.args
        self.assertEqual((payload["title"], payload["body"], payload["url"], audience, user_id), ("Hello", "Plain text", "#/profile", "group", self.root))
        with mock.patch.object(push, "deliver", new=mock.AsyncMock(return_value=(1, 0))) as deliver:
            self.announce(audience="user", user_id=self.ana)
        self.assertEqual(deliver.call_args.args[1:], ("user", self.ana))

    def test_nobody_receiving_it_is_a_404_with_the_reason(self):
        self.enable_push()
        with mock.patch.object(push, "deliver", new=mock.AsyncMock(return_value=(0, 0))):
            self.assertIn("ningún dispositivo", self.announce().json()["detail"].lower())
        with mock.patch.object(push, "deliver", new=mock.AsyncMock(return_value=(0, 3))):
            refused = self.announce()
        self.assertEqual((refused.status_code, refused.json()["detail"]), (404, "Ningún dispositivo lo ha aceptado"))


class TelegramAnnouncementTests(OpsTestCase):
    def announce(self, **body):
        return self.admin("POST", "/telegram/announce", json={"title": "Hello", **body})

    def configure(self, group=True):
        values = {"telegram.token": TOKEN}
        if group:
            values["telegram.group_id"] = "-100123"
        self.set_settings(**values)

    def test_without_a_bot_token_it_says_so(self):
        self.assertEqual(self.announce().status_code, 409)

    def test_the_group_needs_its_id(self):
        self.configure(group=False)
        self.assertEqual(self.announce(audience="group").status_code, 409)

    def test_it_goes_to_the_admin_a_user_or_the_group(self):
        self.configure()
        self.user("bea", telegram_id=222)
        with mock.patch.object(my_utils, "send_announcement_to_chat", new=mock.AsyncMock(return_value=True)) as send:
            self.assertEqual(self.announce().json(), {"message": "Enviado a root"})
            self.assertEqual(send.call_args.args[0], 777)
            self.assertEqual(self.announce(audience="user", user_id=self.user_id("bea"), body="Hi").json(), {"message": "Enviado a bea"})
            self.assertEqual(send.call_args.args, (222, "Hello", "Hi"))
            self.assertEqual(self.announce(audience="group").json(), {"message": "Enviado a el grupo"})
            self.assertEqual(send.call_args.args[0], "-100123")

    def user_id(self, username):
        return self.scalar("SELECT id FROM users WHERE username = :u", u=username)

    def test_the_target_needs_a_telegram_id_and_must_exist(self):
        self.configure()
        self.assertEqual(self.announce(audience="user", user_id=self.ana).status_code, 409)  # ana has no Telegram id
        self.assertEqual(self.announce(audience="user").status_code, 400)
        self.assertEqual(self.announce(audience="user", user_id=9999).status_code, 404)
        self.assertEqual(self.announce(audience="everyone").status_code, 422)

    def test_a_refusal_from_telegram_is_a_502(self):
        self.configure()
        with mock.patch.object(my_utils, "send_announcement_to_chat", new=mock.AsyncMock(return_value=False)):
            self.assertEqual(self.announce().status_code, 502)


class DiagnosticsTests(OpsTestCase):
    def test_the_telegram_test_message(self):
        with mock.patch.object(my_utils, "send_test_message", new=mock.AsyncMock()) as send:
            self.assertEqual(self.admin("POST", "/settings/test-message").json(), {"message": "Mensaje enviado"})
        send.assert_awaited_once_with("root")
        with mock.patch.object(my_utils, "send_test_message", new=mock.AsyncMock(side_effect=RuntimeError("chat not found"))):
            failed = self.admin("POST", "/settings/test-message")
        self.assertEqual(failed.status_code, 502)
        self.assertIn("chat not found", failed.json()["detail"])

    def test_the_ai_test_needs_a_key_and_reports_what_the_ai_answers(self):
        self.assertEqual(self.admin("POST", "/settings/test-ai").status_code, 409)
        self.set_settings(**{"ai.api_key": "sk-test-key-1234"})
        with mock.patch.object(ai, "complete", return_value="¡Hola, jugones!") as complete, mock.patch.object(ai, "current", return_value=("google", "gemini-x")):
            done = self.admin("POST", "/settings/test-ai")
        self.assertEqual(done.json(), {"message": "La IA ha respondido", "reply": "¡Hola, jugones!", "provider": "google", "model": "gemini-x"})
        self.assertTrue(complete.call_args.kwargs["force"])  # it works with the AI switched off
        with mock.patch.object(ai, "complete", side_effect=AIError("clave rechazada")):
            failed = self.admin("POST", "/settings/test-ai")
        self.assertEqual((failed.status_code, failed.json()["detail"]), (502, "La IA no ha respondido: clave rechazada"))

    def test_the_email_test_says_what_is_missing_who_receives_it_and_why_it_failed(self):
        with mock.patch.object(mail, "missing_settings", return_value=["SMTP_HOST", "PUBLIC_URL"]):
            missing = self.admin("POST", "/settings/test-email")
        self.assertEqual((missing.status_code, "SMTP_HOST, PUBLIC_URL" in missing.json()["detail"]), (409, True))
        with mock.patch.object(mail, "missing_settings", return_value=[]), mock.patch.object(mail, "send_test_email") as send:
            done = self.admin("POST", "/settings/test-email")
            send.assert_called_once_with("root@example.com", "root")
        self.assertEqual(done.json(), {"message": "Correo de prueba enviado a root@example.com"})
        with mock.patch.object(mail, "missing_settings", return_value=[]), mock.patch.object(mail, "send_test_email", side_effect=OSError("connection refused")):
            failed = self.admin("POST", "/settings/test-email")
        self.assertEqual(failed.status_code, 502)
        self.assertIn("connection refused", failed.json()["detail"])

    def test_an_admin_without_an_email_is_told_to_add_one(self):
        with self.engine.begin() as conn:
            conn.execute(text("UPDATE users SET email = NULL WHERE username = 'root'"))
        with mock.patch.object(mail, "missing_settings", return_value=[]):
            self.assertEqual(self.admin("POST", "/settings/test-email").status_code, 400)
