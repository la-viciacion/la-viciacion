import unittest
from unittest import mock

import run_tests


class ModulesTests(unittest.TestCase):
    def test_every_test_module_is_found_and_the_mariadb_ones_can_be_left_out(self):
        everything = run_tests.modules()
        self.assertIn("test_run_tests", everything)
        self.assertTrue(any(name.startswith("test_mariadb_") for name in everything))
        without = run_tests.modules(with_db=False)
        self.assertFalse(any(name.startswith("test_mariadb_") for name in without))
        self.assertEqual(set(everything) - set(without), {name for name in everything if name.startswith("test_mariadb_")})

    def test_the_migration_modules_can_be_left_out_but_not_the_history_guards(self):
        without = run_tests.modules(with_migrations=False)
        self.assertNotIn("test_mariadb_migration_chain", without)
        self.assertNotIn("test_mariadb_migrations", without)
        self.assertNotIn("test_mariadb_v1_upgrade", without)
        self.assertIn("test_migrations", without)  # the history guards need no MariaDB and take seconds
        self.assertIn("test_mariadb_api_users", without)

    def test_a_pattern_keeps_the_modules_that_have_it(self):
        found = run_tests.modules("achievement")
        self.assertTrue(found)
        self.assertTrue(all("achievement" in name for name in found))
        self.assertEqual(run_tests.modules("no-such-module-at-all"), [])


class OrderTests(unittest.TestCase):
    def test_the_slowest_goes_first_and_what_is_not_timed_is_taken_as_slow(self):
        timings = {"a": 5.0, "b": 90.0, "c": 1.0}
        self.assertEqual(run_tests.order(["a", "c", "b"], timings), ["b", "a", "c"])
        self.assertEqual(run_tests.order(["a", "new", "b"], timings)[1], "new")  # 60 s: after b (90) and before a (5)

    def test_the_weight_of_a_module_is_its_own_time_or_the_sum_of_its_classes(self):
        timings = {"whole": 12.0, "split.A": 30.0, "split.B": 45.5, "splitter": 99.0}
        self.assertEqual(run_tests.weight("whole", timings), 12.0)
        self.assertEqual(run_tests.weight("split", timings), 75.5)  # "splitter" is another module
        self.assertIsNone(run_tests.weight("never", timings))


class JobsTests(unittest.TestCase):
    def test_only_a_module_that_was_slow_is_split_by_class(self):
        timings = {"slow": 200.0, "quick": 3.0}
        with mock.patch.object(run_tests, "classes_of", return_value=["slow.A", "slow.B"]) as classes:
            jobs = run_tests.jobs_for(["slow", "quick", "unknown"], timings, {})
        self.assertEqual(jobs, ["slow.A", "slow.B", "quick", "unknown"])
        classes.assert_called_once_with("slow", {})

    def test_a_split_module_is_judged_by_the_sum_of_its_classes(self):
        with mock.patch.object(run_tests, "classes_of", return_value=["m.A", "m.B"]):
            self.assertEqual(run_tests.jobs_for(["m"], {"m.A": 40.0, "m.B": 40.0}, {}), ["m.A", "m.B"])
            self.assertEqual(run_tests.jobs_for(["m"], {"m.A": 10.0, "m.B": 10.0}, {}), ["m"])


class SummaryTests(unittest.TestCase):
    def test_it_reads_how_many_ran_and_whether_they_passed(self):
        self.assertEqual(run_tests.summary_of("....\n----\nRan 4 tests in 0.1s\n\nOK\n"), (4, True))
        self.assertEqual(run_tests.summary_of("Ran 1 test in 0.1s\n\nOK (skipped=1)\n"), (1, True))
        self.assertEqual(run_tests.summary_of("Ran 3 tests in 1s\n\nFAILED (failures=1)\n"), (3, False))
        self.assertEqual(run_tests.summary_of("ImportError: no module\n"), (0, False))


if __name__ == "__main__":
    unittest.main()
