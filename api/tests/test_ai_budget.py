"""The monthly budget of the group's key: what counts against it (only what the group paid), who is stopped and told what, how an admin
changes a player's share and what a player sees of their own spending."""
import datetime
import types
import unittest
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src import auth
from src.database import models
from src.routers import chat as chat_router
from src.routers import guide as guide_router
from src.routers import user_ai as user_route
from src.routers.manage import ai_usage as manage_route
from src.utils import ai_budget, ai_ledger, ai_source, messages, settings, user_ai
from tests.sqlite_db import make_session
from tests.test_chat import seed

NOW = datetime.datetime(2026, 11, 15, 12, 0)
KEY = "sk-proj-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"


def values(**overrides):
    base = {key: spec.default for key, spec in settings.REGISTRY.items()}
    return {**base, "ai.api_key": "GROUPKEY", "ai.provider": "openai", "ai.model": "gpt-4.1-mini", "chat.model": None, **overrides}


def patched(**overrides):
    table = values(**overrides)
    return mock.patch.object(settings, "get", side_effect=lambda key: table[key])


class Base(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        seed(self.db)

    def spend(self, user=1, dollars=1.0, source="group", when=NOW, feature="chat", cost=True):
        self.db.add(models.AiUsage(
            created_at=when, user_id=user, feature=feature, key_source=source, status="ok",
            cost_micros=int(dollars * 1_000_000) if cost else None, provider="openai", model="gpt-4.1-mini",
        ))
        self.db.commit()


class SpentTests(Base):
    def test_only_what_the_group_paid_this_month_counts(self):
        self.spend(1, 2.0)
        self.spend(2, 3.0)
        self.spend(1, 50.0, source="user")
        self.spend(1, 7.0, when=datetime.datetime(2026, 10, 31, 23, 59))
        self.assertEqual(ai_budget.spent(self.db, None, NOW), 5_000_000)
        self.assertEqual(ai_budget.spent(self.db, 1, NOW), 2_000_000)
        self.assertEqual(ai_budget.spent(self.db, 2, NOW), 3_000_000)

    def test_a_call_with_no_known_price_counts_as_nothing(self):
        self.spend(1, cost=False)
        self.assertEqual(ai_budget.spent(self.db, 1, NOW), 0)

    def test_the_month_starts_on_the_first_and_the_next_one_after_it(self):
        self.assertEqual(ai_budget.month_start(NOW), datetime.datetime(2026, 11, 1))
        self.assertEqual(ai_budget.next_month(NOW), datetime.datetime(2026, 12, 1))
        self.assertEqual(ai_budget.next_month(datetime.datetime(2026, 12, 31)), datetime.datetime(2027, 1, 1))


class CapsTests(Base):
    def test_a_player_has_the_default_unless_an_admin_gave_them_another(self):
        with patched(**{"ai.user_budget_month": 5}):
            self.assertEqual(ai_budget.user_cap(self.db, 1), 5)
            ai_budget.set_user_cap(self.db, 1, 12)
            self.assertEqual(ai_budget.user_cap(self.db, 1), 12)
            self.assertEqual(ai_budget.user_cap(self.db, 2), 5)
            ai_budget.set_user_cap(self.db, 1, None)
            self.assertEqual(ai_budget.user_cap(self.db, 1), 5)

    def test_an_individual_zero_is_no_limit_even_when_the_default_has_one(self):
        with patched(**{"ai.user_budget_month": 5}):
            ai_budget.set_user_cap(self.db, 1, 0)
            self.spend(1, 100.0)
            self.assertIsNone(ai_budget.exceeded(self.db, 1, NOW))

    def test_nothing_is_limited_when_every_cap_is_zero(self):
        self.spend(1, 1000.0)
        with patched():
            self.assertIsNone(ai_budget.exceeded(self.db, 1, NOW))

    def test_the_group_budget_stops_everybody_and_the_players_share_stops_only_them(self):
        self.spend(1, 4.0)
        self.spend(2, 1.0)
        with patched(**{"ai.group_budget_month": 5}):
            self.assertEqual(ai_budget.exceeded(self.db, 1, NOW), "group")
            self.assertEqual(ai_budget.exceeded(self.db, 2, NOW), "group")
        with patched(**{"ai.group_budget_month": 100, "ai.user_budget_month": 3}):
            self.assertEqual(ai_budget.exceeded(self.db, 1, NOW), "user")
            self.assertIsNone(ai_budget.exceeded(self.db, 2, NOW))

    def test_a_budget_is_spent_when_it_is_reached_and_not_before(self):
        self.spend(1, 2.99)
        with patched(**{"ai.user_budget_month": 3}):
            self.assertIsNone(ai_budget.exceeded(self.db, 1, NOW))
            self.spend(1, 0.01)
            self.assertEqual(ai_budget.exceeded(self.db, 1, NOW), "user")

    def test_last_months_spending_does_not_count_and_the_budget_starts_again(self):
        self.spend(1, 10.0, when=datetime.datetime(2026, 10, 20))
        with patched(**{"ai.group_budget_month": 5, "ai.user_budget_month": 5}):
            self.assertIsNone(ai_budget.exceeded(self.db, 1, NOW))

    def test_the_players_screen_gets_both_caps_with_what_is_spent_and_when_it_starts_again(self):
        self.spend(1, 1.5)
        with patched(**{"ai.group_budget_month": 20, "ai.user_budget_month": 4}):
            found = ai_budget.usage(self.db, 1, NOW)
        self.assertEqual(found, {"month": "2026-11", "resets_on": "2026-12-01", "group": {"cap": 20, "spent": 1.5}, "user": {"cap": 4, "spent": 1.5}})


class AdminTableTests(Base):
    def test_every_player_is_listed_with_cap_spent_and_override_and_the_emergency_account_is_not(self):
        self.spend(1, 2.0)
        ai_budget.set_user_cap(self.db, 2, 9)
        with patched(**{"ai.user_budget_month": 5}):
            players = ai_budget.players(self.db, NOW)
        self.assertEqual([(p["name"], p["cap"], p["override"], p["spent"], p["calls"]) for p in players], [("Ana", 5, None, 2.0, 1), ("Beto", 9, 9, 0.0, 0)])

    def test_what_a_player_paid_with_their_own_key_is_not_in_the_table(self):
        self.spend(1, 99.0, source="user")
        with patched():
            self.assertEqual(ai_budget.players(self.db, NOW)[0]["spent"], 0.0)


class DecisionTests(Base):
    def decide(self, mode, own=False, **settings_):
        if own:
            user_ai.save(self.db, 1, KEY, "gpt-5-mini")
        else:
            user_ai.clear(self.db, 1)
        with patched(**{"chat.key_source": mode, **settings_}):
            return ai_source.decide(self.db, 1, "chat"), ai_source.availability(self.db, 1, "chat")

    def test_a_spent_budget_stops_the_groups_key_and_says_whose_budget(self):
        self.spend(1, 6.0)
        decision, state = self.decide("user_or_group", **{"ai.group_budget_month": 5})
        self.assertEqual((decision.source, decision.blocked), (None, "group"))
        self.assertEqual((state["blocked"], state["needs_key"], state["available"]), ("group", True, True))
        decision, _ = self.decide("user_or_group", **{"ai.group_budget_month": 100, "ai.user_budget_month": 5})
        self.assertEqual(decision.blocked, "user")

    def test_a_player_with_their_own_key_is_never_stopped_by_the_groups_budget(self):
        self.spend(1, 60.0)
        decision, state = self.decide("user_or_group", own=True, **{"ai.group_budget_month": 5, "ai.user_budget_month": 5})
        self.assertEqual((decision.source.key_source, decision.blocked, state["blocked"]), ("user", None, None))

    def test_a_feature_that_is_only_the_players_has_no_budget_to_spend(self):
        self.spend(1, 60.0)
        decision, state = self.decide("user_only", **{"ai.group_budget_month": 5})
        self.assertEqual((decision.source, decision.blocked, state["blocked"]), (None, None, None))

    def test_when_the_group_always_pays_the_budget_stops_even_a_player_with_a_key(self):
        self.spend(1, 60.0)
        decision, state = self.decide("group_only", own=True, **{"ai.group_budget_month": 5})
        self.assertEqual((decision.source, decision.blocked), (None, "group"))
        self.assertEqual((state["available"], state["needs_key"], state["blocked"]), (True, False, "group"))

    def test_under_budget_the_group_pays_as_before(self):
        self.spend(1, 1.0)
        decision, state = self.decide("user_or_group", **{"ai.group_budget_month": 5})
        self.assertEqual((decision.source.key_source, decision.blocked, state["paid_by"]), ("group", None, "group"))

    def test_the_message_names_the_budget_and_offers_the_own_key_only_where_it_would_be_used(self):
        with patched(**{"chat.key_source": "user_or_group", "guide.key_source": "group_only"}):
            self.assertIn(messages.GROUP_BUDGET_REACHED, ai_source.blocked_message("group", "chat"))
            self.assertIn("Mi IA", ai_source.blocked_message("group", "chat"))
            self.assertIn(messages.USER_BUDGET_REACHED, ai_source.blocked_message("user", "chat"))
            self.assertNotIn("Mi IA", ai_source.blocked_message("group", "guide"))


class QuestionsStoppedTests(Base):
    def setUp(self):
        super().setUp()
        self.db = make_session(threads=True)
        seed(self.db)
        self.user = types.SimpleNamespace(id=1, username="ana", name="Ana", is_admin=0, is_active=1)
        app = FastAPI()
        for router, module in ((chat_router.router, chat_router), (guide_router.router, guide_router)):
            app.include_router(router)
            app.dependency_overrides[module.get_db] = lambda: self.db
        app.dependency_overrides[auth.get_current_active_user] = lambda: self.user
        self.client = TestClient(app)
        chat_router.limits.limiter.clear()
        self.addCleanup(chat_router.limits.limiter.clear)

    def test_a_chat_question_over_budget_is_a_429_that_says_so_and_is_recorded_without_calling_the_ai(self):
        self.spend(1, 6.0)
        with patched(**{"ai.group_budget_month": 5}), mock.patch.object(chat_router.agent, "ask") as ask:
            response = self.client.post("/chat", json={"message": "hola"})
        self.assertEqual(response.status_code, 429)
        self.assertIn(messages.GROUP_BUDGET_REACHED, response.json()["detail"])
        self.assertFalse(ask.called)
        statuses = [r.status for r in self.db.query(models.AiUsage).order_by(models.AiUsage.id)]
        self.assertEqual(statuses, ["ok", "budget"])

    def test_the_chat_is_still_there_for_whoever_ran_out_so_that_asking_tells_them_why(self):
        self.spend(1, 6.0)
        with patched(**{"ai.group_budget_month": 5}):
            self.assertEqual(self.client.get("/chat/status").json(), {"available": True})

    def test_a_guide_question_over_budget_is_a_429_too(self):
        self.spend(1, 6.0)
        with patched(**{"ai.group_budget_month": 5, "guide.key_source": "group_only"}), mock.patch.object(guide_router.agent, "ask") as ask:
            response = self.client.post("/guide/g1", json={"message": "hola"})
        self.assertEqual(response.status_code, 429)
        self.assertFalse(ask.called)
        self.assertEqual(self.db.query(models.AiUsage).order_by(models.AiUsage.id.desc()).first().status, "budget")

    def test_the_guide_status_says_which_budget_is_spent(self):
        self.spend(1, 6.0)
        with patched(**{"ai.group_budget_month": 5, "guide.key_source": "user_or_group"}):
            body = self.client.get("/guide/status").json()
        self.assertEqual((body["blocked"], body["needs_key"]), ("group", True))

    def test_a_question_within_budget_goes_through(self):
        self.spend(1, 1.0)
        with patched(**{"ai.group_budget_month": 5}), mock.patch.object(chat_router.agent, "ask", return_value=chat_router.agent.Answer("Hola", True)):
            self.assertEqual(self.client.post("/chat", json={"message": "hola"}).status_code, 200)


class PlayerSpendingTests(Base):
    def setUp(self):
        super().setUp()
        self.db = make_session(threads=True)
        seed(self.db)
        user_route.limiter.clear()
        app = FastAPI()
        app.include_router(user_route.router)
        self.user = types.SimpleNamespace(id=1, username="ana", name="Ana", is_admin=0, is_active=1)
        app.dependency_overrides[auth.get_current_active_user] = lambda: self.user
        app.dependency_overrides[user_route.get_db] = lambda: self.db
        self.client = TestClient(app)
        patcher = patched(**{"ai.group_budget_month": 20, "ai.user_budget_month": 4})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_player_sees_their_own_calls_split_by_who_paid_and_nobody_elses(self):
        self.spend(1, 2.0, when=datetime.datetime.now())
        self.spend(1, 3.0, source="user", when=datetime.datetime.now(), feature="guide")
        self.spend(2, 40.0, when=datetime.datetime.now())
        body = self.client.get("/users/ana/ai/usage").json()
        self.assertEqual((body["total"]["calls"], body["total"]["cost"]), (2, 5.0))
        self.assertEqual({s["name"]: s["cost"] for s in body["by_source"]}, {"group": 2.0, "user": 3.0})
        self.assertEqual({f["name"]: f["cost"] for f in body["by_feature"]}, {"chat": 2.0, "guide": 3.0})
        month = body["months"][0]
        self.assertEqual((month["group_cost"], month["user_cost"]), (2.0, 3.0))

    def test_nothing_of_what_only_the_admins_see_is_in_it_and_the_budget_is(self):
        self.spend(1, 1.0, when=datetime.datetime.now())
        body = self.client.get("/users/ana/ai/usage").json()
        for admin_only in ("group_paid_by_user", "by_tools", "price_stamp"):
            self.assertNotIn(admin_only, body)
        self.assertEqual((body["budget"]["group"]["cap"], body["budget"]["user"]["cap"], body["budget"]["user"]["spent"]), (20, 4, 1.0))

    def test_a_month_shows_its_days(self):
        self.spend(1, 1.0, when=datetime.datetime(2026, 10, 3, 10))
        body = self.client.get("/users/ana/ai/usage?month=2026-10").json()
        self.assertEqual(body["days"], [{"date": "2026-10-03", "calls": 1, "cost": 1.0}])
        self.assertEqual(self.client.get("/users/ana/ai/usage?month=2026-13").status_code, 422)

    def test_the_status_carries_the_budget_and_an_admin_cannot_read_a_players_spending(self):
        self.assertIn("budget", self.client.get("/users/ana/ai").json())
        self.user.username, self.user.is_admin = "root", 1
        self.assertEqual(self.client.get("/users/ana/ai/usage").status_code, 403)


class AdminRoutesTests(Base):
    def test_the_admin_gets_the_budget_and_gives_a_player_another_one(self):
        self.spend(1, 2.0, when=datetime.datetime.now())
        with patched(**{"ai.group_budget_month": 20, "ai.user_budget_month": 5}):
            body = manage_route.get_ai_budgets(self.db)
            self.assertEqual((body["group"]["cap"], body["group"]["spent"], body["default_user_cap"]), (20, 2.0, 5))
            changed = manage_route.put_ai_budget(2, manage_route.BudgetBody(usd=8), self.db)
        self.assertEqual((changed["name"], changed["cap"], changed["override"]), ("Beto", 8, 8))
        with patched(**{"ai.user_budget_month": 5}):
            back = manage_route.put_ai_budget(2, manage_route.BudgetBody(usd=None), self.db)
        self.assertEqual((back["cap"], back["override"]), (5, None))

    def test_the_emergency_account_and_unknown_players_have_no_budget(self):
        from fastapi import HTTPException

        for user_id in (3, 999):
            with self.assertRaises(HTTPException) as caught:
                manage_route.put_ai_budget(user_id, manage_route.BudgetBody(usd=1), self.db)
            self.assertEqual(caught.exception.status_code, 404)

    def test_a_budget_is_whole_dollars_between_zero_and_ten_thousand(self):
        from pydantic import ValidationError

        for bad in (-1, 10001):
            with self.assertRaises(ValidationError):
                manage_route.BudgetBody(usd=bad)
        self.assertEqual(manage_route.BudgetBody(usd=0).usd, 0)

    def test_the_settings_are_whole_dollars_with_zero_meaning_no_limit(self):
        for key in ("ai.group_budget_month", "ai.user_budget_month"):
            self.assertEqual(settings.REGISTRY[key].default, 0)
            self.assertIsNone(settings.REGISTRY[key].check(0))
            self.assertIsNotNone(settings.REGISTRY[key].check(10001))
            self.assertIsNotNone(settings.REGISTRY[key].check(-1))

    def test_the_ledger_knows_the_budget_status(self):
        self.assertEqual(ai_ledger.BUDGET, "budget")


if __name__ == "__main__":
    unittest.main()
