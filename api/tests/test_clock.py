"""The tests run on a pinned clock (tests/clock.py). These tests keep it pinned."""
import ast
import datetime
import unittest
from pathlib import Path

from tests import clock

TESTS = Path(__file__).resolve().parent
READS = {"now", "today", "utcnow"}


def import_time_clock_reads(path: Path):
    """The clock reads that run when a test module is imported (module level and class bodies, `TODAY = date.today`
    included), which happen before the clock is pinned."""
    def walk(node):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                continue
            if isinstance(child, ast.Attribute) and child.attr in READS and ast.unparse(child.value) != "clock":
                yield child.lineno, ast.unparse(child)
            yield from walk(child)

    yield from walk(ast.parse(path.read_text(encoding="utf-8")))


class PinnedClockTests(unittest.TestCase):
    def test_the_clock_is_pinned_while_tests_run(self):
        self.assertEqual(datetime.date.today(), clock.PIN.date())
        self.assertEqual(datetime.date.today().year, clock.YEAR)
        # it keeps ticking, from the pinned moment
        self.assertLess(abs(datetime.datetime.now() - clock.PIN), datetime.timedelta(hours=1))

    def test_values_stay_real_dates_and_datetimes(self):
        day = datetime.date(2024, 2, 29)
        moment = datetime.datetime.combine(day, datetime.time(23, 59))
        for value in (day, moment, datetime.datetime.now(), datetime.date.today(), datetime.datetime.fromisoformat("2024-01-01T10:00:00")):
            self.assertEqual(type(value).__module__, "datetime")  # never an instance of the pinning classes
        self.assertIsInstance(moment, datetime.date)
        self.assertTrue(issubclass(datetime.datetime, datetime.date))
        self.assertEqual(moment - datetime.timedelta(days=1), datetime.datetime(2024, 2, 28, 23, 59))

    def test_hours_ago_never_cross_midnight(self):
        # the failure this module exists for: a fixture "5 hours ago" landing on yesterday when the suite runs at night
        self.assertEqual(clock.ago(hours=5).date(), clock.today())

    def test_no_test_module_reads_the_real_clock_when_it_is_imported(self):
        offenders = [
            f"{path.name}:{line}: {code}"
            for path in sorted(TESTS.glob("*.py"))
            if path.name not in ("clock.py", "test_clock.py")
            for line, code in import_time_clock_reads(path)
        ]
        self.assertEqual(offenders, [], "read at import time, before the clock is pinned: use clock.PIN, clock.YEAR or clock.today() inside the test")


if __name__ == "__main__":
    unittest.main()
