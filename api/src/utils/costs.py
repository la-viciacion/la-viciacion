"""What keeping the app running costs, derived from the rates in `cost_items` (nothing about a month is stored).

A rate is an amount per period with the days it applies. Its cost in any stretch of time is worked out when asked:
a monthly rate by the share of the month it covers, a yearly one the same over twelve, a one-off one whole in the
month of its date, and the server's, which Hetzner bills by the hour up to its monthly price, by the hours it covers
with that cap. Pure: the caller passes the rows and the clock. Euros, VAT included. Dates are the server's local ones."""
import datetime

KINDS = ("server", "domain", "other")
PERIODS = ("month", "year", "once")
PRECISION = 2


def _midnight(day: datetime.date) -> datetime.datetime:
    return datetime.datetime.combine(day, datetime.time())


def _month_start(moment: datetime.datetime) -> datetime.datetime:
    return moment.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _next_month(moment: datetime.datetime) -> datetime.datetime:
    return (moment + datetime.timedelta(days=32)).replace(day=1)


def month_cost(item: dict, month_start: datetime.datetime, until: datetime.datetime) -> float:
    """What `item` costs in the month that starts at `month_start`, up to `until` (the moment "so far" is counted to, or
    the month's end for what the month will cost). A rate with no end counts as running on."""
    month_end = _next_month(month_start)
    stop = min(until, month_end)
    if stop <= month_start:
        return 0.0
    amount = item["amount_cents"] / 100
    starts = _midnight(item["starts_on"])
    if item["period"] == "once":
        return amount if month_start <= starts < stop else 0.0
    begin = max(starts, month_start)
    finish = stop if item["ends_on"] is None else min(_midnight(item["ends_on"] + datetime.timedelta(days=1)), stop)
    overlap = (finish - begin).total_seconds()
    if overlap <= 0:
        return 0.0
    if item.get("hourly_micros"):
        return min(overlap / 3600 * item["hourly_micros"] / 1e6, amount)
    share = overlap / (month_end - month_start).total_seconds()
    return amount * share / (12 if item["period"] == "year" else 1)


def summary(items: list[dict], now: datetime.datetime, extra: float = 0.0) -> dict | None:
    """The cost of the running month, of the running year and of the whole life, so far and (month and year) by the end,
    assuming the rates that have no end go on. `extra` is what the running month costs beyond the rates (the traffic
    over the plan). None while there is no rate at all."""
    if not items:
        return None
    this_month = _month_start(now)

    def in_month(start: datetime.datetime, until: datetime.datetime) -> float:
        return sum(month_cost(item, start, until) for item in items)

    so_far = in_month(this_month, now) + extra
    month_end = in_month(this_month, _next_month(this_month)) + extra

    first = min(item["starts_on"] for item in items)
    closed_total = closed_year = 0.0
    start = _month_start(_midnight(first))
    while start < this_month:
        amount = in_month(start, _next_month(start))
        closed_total += amount
        if start.year == now.year:
            closed_year += amount
        start = _next_month(start)

    ahead = 0.0  # the months of this year still to come
    start = _next_month(this_month)
    while start.year == now.year:
        ahead += in_month(start, _next_month(start))
        start = _next_month(start)

    return {
        "currency": "EUR",
        "month": {"so_far": round(so_far, PRECISION), "projected": round(month_end, PRECISION)},
        "year": {"so_far": round(closed_year + so_far, PRECISION), "projected": round(closed_year + month_end + ahead, PRECISION)},
        "total": {"so_far": round(closed_total + so_far, PRECISION), "since": first.isoformat()},
    }
