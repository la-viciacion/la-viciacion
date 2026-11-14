"""The wallet of the group's key: what a player put in and what is left of it. It counts only what the group's key paid, from the moment
of the first contribution (or the date an admin chose) and it stops a player whose balance is spent. It is always on: a player has 0
until something is put in for them, unless an admin took the limit off them."""
import datetime
import unittest
from unittest import mock

from fastapi import HTTPException
from pydantic import ValidationError

from src.database import models
from src.routers.manage import ai_usage as manage_route
from src.utils import ai_budget, ai_source, ai_wallet, messages
from tests import ai_env
from tests.sqlite_db import make_session
from tests.test_ai_budget import KEY, NOW, patched
from tests.test_chat import seed

START = datetime.datetime(2026, 11, 10, 9, 0)


class Base(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        seed(self.db)

    def put(self, user=1, usd=2.0, when=START):
        self.db.add(models.AiWalletEntry(user_id=user, amount_micros=round(usd * 1_000_000), created_at=when))
        self.db.commit()

    def spend(self, user=1, dollars=1.0, source="group", when=NOW, cost=True, free=False):
        self.db.add(models.AiUsage(
            created_at=when, user_id=user, feature="chat", key_source=source, status="ok",
            cost_micros=int(dollars * 1_000_000) if cost else None, provider="openai", model="gpt-4.1-mini", free_plan=free,
        ))
        self.db.commit()


class BalanceTests(Base):
    def test_a_player_has_nothing_until_something_is_put_in_for_them(self):
        with patched():
            self.assertEqual(ai_wallet.player(self.db, 1), {"contributed": 0.0, "spent": 0.0, "balance": 0.0, "since": None, "unlimited": False})
            self.assertEqual(ai_budget.exceeded(self.db, 1, NOW), ai_budget.WALLET)  # with no contribution at all, nobody uses the group's key
            self.put(1, 2.0)
            self.assertIsNone(ai_budget.exceeded(self.db, 1, NOW))

    def test_the_balance_is_what_was_put_in_minus_what_the_groups_key_spent_for_that_player(self):
        with patched():
            self.put(1, 2.0)
            self.put(2, 5.0)
            self.spend(1, 0.5)
            self.spend(2, 1.25)
            self.assertEqual((ai_wallet.balance(self.db, 1), ai_wallet.balance(self.db, 2)), (1_500_000, 3_750_000))

    def test_only_what_the_group_paid_at_its_real_cost_after_the_start_counts(self):
        with patched():
            self.put(1, 5.0)
            self.spend(1, 99.0, source="user")  # their own key: nobody else's money
            self.spend(1, 99.0, free=True)  # a free plan really cost nothing
            self.spend(1, 99.0, cost=False)  # no known price
            self.spend(1, 99.0, when=START - datetime.timedelta(seconds=1))  # before the wallet started
            self.assertEqual(ai_wallet.spent(self.db, 1), 0)
            self.spend(1, 1.0)
            self.assertEqual(ai_wallet.balance(self.db, 1), 4_000_000)

    def test_a_refund_is_a_negative_entry(self):
        with patched():
            self.put(1, 5.0)
            self.put(1, -2.0)
            self.assertEqual(ai_wallet.contributed(self.db, 1), 3_000_000)

    def test_an_admin_can_choose_the_day_it_starts_counting(self):
        self.put(1, 5.0, when=datetime.datetime(2026, 11, 14, 10, 0))
        self.spend(1, 1.0, when=datetime.datetime(2026, 11, 12, 10, 0))
        with patched():
            self.assertEqual(ai_wallet.spent(self.db, 1), 0)  # the first top-up was after it
        with patched(**{"ai.wallet_start": "2026-11-01"}):
            self.assertEqual(ai_wallet.spent(self.db, 1), 1_000_000)
            self.assertEqual(ai_wallet.start(self.db), datetime.datetime(2026, 11, 1))


class EnforcementTests(Base):
    def test_a_player_with_nothing_left_is_stopped_and_one_with_balance_is_not(self):
        with patched():
            self.put(1, 1.0)
            self.put(2, 1.0)
            self.spend(1, 1.0)
            self.assertEqual(ai_budget.exceeded(self.db, 1, NOW), ai_budget.WALLET)  # exactly 0 is nothing left
            self.assertIsNone(ai_budget.exceeded(self.db, 2, NOW))

    def test_the_balance_can_go_negative_because_a_call_costs_what_it_costs(self):
        with patched():
            self.put(1, 1.0)
            self.spend(1, 1.4)
            self.assertEqual(ai_wallet.balance(self.db, 1), -400_000)
            self.assertEqual(ai_budget.exceeded(self.db, 1, NOW), ai_budget.WALLET)

    def test_a_player_who_never_put_anything_in_is_stopped_whoever_else_did(self):
        with patched():
            self.put(1, 1.0)
            self.assertEqual(ai_budget.exceeded(self.db, 2, NOW), ai_budget.WALLET)

    def test_an_admin_can_take_the_limit_off_a_player_and_put_it_back(self):
        with patched():
            self.assertEqual(ai_budget.exceeded(self.db, 1, NOW), ai_budget.WALLET)
            ai_wallet.set_unlimited(self.db, 1, True)
            self.assertTrue(ai_wallet.unlimited(self.db, 1))
            self.assertIsNone(ai_budget.exceeded(self.db, 1, NOW))
            self.spend(1, 50.0)  # whatever they spend, with no contribution
            self.assertIsNone(ai_budget.exceeded(self.db, 1, NOW))
            self.assertEqual(ai_budget.exceeded(self.db, 2, NOW), ai_budget.WALLET)  # the others keep the limit
            ai_wallet.set_unlimited(self.db, 1, False)
            self.assertEqual(ai_budget.exceeded(self.db, 1, NOW), ai_budget.WALLET)

    def test_the_monthly_cap_still_stops_a_player_without_a_wallet_limit(self):
        with patched(**{"ai.user_budget_month": 1}):
            ai_wallet.set_unlimited(self.db, 1, True)
            self.spend(1, 1.0)
            self.assertEqual(ai_budget.exceeded(self.db, 1, NOW), ai_budget.USER)

    def test_a_top_up_gives_the_access_back(self):
        with patched():
            self.put(1, 1.0)
            self.spend(1, 1.0)
            self.assertEqual(ai_budget.exceeded(self.db, 1, NOW), ai_budget.WALLET)
            self.put(1, 2.0, when=NOW)
            self.assertIsNone(ai_budget.exceeded(self.db, 1, NOW))

    def test_the_monthly_budgets_still_apply_on_top(self):
        with patched(**{"ai.user_budget_month": 1}):
            self.put(1, 50.0)
            self.spend(1, 1.0)
            self.assertEqual(ai_budget.exceeded(self.db, 1, NOW), ai_budget.USER)

    def test_the_decision_blocks_the_groups_key_and_with_an_own_key_goes_on_with_it(self):
        with patched(**{"chat.key_source": "group_then_user"}):
            self.put(2, 1.0)
            decision = ai_source.decide(self.db, 1, "chat")
            self.assertEqual((decision.source, decision.blocked), (None, ai_budget.WALLET))
            self.assertTrue(ai_source.blocked_message(ai_budget.WALLET, "chat").startswith(messages.WALLET_EMPTY))
            dek = ai_env.give_key(self.db, 1, KEY, "gpt-5-mini")
            decision = ai_source.decide(self.db, 1, "chat", dek)
            self.assertEqual((decision.source.key_source, decision.blocked), ("user", ai_budget.WALLET))


class OverviewTests(Base):
    def test_the_admin_sees_the_total_available_each_players_part_and_the_latest_entries(self):
        with patched():
            self.put(1, 3.0)
            self.put(2, 2.0)
            self.spend(1, 0.5)
            body = ai_wallet.overview(self.db)
        self.assertEqual(body["start"], "2026-11-10")
        self.assertEqual(body["total"], {"contributed": 5.0, "spent": 0.5, "available": 4.5, "unassigned": 0.0})
        self.assertEqual([(p["name"], p["contributed"], p["spent"], p["balance"]) for p in body["players"]], [("Ana", 3.0, 0.5, 2.5), ("Beto", 2.0, 0.0, 2.0)])
        self.assertEqual([p["unlimited"] for p in body["players"]], [False, False])
        self.assertEqual([e["name"] for e in body["entries"]], ["Beto", "Ana"])  # newest first

    def test_what_the_app_spent_with_no_player_is_in_the_total_and_shown_apart(self):
        with patched():
            self.put(1, 3.0)
            self.spend(1, 0.5)
            self.db.add(models.AiUsage(created_at=NOW, user_id=None, feature="notice", key_source="group", status="ok", cost_micros=250_000, provider="openai", model="m"))
            self.db.commit()
            body = ai_wallet.overview(self.db)
        self.assertEqual(body["total"], {"contributed": 3.0, "spent": 0.75, "available": 2.25, "unassigned": 0.25})
        self.assertEqual(sum(p["spent"] for p in body["players"]) + body["total"]["unassigned"], body["total"]["spent"])

    def test_the_money_of_a_deleted_account_stays_in_the_total(self):
        with patched():
            self.put(1, 3.0)
            self.db.query(models.AiWalletEntry).update({"user_id": None})
            self.db.commit()
            body = ai_wallet.overview(self.db)
        self.assertEqual(body["total"]["contributed"], 3.0)
        self.assertEqual([p["contributed"] for p in body["players"]], [0.0, 0.0])

    def test_the_player_sees_only_their_own_part(self):
        with patched():
            self.put(1, 3.0)
            self.put(2, 9.0)
            self.spend(1, 1.0)
            self.assertEqual(ai_wallet.player(self.db, 1), {"contributed": 3.0, "spent": 1.0, "balance": 2.0, "since": "2026-11-10", "unlimited": False})


class AdminRoutesTests(Base):
    admin = mock.Mock(id=1)

    def test_an_admin_writes_down_a_contribution_and_it_is_in_the_overview(self):
        with patched():
            body = manage_route.post_wallet_entry(manage_route.WalletEntryBody(user_id=2, usd=2.5, note=" bizum "), self.admin, self.db)
        self.assertEqual(body["total"]["contributed"], 2.5)
        entry = body["entries"][0]
        self.assertEqual((entry["name"], entry["usd"], entry["note"]), ("Beto", 2.5, "bizum"))

    def test_the_emergency_account_unknown_players_and_a_zero_are_refused(self):
        for user_id, usd, status in ((3, 1.0, 404), (999, 1.0, 404), (1, 0.0, 400)):
            with self.assertRaises(HTTPException) as caught:
                manage_route.post_wallet_entry(manage_route.WalletEntryBody(user_id=user_id, usd=usd), self.admin, self.db)
            self.assertEqual(caught.exception.status_code, status)

    def test_an_admin_takes_the_limit_off_a_player_and_the_overview_says_so(self):
        with patched():
            body = manage_route.put_wallet_unlimited(2, manage_route.WalletUnlimitedBody(unlimited=True), self.db)
            self.assertEqual({p["name"]: p["unlimited"] for p in body["players"]}, {"Ana": False, "Beto": True})
            body = manage_route.put_wallet_unlimited(2, manage_route.WalletUnlimitedBody(unlimited=False), self.db)
            self.assertEqual({p["name"]: p["unlimited"] for p in body["players"]}, {"Ana": False, "Beto": False})
        for user_id in (3, 999):
            with self.assertRaises(HTTPException) as caught:
                manage_route.put_wallet_unlimited(user_id, manage_route.WalletUnlimitedBody(unlimited=True), self.db)
            self.assertEqual(caught.exception.status_code, 404)

    def test_an_amount_is_within_ten_thousand_dollars_either_way(self):
        for bad in (10001, -10001):
            with self.assertRaises(ValidationError):
                manage_route.WalletEntryBody(user_id=1, usd=bad)

    def test_the_start_date_goes_to_the_settings_and_null_clears_it(self):
        with mock.patch.object(manage_route.settings, "set_values") as saved, patched():
            manage_route.put_wallet_start(manage_route.WalletStartBody(date=datetime.date(2026, 11, 1)), self.admin, self.db)
            manage_route.put_wallet_start(manage_route.WalletStartBody(date=None), self.admin, self.db)
        self.assertEqual([c.args[1] for c in saved.call_args_list], [{"ai.wallet_start": "2026-11-01"}, {"ai.wallet_start": None}])

    def test_the_start_setting_is_a_real_date_or_nothing(self):
        spec = ai_wallet.settings.REGISTRY["ai.wallet_start"]
        self.assertTrue(spec.resettable)
        self.assertIsNone(spec.check("2026-11-01"))
        for bad in ("2026-13-01", "01/11/2026", "x"):
            self.assertIsNotNone(spec.check(bad))


if __name__ == "__main__":
    unittest.main()
