"""What the app costs, derived from the rates (utils/costs.py), and how the rates are kept and checked (crud/costs.py)."""
import datetime
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.crud import costs as crud
from src.database import models
from src.utils import costs

D = datetime.date
DT = datetime.datetime


def server(starts_on=D(2025, 6, 1), ends_on=None, amount=490, hourly=8000):
    return {"kind": "server", "amount_cents": amount, "hourly_micros": hourly, "period": "month", "starts_on": starts_on, "ends_on": ends_on}


def manual(amount, period, starts_on, ends_on=None, kind="domain"):
    return {"kind": kind, "amount_cents": amount, "hourly_micros": None, "period": period, "starts_on": starts_on, "ends_on": ends_on}


OCT_1, NOV_1 = DT(2026, 10, 1), DT(2026, 11, 1)
NOW = DT(2026, 10, 11, 0, 0)  # 10 days into October: 240 hours


class MonthCostTests(unittest.TestCase):
    def test_the_server_is_billed_by_the_hour_up_to_its_monthly_price(self):
        self.assertEqual(round(costs.month_cost(server(), OCT_1, NOW), 4), 1.92)  # 240 h * 0.008
        self.assertEqual(costs.month_cost(server(), OCT_1, DT(2026, 10, 31, 23)), 4.9)  # 743 h * 0.008 would be 5,94
        self.assertEqual(costs.month_cost(server(), OCT_1, NOV_1), 4.9)

    def test_a_server_that_began_this_month_pays_only_since_then(self):
        self.assertEqual(round(costs.month_cost(server(starts_on=D(2026, 10, 10)), OCT_1, NOW), 4), 0.192)  # 24 h

    def test_a_rate_that_ended_stops_counting_the_day_after_its_last_day(self):
        item = server(ends_on=D(2026, 10, 5))  # applies through the 5th: 5 days = 120 h
        self.assertEqual(round(costs.month_cost(item, OCT_1, NOV_1), 4), 0.96)
        self.assertEqual(costs.month_cost(item, NOV_1, DT(2026, 12, 1)), 0)

    def test_a_monthly_rate_is_split_by_the_share_of_the_month_it_covers(self):
        item = manual(3100, "month", D(2026, 1, 1))  # 31 days in October
        self.assertEqual(round(costs.month_cost(item, OCT_1, DT(2026, 10, 11)), 4), 10.0)  # 10 days of 31
        self.assertEqual(costs.month_cost(item, OCT_1, NOV_1), 31.0)

    def test_a_yearly_rate_is_spread_over_twelve_months(self):
        item = manual(1200, "year", D(2026, 3, 1))
        self.assertEqual(costs.month_cost(item, OCT_1, NOV_1), 1.0)
        self.assertEqual(costs.month_cost(item, DT(2026, 2, 1), OCT_1), 0)  # before it began

    def test_a_one_off_cost_counts_whole_in_the_month_of_its_date_and_only_once_it_has_come(self):
        item = manual(1500, "once", D(2026, 10, 20))
        self.assertEqual(costs.month_cost(item, OCT_1, NOW), 0)  # not yet, "so far"
        self.assertEqual(costs.month_cost(item, OCT_1, NOV_1), 15.0)
        self.assertEqual(costs.month_cost(item, NOV_1, DT(2026, 12, 1)), 0)
        self.assertEqual(costs.month_cost(item, OCT_1, DT(2026, 10, 20, 12)), 15.0)  # the day itself

    def test_nothing_before_the_month_starts(self):
        self.assertEqual(costs.month_cost(server(), OCT_1, OCT_1), 0)


