"""The notices about the challenges (MariaDB required, see api_support.py): which request schedules which follow-up, who
is told through which channel, the digests of the two daily jobs and that nothing reaches the group but the group's own
challenges."""
import asyncio
from datetime import datetime, timedelta
from unittest import mock

from src.database import database, models
from src.utils import challenge_notices, my_utils, scheduler
from tests import clock
from tests import test_mariadb_api_challenges as base
from tests.test_mariadb_scheduler import at

TODAY = base.TODAY


class NoticeTestCase(base.ChallengesTestCase):
    def setUp(self):
        super().setUp()
        self.private = []  # (user_id, text, telegram_on, push_on, in_inbox)
        self.group = []

        async def to_user(telegram_id, msg, user_id=None, telegram_on=True, push_on=True, push_payload=None, in_inbox=True):
            self.private.append((user_id, msg, telegram_on, push_on, in_inbox))

        async def to_group(msg, silent, *args, **kwargs):
            self.group.append(msg)

        for patcher in (
            mock.patch.object(my_utils, "send_message_to_user", new=to_user),
            mock.patch.object(my_utils, "send_message", new=to_group),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_notice(self, function, *args):
        async def run():
            with database.SessionLocal() as db:
                return await function(db, *args)

        return asyncio.run(run())

    def prefer(self, user, **columns):
        with database.SessionLocal() as db:
            row = db.get(models.UserSettings, user) or models.UserSettings(user_id=user)
            for column, value in columns.items():
                setattr(row, column, value)
            db.add(row)
            db.commit()

    def told(self, user):
        return [entry for entry in self.private if entry[0] == user]

    def duel(self, as_user="ana", opponent=None, **changes):
        options = {"opponent_id": opponent or self.bea, "duration": "week", **changes}
        return self.api("POST", "/challenges", as_user=as_user, json={"kind": "duel_hours", "options": options}).json()

    def move(self, challenge_id, starts=None, ends=None):
        with database.SessionLocal() as db:
            row = db.get(models.Challenge, challenge_id)
            if starts is not None:
                row.starts_on = TODAY() + timedelta(days=starts)
            if ends is not None:
                row.ends_on = TODAY() + timedelta(days=ends)
            db.commit()

    def play(self, user, minutes, days_ago=0, game="hades"):
        start = datetime.combine(TODAY() - timedelta(days=days_ago), datetime.min.time()) + timedelta(hours=12)
        if not self.scalar("SELECT COUNT(*) FROM users_games WHERE user_id = :u AND game_id = :g", u=user, g=game):
            self.library_entry(user, game, start.date(), "pc")
        self.session(user, game, start, minutes)

    def inbox(self, user):
        return [title for (title,) in self.rows("SELECT title FROM user_notifications WHERE user_id = :u ORDER BY id", u=user)]


class RequestsScheduleTheirNoticesTests(NoticeTestCase):
    def test_launching_a_duel_tells_the_challenged_player_but_a_personal_challenge_tells_nobody(self):
        duel = self.duel()
        self.background["after_duel_launch"].assert_called_once_with(duel["id"])
        self.api("POST", "/challenges", as_user="ana", json={"kind": "long_sessions", "options": {"sessions": 1, "minutes": 30, "duration": "week"}})
        self.assertEqual(self.background["after_duel_launch"].call_count, 1)

    def test_declining_tells_the_challenger_once_however_many_times_it_is_asked(self):
        duel = self.duel()["id"]
        for _ in range(2):
            self.api("PUT", f"/challenges/{duel}/participation", as_user="bea", params={"joined": False})
        self.background["after_duel_decline"].assert_called_once_with(duel)
        self.assertEqual(self.api("PUT", f"/challenges/{duel}/participation", as_user="bea", params={"joined": True}).status_code, 409)  # a decline is final
        self.assertEqual(self.background["after_duel_decline"].call_count, 1)

    def test_leaving_a_group_challenge_tells_nobody(self):
        challenge = self.launch().json()["id"]
        self.api("PUT", f"/challenges/{challenge}/participation", as_user="ana", params={"joined": False})
        self.background["after_duel_decline"].assert_not_called()

    def test_a_proposal_tells_the_admins_and_its_decision_the_proposer(self):
        options = {"game_id": "hades", "month": base.this_month(), "min_hours_each": 3, "min_hours_total": 10}
        proposal = self.api("POST", "/challenges/proposals", as_user="ana", json={"kind": "game_of_month", "options": options}).json()["id"]
        self.background["after_proposal_made"].assert_called_once_with(proposal)
        self.api("POST", f"/manage/challenge-proposals/{proposal}/reject", as_user="root", json={"note": "no"})
        self.background["after_proposal_decided"].assert_called_once_with(proposal)
        other = self.api("POST", "/challenges/proposals", as_user="ana", json={"kind": "game_of_month", "options": {**options, "game_id": "celeste"}}).json()["id"]
        self.api("POST", f"/manage/challenge-proposals/{other}/approve", as_user="root", json={"announce": False})
        self.background["after_proposal_decided"].assert_called_with(other)


class EventNoticeTests(NoticeTestCase):
    def test_the_challenged_player_is_told_through_their_channels_and_it_is_kept_in_the_inbox(self):
        duel = self.duel()["id"]
        self.run_notice(challenge_notices.duel_launched, duel)
        [(user, text, telegram_on, push_on, in_inbox)] = self.told(self.bea)
        self.assertEqual((telegram_on, push_on, in_inbox), (True, True, True))
        self.assertIn("*Ana* te ha retado a un duelo", text)
        self.assertEqual(self.told(self.ana), [])  # the challenger is not told about their own duel

    def test_a_player_who_turned_the_notices_off_is_not_told_and_one_channel_is_respected(self):
        duel = self.duel()["id"]
        self.prefer(self.bea, challenge_notices_telegram=False)
        self.run_notice(challenge_notices.duel_launched, duel)
        self.assertEqual([(t, p) for _, _, t, p, _ in self.told(self.bea)], [(False, True)])
        self.private.clear()
        self.prefer(self.bea, challenge_notices_push=False)
        self.run_notice(challenge_notices.duel_launched, duel)
        self.assertEqual(self.private, [])  # both off: nothing, not even the inbox

    def test_the_admin_switch_for_private_notices_silences_them_all(self):
        duel = self.duel()["id"]
        self.set_settings(**{"challenges.private_notices": False})
        self.assertEqual(self.run_notice(challenge_notices.duel_launched, duel), "skipped")
        self.assertEqual(self.private, [])

    def test_a_declined_duel_tells_the_challenger_and_a_duel_that_stands_does_not(self):
        duel = self.duel()["id"]
        self.assertEqual(self.run_notice(challenge_notices.duel_declined, duel), "skipped")
        self.api("PUT", f"/challenges/{duel}/participation", as_user="bea", params={"joined": False})
        self.run_notice(challenge_notices.duel_declined, duel)
        [(_, text, *_)] = self.told(self.ana)
        self.assertIn("*Bea* ha rechazado tu duelo", text)

    def test_a_decided_proposal_tells_its_proposer_with_the_note_and_a_waiting_one_tells_nobody(self):
        options = {"game_id": "hades", "month": base.this_month(), "min_hours_each": 3, "min_hours_total": 10}
        proposal = self.api("POST", "/challenges/proposals", as_user="ana", json={"kind": "game_of_month", "options": options}).json()["id"]
        self.assertEqual(self.run_notice(challenge_notices.proposal_decided, proposal), "skipped")
        self.api("POST", f"/manage/challenge-proposals/{proposal}/reject", as_user="root", json={"note": "Mejor en noviembre"})
        self.run_notice(challenge_notices.proposal_decided, proposal)
        [(_, text, *_)] = self.told(self.ana)
        self.assertIn("Tu propuesta se ha rechazado", text)
        self.assertIn("Nota: Mejor en noviembre", text)

    def test_a_new_proposal_reaches_the_admins_inbox_only_and_not_the_proposer(self):
        self.user("second", admin=True)
        options = {"game_id": "hades", "month": base.this_month(), "min_hours_each": 3, "min_hours_total": 10}
        proposal = self.api("POST", "/challenges/proposals", as_user="ana", json={"kind": "game_of_month", "options": options}).json()["id"]
        self.run_notice(challenge_notices.proposal_made, proposal)
        self.assertEqual([len(self.inbox(self.root)), len(self.inbox(self.ana)), len(self.inbox(self.bea))], [1, 0, 0])
        self.assertEqual(self.private, [])  # no Telegram and no push
        self.assertEqual(self.inbox(self.root), ["📝 Ana ha propuesto un reto"])

    def test_no_proposal_notice_while_the_notifications_are_off(self):
        options = {"game_id": "hades", "month": base.this_month(), "min_hours_each": 3, "min_hours_total": 10}
        proposal = self.api("POST", "/challenges/proposals", as_user="ana", json={"kind": "game_of_month", "options": options}).json()["id"]
        self.set_settings(**{"notifications.enabled": False})
        self.run_notice(challenge_notices.proposal_made, proposal)
        self.assertEqual(self.inbox(self.root), [])


class ResultsTests(NoticeTestCase):
    def ended_yesterday(self, challenge_id):
        self.move(challenge_id, starts=-8, ends=-1)

    def run_results(self):
        return self.run_notice(challenge_notices.announce_results, TODAY())

    def test_a_group_challenge_that_ended_yesterday_tells_each_player_and_the_group_once(self):
        challenge = self.launch(min_hours_each=1, min_hours_total=2, versus=True).json()["id"]
        self.ended_yesterday(challenge)
        self.play(self.ana, 120, days_ago=3)
        self.play(self.bea, 30, days_ago=3)
        self.run_results()
        by_user = {user: text for user, text, *_ in self.private}
        self.assertEqual(sorted(by_user), sorted([self.ana, self.bea, self.root]))
        self.assertIn("✅ *Juego del mes: Hades*: cumpliste tu parte", by_user[self.ana])
        self.assertIn("(🥇)", by_user[self.ana])
        self.assertIn("❌", by_user[self.bea])
        [message] = self.group
        self.assertIn("1 de 3 habéis cumplido vuestra parte", message)
        self.assertIn("🥇 Gana *Ana*", message)

    def test_a_player_with_several_endings_gets_one_message_with_all_of_them(self):
        first = self.launch(min_hours_each=1, min_hours_total=2).json()["id"]
        second = self.launch(game_id="celeste", min_hours_each=1, min_hours_total=2).json()["id"]
        duel = self.duel()["id"]
        for challenge in (first, second, duel):
            self.ended_yesterday(challenge)
        self.run_results()
        ana = self.told(self.ana)
        self.assertEqual(len(ana), 1)
        self.assertTrue(ana[0][1].startswith("🏁 Han terminado 3 de tus retos"))
        self.assertEqual(len(self.group), 2)  # one for each group challenge, nothing for the duel

    def test_a_duel_is_told_to_its_two_players_and_never_to_the_group(self):
        duel = self.duel()["id"]
        self.ended_yesterday(duel)
        self.play(self.ana, 90, days_ago=3)
        self.play(self.bea, 30, days_ago=3)
        self.run_results()
        self.assertIn("Ganaste el duelo a *Bea*", self.told(self.ana)[0][1])
        self.assertIn("Perdiste el duelo contra *Ana*", self.told(self.bea)[0][1])
        self.assertEqual(self.group, [])

    def test_a_personal_challenge_is_told_to_its_owner_only(self):
        self.api("POST", "/challenges", as_user="ana", json={"kind": "long_sessions", "options": {"sessions": 1, "minutes": 30, "duration": "week"}})
        challenge = self.scalar("SELECT id FROM challenges")
        self.ended_yesterday(challenge)
        self.run_results()
        self.assertEqual([user for user, *_ in self.private], [self.ana])
        self.assertEqual(self.group, [])

    def test_a_declined_duel_and_a_challenge_that_ended_some_other_day_say_nothing(self):
        declined = self.duel()["id"]
        self.api("PUT", f"/challenges/{declined}/participation", as_user="bea", params={"joined": False})
        self.ended_yesterday(declined)
        other = self.launch().json()["id"]
        self.move(other, starts=-8, ends=-2)  # ended the day before yesterday
        running = self.launch(game_id="celeste").json()["id"]
        self.move(running, starts=-3, ends=3)
        self.run_results()
        self.assertEqual((self.private, self.group), ([], []))

    def test_the_two_switches_are_independent_and_a_player_with_the_channels_off_is_skipped(self):
        challenge = self.launch().json()["id"]
        self.ended_yesterday(challenge)
        self.set_settings(**{"challenges.result_notice": False})
        self.run_results()
        self.assertEqual((len(self.private), self.group), (3, []))
        self.private.clear()
        self.set_settings(**{"challenges.result_notice": True, "challenges.private_notices": False})
        self.run_results()
        self.assertEqual((self.private, len(self.group)), ([], 1))
        self.group.clear()
        self.set_settings(**{"challenges.private_notices": True})
        self.prefer(self.ana, challenge_notices_telegram=False, challenge_notices_push=False)
        self.run_results()
        self.assertEqual(sorted(user for user, *_ in self.private), sorted([self.bea, self.root]))

    def test_a_voluntary_challenge_is_told_to_who_joined_and_one_nobody_joined_to_nobody(self):
        joined = self.launch(participation="opt_in").json()["id"]
        empty = self.launch(participation="opt_in", game_id="celeste").json()["id"]
        self.api("PUT", f"/challenges/{joined}/participation", as_user="bea", params={"joined": True})
        for challenge in (joined, empty):
            self.ended_yesterday(challenge)
        self.run_results()
        self.assertEqual([user for user, *_ in self.private], [self.bea])
        self.assertEqual(len(self.group), 1)

    def test_the_inbox_keeps_what_was_told(self):
        challenge = self.launch().json()["id"]
        self.ended_yesterday(challenge)
        self.run_results()
        self.assertTrue(all(entry[4] for entry in self.private))  # in_inbox


class ReminderTests(NoticeTestCase):
    def run_reminders(self):
        return self.run_notice(challenge_notices.send_reminders, TODAY())

    def two_days_left(self, challenge_id):
        self.move(challenge_id, starts=-5, ends=2)

    def test_they_are_off_until_a_player_turns_them_on(self):
        challenge = self.launch().json()["id"]
        self.two_days_left(challenge)
        self.run_reminders()
        self.assertEqual(self.private, [])
        self.prefer(self.ana, challenge_reminders_push=True)
        self.run_reminders()
        [(user, text, telegram_on, push_on, in_inbox)] = self.private
        self.assertEqual((user, telegram_on, push_on, in_inbox), (self.ana, False, True, False))  # a reminder is not kept in the inbox
        self.assertEqual(text.splitlines()[0], "⏰ Te quedan 2 días en un reto")
        self.assertIn("*Juego del mes: Hades*: te faltan 5 h", text)

    def test_only_who_has_not_met_their_part_is_reminded_and_only_at_exactly_two_days(self):
        challenge = self.launch(min_hours_each=1, min_hours_total=2).json()["id"]
        self.two_days_left(challenge)
        for user in (self.ana, self.bea):
            self.prefer(user, challenge_reminders_telegram=True)
        self.played(self.ana, 2, days_ago=1)
        self.run_reminders()
        self.assertEqual([user for user, *_ in self.private], [self.bea])
        self.private.clear()
        self.move(challenge, ends=3)
        self.run_reminders()
        self.move(challenge, ends=1)
        self.run_reminders()
        self.assertEqual(self.private, [])

    def test_a_player_gets_one_reminder_for_all_their_challenges(self):
        first = self.launch(min_hours_each=1, min_hours_total=2).json()["id"]
        second = self.launch(game_id="celeste", min_hours_each=1, min_hours_total=2).json()["id"]
        for challenge in (first, second):
            self.two_days_left(challenge)
        self.prefer(self.ana, challenge_reminders_telegram=True)
        self.run_reminders()
        [(user, text, *_)] = self.private
        self.assertEqual(text.splitlines()[0], "⏰ Te quedan 2 días en 2 retos")
        self.assertEqual(len(text.splitlines()), 3)

    def test_in_a_duel_only_the_one_who_is_behind_is_reminded(self):
        duel = self.duel()["id"]
        self.two_days_left(duel)
        self.prefer(self.ana, challenge_reminders_telegram=True)
        self.prefer(self.bea, challenge_reminders_telegram=True)
        self.play(self.ana, 120, days_ago=1)
        self.play(self.bea, 30, days_ago=1)
        self.run_reminders()
        [(user, text, *_)] = self.private
        self.assertEqual(user, self.bea)
        self.assertIn("vas perdiendo contra *Ana* por 1,5 h", text)

    def test_the_admin_switch_turns_them_all_off(self):
        challenge = self.launch().json()["id"]
        self.two_days_left(challenge)
        self.prefer(self.ana, challenge_reminders_telegram=True)
        self.set_settings(**{"challenges.reminders": False})
        self.assertEqual(self.run_reminders(), "off")
        self.assertEqual(self.private, [])

    def test_a_declined_duel_and_a_challenge_that_has_not_begun_are_not_reminded(self):
        duel = self.duel()["id"]
        self.api("PUT", f"/challenges/{duel}/participation", as_user="bea", params={"joined": False})
        self.two_days_left(duel)
        future = self.launch(game_id="celeste").json()["id"]
        self.move(future, starts=1, ends=2)
        for user in (self.ana, self.bea):
            self.prefer(user, challenge_reminders_telegram=True)
        self.run_reminders()
        self.assertEqual(self.private, [])


class JobTests(NoticeTestCase):
    def setUp(self):
        super().setUp()
        for patcher in (mock.patch.object(scheduler.actions, "announce_lost_streaks", new=mock.AsyncMock()), mock.patch.object(scheduler.actions, "check_wishlist", new=mock.AsyncMock(return_value=""))):
            patcher.start()
            self.addCleanup(patcher.stop)

    def jobs(self):
        return {job: status for job, status in self.rows("SELECT job, last_status FROM job_runs")}

    def test_the_results_go_out_once_at_their_hour_and_the_reminders_at_theirs(self):
        ended = self.launch().json()["id"]
        self.move(ended, starts=-8, ends=-1)
        closing = self.launch(game_id="celeste").json()["id"]
        self.move(closing, starts=-5, ends=2)
        self.prefer(self.ana, challenge_reminders_telegram=True)
        scheduler.tick(at(9, 31))
        self.assertEqual(self.jobs()["challenge_results"], "ok: 3 told, 1 to the group")
        self.assertNotIn("challenge_reminders", self.jobs())  # their hour has not come
        scheduler.tick(at(10, 1))
        self.assertEqual(self.jobs()["challenge_reminders"], "ok: 1 told")
        scheduler.tick(at(10, 2))
        scheduler.tick(at(9, 40))
        self.assertEqual(len(self.group), 1)  # a second tick in the same slot sends nothing

    def test_the_hours_can_be_changed_and_a_late_run_is_too_late(self):
        self.set_settings(**{"challenges.results_time": "14:00", "challenges.reminders_time": "15:00"})
        scheduler.tick(at(9, 31))
        scheduler.tick(at(10, 1))
        self.assertNotIn("challenge_results", self.jobs())
        scheduler.tick(at(14, 1))
        scheduler.tick(at(19, 0))  # more than the grace window after 15:00
        self.assertEqual(sorted(name for name in self.jobs() if name.startswith("challenge_re")), ["challenge_results"])

    def test_nothing_runs_while_the_notifications_or_the_switches_are_off(self):
        self.set_settings(**{"notifications.enabled": False})
        scheduler.tick(at(9, 31))
        scheduler.tick(at(10, 1))
        self.assertEqual([name for name in self.jobs() if name.startswith("challenge_re")], [])
        self.set_settings(**{"notifications.enabled": True, "challenges.private_notices": False, "challenges.result_notice": False, "challenges.reminders": False})
        scheduler.tick(at(9, 32, day=1))
        scheduler.tick(at(10, 2, day=1))
        self.assertEqual([name for name in self.jobs() if name.startswith("challenge_re")], [])


class PreferencesTests(NoticeTestCase):
    def test_the_channels_of_the_challenge_notices_are_saved_and_default_when_cleared(self):
        body = self.api("GET", "/users/ana/settings", as_user="ana").json()
        self.assertEqual((body["challenge_notices_telegram"], body["defaults"]["challenge_notices_telegram"], body["defaults"]["challenge_reminders_push"]), (None, True, False))
        saved = self.api("PATCH", "/users/ana/settings", as_user="ana", json={"challenge_reminders_push": True, "challenge_notices_telegram": False}).json()
        self.assertEqual((saved["challenge_reminders_push"], saved["challenge_notices_telegram"]), (True, False))
        cleared = self.api("PATCH", "/users/ana/settings", as_user="ana", json={"challenge_reminders_push": None}).json()
        self.assertEqual((cleared["challenge_reminders_push"], cleared["challenge_notices_telegram"]), (None, False))
        self.assertEqual(self.api("GET", "/users/ana/settings", as_user="bea").status_code, 403)

    def test_the_clock_the_jobs_use_is_the_pinned_one(self):
        self.assertEqual(clock.today(), TODAY())
