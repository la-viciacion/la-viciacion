"""The group's polls through real requests (MariaDB required, see api_support.py): who may launch and close them, what the
panel shows, what the bot reports, that a vote is not kept in the audit log, that a poll is closed whatever Telegram
does, and that the scheduler closes the ones whose deadline has passed."""
from datetime import timedelta
from unittest import mock

from src.database import database, models
from src.utils import polls, scheduler
from tests import clock
from tests.api_support import ApiTestCase


class PollsTestCase(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.root = self.user("root", admin=True)
        self.ana = self.user("ana", telegram_id=111)
        self.bea = self.user("bea")
        self.sent = []  # the messages to the group
        self.stopped = []  # the polls Telegram was asked to stop
        self.stop_result = (True, 2)

        async def send(question, options, multiple, allow_adding_options=False):
            self.sent.append((question, list(options), multiple))
            return str(500 + len(self.sent)), 70 + len(self.sent), [f"k{n}" for n in range(len(options))]

        async def stop(poll):
            self.stopped.append(poll.id)
            return self.stop_result

        self.announced = []

        async def announce(message, silent, **kwargs):
            self.announced.append(message)

        for patcher in (
            mock.patch.object(polls, "send", new=send),
            mock.patch.object(polls, "stop", new=stop),
            mock.patch.object(polls.my_utils, "send_message", new=announce),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def launch(self, as_user="root", **changes):
        body = {"question": "¿A qué jugamos?", "options": ["Hades", "Celeste", "Tetris"], **changes}
        return self.api("POST", "/manage/polls", as_user=as_user, json=body)

    def answer(self, poll_id, user_id, option_ids, as_user="root"):
        return self.api("PUT", "/manage/polls/answers", as_user=as_user, json={"poll_id": poll_id, "user_id": user_id, "option_ids": option_ids})

    def close(self, poll_id, as_user="root", **body):
        return self.api("POST", f"/manage/polls/{poll_id}/close", as_user=as_user, json=body)

    def audit_paths(self):
        return [path for (path,) in self.rows("SELECT path FROM audit_log ORDER BY id")]


class AccessTests(PollsTestCase):
    def test_everything_is_for_the_admins(self):
        poll = self.launch().json()["id"]
        for method, path, body in (
            ("GET", "/manage/polls", None), ("POST", "/manage/polls", {"question": "¿?", "options": ["a", "b"]}),
            ("POST", f"/manage/polls/{poll}/close", {}), ("DELETE", f"/manage/polls/{poll}", None),
            ("PUT", "/manage/polls/answers", {"poll_id": "501", "user_id": 1, "option_ids": [0]}),
            ("PUT", "/manage/polls/options", {"key": "k9", "text": "Otra"}),
        ):
            self.assertEqual(self.api(method, path, json=body).status_code, 401, (method, path))
            self.assertEqual(self.api(method, path, as_user="ana", json=body).status_code, 403, (method, path))


class LaunchTests(PollsTestCase):
    def test_a_poll_is_sent_to_the_group_and_kept(self):
        response = self.launch(multiple=True, options="Hades\n\n Celeste \nTetris")  # the panel posts one option per line
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(self.sent, [("¿A qué jugamos?", ["Hades", "Celeste", "Tetris"], True)])
        self.assertEqual((body["status"], body["multiple"], body["voters"], body["winners"]), ("open", True, 0, []))
        self.assertEqual([option["text"] for option in body["options"]], ["Hades", "Celeste", "Tetris"])
        self.assertEqual(self.rows("SELECT telegram_poll_id, telegram_message_id, created_by FROM group_polls"), [("501", 71, self.root)])
        self.assertEqual(self.audit_paths(), ["/api/v1/manage/polls"])  # the launch is the admin's change

    def test_what_telegram_would_refuse_is_refused_before_sending(self):
        for changes in ({"question": ""}, {"options": ["solo una"]}, {"options": [str(n) for n in range(11)]}, {"options": ["a", "A"]},
                        {"closes_at": (clock.now() - timedelta(hours=1)).isoformat()}):
            self.assertEqual(self.launch(**changes).status_code, 400, changes)
        self.assertEqual((self.sent, self.scalar("SELECT COUNT(*) FROM group_polls")), ([], 0))

    def test_a_telegram_that_refuses_it_leaves_nothing_behind(self):
        async def refuse(question, options, multiple, allow_adding_options=False):
            raise polls.TelegramFailure("Falta el token del bot o el ID del grupo")

        with mock.patch.object(polls, "send", new=refuse):
            response = self.launch()
        self.assertEqual((response.status_code, response.json()["detail"]), (502, "Falta el token del bot o el ID del grupo"))
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM group_polls"), 0)

    def test_only_one_poll_can_be_open_at_a_time(self):
        first = self.launch().json()["id"]
        refused = self.launch(question="¿Y ahora?")
        self.assertEqual((refused.status_code, refused.json()["detail"]), (409, "Ya hay una encuesta abierta: ciérrala antes de lanzar otra"))
        self.assertEqual((len(self.sent), self.scalar("SELECT COUNT(*) FROM group_polls")), (1, 1))  # nothing reached the group
        self.close(first)
        self.assertEqual(self.launch(question="¿Y ahora?").status_code, 201)

    def test_the_deadline_is_kept(self):
        closes_at = clock.now() + timedelta(days=2)
        self.launch(closes_at=closes_at.isoformat())
        self.assertEqual(self.scalar("SELECT closes_at FROM group_polls"), closes_at)


class AnswerTests(PollsTestCase):
    def test_the_bot_reports_what_each_person_chose_and_the_panel_shows_who(self):
        poll = self.launch().json()["id"]
        self.assertEqual(self.answer("501", 111, [0]).json(), {"recorded": True})  # Ana, who linked her Telegram
        self.answer("501", 999, [0])  # somebody in the group with no account
        self.answer("501", 111, [1])  # Ana changes her mind
        shown = self.api("GET", "/manage/polls", as_user="root").json()
        self.assertEqual([p["id"] for p in shown], [poll])
        options = shown[0]["options"]
        self.assertEqual([(o["text"], o["votes"], [v["name"] for v in o["voters"]]) for o in options],
                         [("Hades", 1, [None]), ("Celeste", 1, ["Ana"]), ("Tetris", 0, [])])
        self.assertEqual((shown[0]["voters"], shown[0]["winners"]), (2, [0, 1]))

    def test_an_answer_to_a_poll_that_is_not_ours_counts_for_nothing(self):
        self.launch()
        self.assertEqual(self.answer("9999", 111, [0]).json(), {"recorded": False})
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM group_poll_votes"), 0)

    def test_a_vote_is_not_in_the_audit_log_but_a_launch_is(self):
        self.launch()
        for _ in range(3):
            self.answer("501", 111, [0])
        self.assertEqual(self.audit_paths(), ["/api/v1/manage/polls"])

    def test_an_answer_with_nothing_chosen_takes_the_vote_back(self):
        self.launch()
        self.answer("501", 111, [2])
        self.answer("501", 111, [])
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM group_poll_votes"), 0)


class AddedOptionsTests(PollsTestCase):
    def add_option(self, key="k9", text="Hollow Knight", **body):
        return self.api("PUT", "/manage/polls/options", as_user="root", json={"key": key, "text": text, **body})

    def test_an_option_the_group_adds_gets_votes_and_can_win(self):
        poll = self.launch(allow_adding_options=True).json()
        self.assertTrue(poll["allow_adding_options"])
        self.assertEqual(self.add_option(message_id=71).json(), {"recorded": True})
        self.api("PUT", "/manage/polls/answers", as_user="root", json={"poll_id": "501", "user_id": 111, "option_ids": [0], "option_keys": ["k9"]})
        shown = self.api("GET", "/manage/polls", as_user="root").json()[0]
        self.assertEqual([(o["text"], o["votes"]) for o in shown["options"]], [("Hades", 0), ("Celeste", 0), ("Tetris", 0), ("Hollow Knight", 1)])
        self.assertEqual(shown["winners"], [3])
        self.assertEqual(self.audit_paths(), ["/api/v1/manage/polls"])  # reporting an option is not an admin's change

    def test_a_poll_that_does_not_let_the_group_add_ignores_them(self):
        self.launch()
        self.assertEqual(self.add_option().json(), {"recorded": False})
        self.assertEqual(self.scalar("SELECT options FROM group_polls").count("Hollow"), 0)


class CloseTests(PollsTestCase):
    def test_closing_ends_the_poll_stops_it_in_telegram_and_tells_the_winner(self):
        poll = self.launch().json()["id"]
        self.answer("501", 111, [2])
        body = self.close(poll).json()
        self.assertEqual((body["status"], body["telegram_stopped"], body["winners"]), ("closed", True, [2]))
        self.assertEqual(self.stopped, [poll])
        self.assertEqual(len(self.announced), 1)
        self.assertIn("Gana *Tetris* con 1 voto", self.announced[0])
        self.assertEqual(self.scalar("SELECT closed_by FROM group_polls"), self.root)
        self.assertEqual(self.answer("501", 999, [0]).json(), {"recorded": False})  # closed: nothing else counts

    def test_the_winner_is_only_told_when_the_admin_asks(self):
        poll = self.launch().json()["id"]
        self.close(poll, announce=False)
        self.assertEqual(self.announced, [])

    def test_a_telegram_that_fails_does_not_keep_it_open_and_closing_again_tries_once_more(self):
        poll = self.launch().json()["id"]
        self.stop_result = (False, None)
        body = self.close(poll).json()
        self.assertEqual((body["status"], body["telegram_stopped"]), ("closed", False))  # closed here: the admin sees it still runs there
        self.assertEqual(len(self.announced), 1)
        self.stop_result = (True, 0)
        body = self.close(poll).json()
        self.assertEqual((body["status"], body["telegram_stopped"]), ("closed", True))
        self.assertEqual((len(self.announced), self.stopped), (1, [poll, poll]))  # nothing is announced twice

    def test_a_poll_that_does_not_exist(self):
        self.assertEqual(self.close(999).status_code, 404)


class DeleteTests(PollsTestCase):
    def test_an_open_poll_cannot_be_deleted_and_a_closed_one_takes_its_votes_with_it(self):
        poll = self.launch().json()["id"]
        self.answer("501", 111, [0])
        self.assertEqual(self.api("DELETE", f"/manage/polls/{poll}", as_user="root").status_code, 409)
        self.close(poll)
        self.assertEqual(self.api("DELETE", f"/manage/polls/{poll}", as_user="root").status_code, 200)
        self.assertEqual((self.scalar("SELECT COUNT(*) FROM group_polls"), self.scalar("SELECT COUNT(*) FROM group_poll_votes")), (0, 0))

    def test_an_account_that_is_deleted_leaves_the_poll(self):
        poll = self.launch().json()["id"]
        self.close(poll)
        with database.SessionLocal() as db:
            db.execute(models.User.__table__.update().where(models.User.id == self.root).values(is_admin=0))
            db.commit()
            db.delete(db.get(models.User, self.root))
            db.commit()
        self.assertEqual(self.rows("SELECT created_by, closed_by FROM group_polls"), [(None, None)])


class SchedulerTests(PollsTestCase):
    def poll(self, **changes):
        poll = self.launch().json()["id"]
        self.sql_set(poll, **changes)
        return poll

    def sql_set(self, poll, **values):
        with database.SessionLocal() as db:
            db.query(models.GroupPoll).filter_by(id=poll).update(values)
            db.commit()

    def test_a_poll_past_its_deadline_is_closed_and_its_winner_told(self):
        now = clock.now()
        poll = self.poll(closes_at=now - timedelta(minutes=1))
        self.answer("501", 111, [1])
        scheduler.tick(now)
        self.assertEqual(self.rows("SELECT closed_at IS NOT NULL, closed_by, telegram_stopped FROM group_polls"), [(1, None, 1)])
        self.assertIn("Gana *Celeste*", self.announced[0])
        self.assertEqual(self.scalar("SELECT last_status FROM job_runs WHERE job = 'group_polls'"), "ok: 1 closed")
        self.assertEqual(self.stopped, [poll])
        scheduler.tick(now + timedelta(minutes=1))
        self.assertEqual(len(self.announced), 1)  # closed once

    def test_a_poll_before_its_deadline_or_without_one_is_left_alone(self):
        now = clock.now()
        self.poll(closes_at=now + timedelta(hours=1))
        self.launch()
        scheduler.tick(now)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM group_polls WHERE closed_at IS NOT NULL"), 0)
        self.assertEqual(self.rows("SELECT job FROM job_runs WHERE job LIKE 'group_poll%'"), [])  # nothing due: no run recorded

    def test_the_deadline_closes_it_whatever_the_notifications_switch_says(self):
        now = clock.now()
        self.set_settings(**{"notifications.enabled": False})
        self.poll(closes_at=now - timedelta(minutes=1))
        scheduler.tick(now)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM group_polls WHERE closed_at IS NOT NULL"), 1)

    def test_telegram_is_told_again_every_ten_minutes_until_it_stops_the_poll(self):
        now = clock.now().replace(minute=0, second=0, microsecond=0)
        poll = self.poll(closes_at=now - timedelta(minutes=1))
        self.stop_result = (False, None)
        scheduler.tick(now)  # closed here; Telegram failed
        self.assertEqual(self.scalar("SELECT telegram_stopped FROM group_polls"), 0)
        self.stop_result = (True, 1)
        scheduler.tick(now + timedelta(minutes=10))
        self.assertEqual(self.scalar("SELECT telegram_stopped FROM group_polls"), 1)
        self.assertEqual(self.scalar("SELECT last_status FROM job_runs WHERE job = 'group_poll_stops'"), "ok: 1 stopped")
        self.assertEqual(self.stopped, [poll, poll])
        scheduler.tick(now + timedelta(minutes=20))
        self.assertEqual(self.stopped, [poll, poll])  # stopped: nothing left to tell

    def test_the_migration_made_the_tables_the_models_describe(self):
        self.assertEqual(sorted(name for (name,) in self.rows("SHOW TABLES LIKE 'group_poll%'")), ["group_poll_votes", "group_polls"])