class SummaryTests(unittest.TestCase):
    def test_without_any_rate_there_is_nothing_to_say(self):
        self.assertIsNone(costs.summary([], NOW))

    def test_the_month_the_year_and_the_whole_life_so_far_and_by_the_end(self):
        result = costs.summary([server()], NOW)  # since 2025-06-01
        self.assertEqual(result["month"], {"so_far": 1.92, "projected": 4.9})
        self.assertEqual(result["year"], {"so_far": 46.02, "projected": 58.8})  # nine whole months, 1,92 and the ones still to come
        self.assertEqual(result["total"], {"so_far": 80.32, "since": "2025-06-01"})  # + 7 months of 2025
        self.assertEqual(result["currency"], "EUR")

    def test_the_year_projection_reaches_december_not_just_the_end_of_the_month(self):
        result = costs.summary([server(starts_on=D(2026, 1, 1))], DT(2026, 10, 11, 0, 0))
        self.assertEqual(result["year"]["projected"], 58.8)  # twelve months at 4,90
        self.assertGreater(result["year"]["projected"], result["month"]["projected"] + result["year"]["so_far"] - result["month"]["so_far"])

    def test_a_server_created_this_year_counts_from_its_first_day(self):
        result = costs.summary([server(starts_on=D(2026, 8, 20))], NOW)
        self.assertEqual(result["year"]["so_far"], 9.12)  # 12 days of August (2,30), September (4,90), 1,92
        self.assertEqual(result["total"]["so_far"], 9.12)

    def test_a_price_change_in_the_middle_of_a_month_is_split_between_the_two_rates(self):
        old = server(starts_on=D(2026, 1, 1), ends_on=D(2026, 9, 30), amount=490, hourly=8000)
        new = server(starts_on=D(2026, 10, 1), amount=1000, hourly=20000)
        result = costs.summary([old, new], NOW)
        self.assertEqual(result["month"]["so_far"], 4.8)  # 240 h * 0.02, not 0.008
        self.assertEqual(result["year"]["so_far"], round(9 * 4.9 + 4.8, 2))

    def test_other_costs_add_to_the_server_in_the_same_figures(self):
        result = costs.summary([server(starts_on=D(2026, 1, 1)), manual(1200, "year", D(2026, 1, 1))], NOW)
        self.assertEqual(result["year"]["projected"], round(12 * 4.9 + 12.0, 2))
        self.assertEqual(result["month"]["projected"], 5.9)

    def test_what_the_month_costs_beyond_the_rates_only_weighs_on_the_running_month(self):
        result = costs.summary([server(starts_on=D(2026, 1, 1))], NOW, extra=2.4)
        self.assertEqual(result["month"], {"so_far": 4.32, "projected": 7.3})
        self.assertEqual(result["year"]["so_far"], round(9 * 4.9 + 4.32, 2))
        self.assertEqual(result["year"]["projected"], round(12 * 4.9 + 2.4, 2))

    def test_in_january_the_year_is_the_month_and_in_december_the_projection_closes_it(self):
        january = costs.summary([server()], DT(2026, 1, 11))
        self.assertEqual(january["year"]["so_far"], january["month"]["so_far"])
        self.assertEqual(costs.summary([server()], DT(2026, 12, 31, 12))["year"]["projected"], 58.8)

    def test_a_rate_that_starts_in_the_future_is_projected_but_not_counted_yet(self):
        result = costs.summary([server(starts_on=D(2026, 12, 1))], NOW)
        self.assertEqual(result["month"], {"so_far": 0, "projected": 0})
        self.assertEqual(result["year"], {"so_far": 0, "projected": 4.9})


