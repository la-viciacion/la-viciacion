"""Streaks of consecutive played days. Pure functions: everything is derived
from the list of days a user played, nothing is stored."""
import datetime


def streak_summary(played_dates: list[datetime.date], today: datetime.date, season: int):
    """Return (best_streak_end_date, best_streak, current_streak,
    best_gap_end_date, best_gap, current_gap) for a sorted list of played days.

    A streak is a run of consecutive days; the current one still counts if the last
    played day is today or yesterday. A gap is a run of days without playing.
    """
    if len(played_dates) == 0:
        first_day = datetime.datetime.strptime(f"{season}-01-01", "%Y-%m-%d")
        return first_day, 0, 0, first_day, 0, 0
    # runs of consecutive days; a later run wins a tie for the best
    max_streak = 0
    end_max_streak_date = None
    run = 0
    for i, day in enumerate(played_dates):
        run = run + 1 if i > 0 and (day - played_dates[i - 1]).days == 1 else 1
        if run >= max_streak:
            max_streak = run
            end_max_streak_date = day
    # the last run only counts as current if its last day is today or yesterday
    days_since_last = (today - played_dates[-1]).days
    current_streak = run if days_since_last in (0, 1) else 0

    max_gap = 0
    end_max_gap_date = None
    current_gap = 0
    for i in range(1, len(played_dates)):
        gap = (played_dates[i] - played_dates[i - 1]).days - 1
        if gap > 0:
            current_gap = gap
            if gap >= max_gap:
                max_gap = gap
                end_max_gap_date = played_dates[i]
    last_gap = days_since_last - 1
    if last_gap > 0:
        current_gap = last_gap
        if last_gap > max_gap:
            max_gap = last_gap
            end_max_gap_date = today
    return end_max_streak_date, max_streak, current_streak, end_max_gap_date, max_gap, current_gap


def lost_streak(played_dates: list[datetime.date], today: datetime.date, minimum: int = 10) -> int | None:
    """Length of the streak a user has just lost, or None.

    A streak is lost the day the last played day is two days ago (yesterday was
    the first day without playing), so this is true on exactly one day and a
    daily check announces it once without remembering anything.
    """
    if not played_dates:
        return None
    last = played_dates[-1]
    if (today - last).days != 2:
        return None
    played = set(played_dates)
    length, day = 0, last
    while day in played:
        length += 1
        day -= datetime.timedelta(days=1)
    return length if length > minimum else None