class MonthsTests(unittest.TestCase):
    ITEMS = [server(starts_on=D(2026, 1, 1)), manual(1200, "year", D(2026, 1, 1))]

    def test_there_are_twelve_months_closed_then_the_running_one_then_the_future(self):
        result = costs.months(self.ITEMS, 2026, NOW)
        self.assertEqual([m["month"] for m in result], [f"2026-{n:02d}" for n in range(1, 13)])
        self.assertEqual([m["state"] for m in result], ["closed"] * 9 + ["running"] + ["future"] * 2)

    def test_a_closed_month_is_what_it_cost_by_kind_with_nothing_forecast(self):
        january = costs.months(self.ITEMS, 2026, NOW)[0]
        self.assertEqual(january["kinds"], {"server": 4.9, "domain": 1.0})
        self.assertEqual(january["forecast"], 0)

    def test_the_running_month_is_what_has_been_spent_and_what_is_left_to_forecast(self):
        october = costs.months(self.ITEMS, 2026, NOW)[9]
        self.assertEqual(october["kinds"], {"server": 1.92, "domain": 0.32})
        self.assertEqual(october["forecast"], 3.66)  # 4,90 + 1,00 less what is already counted

    def test_a_future_month_is_all_forecast_and_has_nothing_spent(self):
        november = costs.months(self.ITEMS, 2026, NOW)[10]
        self.assertEqual(november["kinds"], {"server": 0, "domain": 0})
        self.assertEqual(november["forecast"], 5.9)

    def test_the_traffic_beyond_the_plan_is_the_servers_in_the_running_month_only(self):
        result = costs.months(self.ITEMS, 2026, NOW, extra=2.4)
        self.assertEqual(result[9]["kinds"]["server"], 4.32)
        self.assertEqual(result[9]["forecast"], 3.66)  # it is already spent: it does not change what is left
        self.assertEqual(result[8]["kinds"]["server"], 4.9)

    def test_a_past_year_is_all_closed_and_a_year_before_the_first_rate_is_empty(self):
        past = costs.months([server()], 2025, NOW)  # since 2025-06-01
        self.assertEqual({m["state"] for m in past}, {"closed"})
        self.assertEqual(past[0]["kinds"], {"server": 0})
        self.assertEqual(past[11]["kinds"], {"server": 4.9})
        self.assertEqual(sum(m["forecast"] for m in past), 0)

    def test_the_years_go_from_the_first_rate_to_the_running_year(self):
        self.assertEqual(costs.years([server()], NOW), [2025, 2026])
        self.assertEqual(costs.years([], NOW), [])

    def test_the_summary_carries_the_years_and_the_months_of_the_running_one(self):
        result = costs.summary(self.ITEMS, NOW, extra=2.4)
        self.assertEqual(result["years"], [2026])
        self.assertEqual(len(result["months"]), 12)
        self.assertEqual(result["months"][9]["kinds"]["server"], 4.32)


class KindsTests(unittest.TestCase):
    ITEMS = [server(starts_on=D(2026, 1, 1)), manual(1200, "year", D(2026, 1, 1)), manual(500, "once", D(2026, 10, 3), kind="other")]

    def test_each_kind_has_its_own_figures_and_the_server_comes_first(self):
        kinds = costs.summary(self.ITEMS, NOW)["kinds"]
        self.assertEqual([k["kind"] for k in kinds], ["server", "domain", "other"])
        server_kind, domain, other = kinds
        self.assertEqual(server_kind["month"], {"so_far": 1.92, "projected": 4.9})
        self.assertEqual(domain["year"], {"so_far": 9.32, "projected": 12.0})  # nine whole months of 1,00 and ten days of October
        self.assertEqual(other["month"], {"so_far": 5.0, "projected": 5.0})
        self.assertEqual(other["total"], {"so_far": 5.0})

    def test_the_kinds_add_up_to_the_whole(self):
        result = costs.summary(self.ITEMS, NOW, extra=2.4)
        for period in ("month", "year", "total"):
            self.assertAlmostEqual(sum(k[period]["so_far"] for k in result["kinds"]), result[period]["so_far"], places=1, msg=period)
        self.assertAlmostEqual(sum(k["year"]["projected"] for k in result["kinds"]), result["year"]["projected"], places=1)

    def test_what_the_month_costs_beyond_the_rates_is_the_servers(self):
        kinds = {k["kind"]: k for k in costs.summary(self.ITEMS, NOW, extra=2.4)["kinds"]}
        self.assertEqual(kinds["server"]["month"]["so_far"], 4.32)
        self.assertEqual(kinds["domain"]["month"]["so_far"], 0.32)  # 10 days of 31 of a euro a month

    def test_a_kind_with_no_rate_is_left_out_and_the_kind_does_not_carry_the_since_date(self):
        result = costs.summary([server()], NOW)
        self.assertEqual([k["kind"] for k in result["kinds"]], ["server"])
        self.assertNotIn("since", result["kinds"][0]["total"])
        self.assertEqual(result["total"]["since"], "2025-06-01")


PRICE = {"external_id": "42", "name": "Servidor lavi", "created": D(2025, 6, 1), "amount_cents": 490, "hourly_micros": 8000}


class DatabaseCase(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite://")
        models.CostItem.__table__.create(engine)
        self.db = sessionmaker(bind=engine)()
        self.addCleanup(engine.dispose)
        self.addCleanup(self.db.close)

    def rows(self):
        return [(r.starts_on, r.ends_on, r.amount_cents, r.hourly_micros) for r in self.db.query(models.CostItem).order_by(models.CostItem.starts_on)]


class SyncServerTests(DatabaseCase):
    def test_the_first_time_it_opens_a_rate_from_the_day_the_server_was_created(self):
        self.assertEqual(crud.sync_server(self.db, PRICE, D(2026, 11, 1)), "created")
        self.assertEqual(self.rows(), [(D(2025, 6, 1), None, 490, 8000)])
        row = self.db.query(models.CostItem).one()
        self.assertEqual((row.kind, row.period, row.source, row.external_id, row.name), ("server", "month", "hetzner", "42", "Servidor lavi"))

    def test_the_same_price_changes_nothing(self):
        crud.sync_server(self.db, PRICE, D(2026, 11, 1))
        self.assertEqual(crud.sync_server(self.db, PRICE, D(2026, 11, 2)), "unchanged")
        self.assertEqual(len(self.rows()), 1)

    def test_a_new_price_closes_the_rate_the_day_before_and_opens_another_from_today(self):
        crud.sync_server(self.db, PRICE, D(2026, 11, 1))
        self.assertEqual(crud.sync_server(self.db, {**PRICE, "amount_cents": 543, "hourly_micros": 8712}, D(2026, 11, 5)), "changed")
        self.assertEqual(self.rows(), [(D(2025, 6, 1), D(2026, 11, 4), 490, 8000), (D(2026, 11, 5), None, 543, 8712)])

    def test_a_change_on_the_day_a_rate_began_corrects_it_instead_of_closing_it(self):
        crud.sync_server(self.db, {**PRICE, "created": D(2026, 11, 5)}, D(2026, 11, 5))
        crud.sync_server(self.db, {**PRICE, "created": D(2026, 11, 5), "amount_cents": 543}, D(2026, 11, 5))
        self.assertEqual(self.rows(), [(D(2026, 11, 5), None, 543, 8000)])

    def test_a_manual_rate_and_another_server_are_left_alone(self):
        self.db.add(models.CostItem(name="Dominio", kind="domain", amount_cents=1200, period="year", starts_on=D(2026, 1, 1), source="manual"))
        self.db.commit()
        crud.sync_server(self.db, PRICE, D(2026, 11, 1))
        crud.sync_server(self.db, {**PRICE, "external_id": "43", "amount_cents": 999}, D(2026, 11, 1))
        crud.sync_server(self.db, {**PRICE, "amount_cents": 543}, D(2026, 11, 2))
        self.assertEqual(self.db.query(models.CostItem).count(), 4)  # domain, 42 (closed), 42 (new), 43

    def test_the_items_come_out_as_what_the_derivation_takes(self):
        crud.sync_server(self.db, PRICE, D(2026, 11, 1))
        self.assertEqual(costs.summary(crud.all_items(self.db), DT(2026, 11, 1, 12))["total"]["since"], "2025-06-01")


class CleanTests(unittest.TestCase):
    OK = {"name": " Dominio ", "kind": "domain", "amount": 12.5, "period": "year", "starts_on": D(2026, 1, 1), "ends_on": None, "note": " .com "}

    def test_a_valid_rate_is_trimmed_and_the_euros_become_cents(self):
        self.assertEqual(crud.clean(self.OK), {
            "name": "Dominio", "kind": "domain", "period": "year", "amount_cents": 1250, "starts_on": D(2026, 1, 1), "ends_on": None, "note": ".com",
        })
        self.assertEqual(crud.clean({**self.OK, "amount": 0.1 + 0.2})["amount_cents"], 30)  # no float noise

    def test_what_is_wrong_says_so_in_spanish(self):
        for change, text in (
            ({"name": "  "}, "concepto"), ({"name": "x" * 101}, "100"), ({"kind": "pizza"}, "tipo"), ({"period": "week"}, "periodicidad"),
            ({"amount": -1}, "importe"), ({"amount": None}, "importe"), ({"amount": 2_000_000}, "importe"), ({"starts_on": None}, "inicio"),
            ({"ends_on": D(2025, 12, 31)}, "anterior"), ({"note": "x" * 256}, "255"),
        ):
            with self.subTest(change=change), self.assertRaises(crud.CostError) as caught:
                crud.clean({**self.OK, **change})
            self.assertIn(text, str(caught.exception))

    def test_a_one_off_cost_has_a_day_and_no_end(self):
        self.assertIsNone(crud.clean({**self.OK, "period": "once", "ends_on": D(2026, 5, 1)})["ends_on"])


if __name__ == "__main__":
    unittest.main()
