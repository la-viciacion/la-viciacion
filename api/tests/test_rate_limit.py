import unittest

from src.utils.rate_limit import AttemptLimiter


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class AttemptLimiterTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.limiter = AttemptLimiter(3, 600, clock=self.clock)

    def test_blocks_after_max_failures_and_says_for_how_long(self):
        for _ in range(2):
            self.limiter.fail("ana")
        self.assertEqual(self.limiter.retry_after("ana"), 0)
        self.limiter.fail("ana")
        self.assertGreater(self.limiter.retry_after("ana"), 0)
        self.assertLessEqual(self.limiter.retry_after("ana"), 601)

    def test_keys_are_independent(self):
        for _ in range(3):
            self.limiter.fail("ana")
        self.assertEqual(self.limiter.retry_after("bob"), 0)

    def test_failures_expire_with_the_window(self):
        for _ in range(3):
            self.limiter.fail("ana")
        self.clock.now += 601
        self.assertEqual(self.limiter.retry_after("ana"), 0)

    def test_window_slides_instead_of_resetting(self):
        self.limiter.fail("ana")
        self.clock.now += 400
        self.limiter.fail("ana")
        self.limiter.fail("ana")
        self.assertGreater(self.limiter.retry_after("ana"), 0)
        self.clock.now += 201  # the first failure leaves the window
        self.assertEqual(self.limiter.retry_after("ana"), 0)

    def test_reset_forgets_the_key(self):
        for _ in range(3):
            self.limiter.fail("ana")
        self.limiter.reset("ana")
        self.assertEqual(self.limiter.retry_after("ana"), 0)

    def test_memory_is_bounded(self):
        from src.utils import rate_limit

        original = rate_limit.MAX_KEYS
        rate_limit.MAX_KEYS = 5
        try:
            for i in range(20):
                self.limiter.fail(f"user{i}")
            self.assertLessEqual(len(self.limiter._failures), 5)
        finally:
            rate_limit.MAX_KEYS = original


if __name__ == "__main__":
    unittest.main()


from src.utils.rate_limit import Scope, UsageLimiter  # noqa: E402


class UsageLimiterTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.limiter = UsageLimiter(clock=self.clock)

    def user(self, name="ana", minute=2, hour=0, day=0):
        return Scope(f"user:{name}", "user", ((60, minute), (3600, hour), (86400, day)))

    def test_it_lets_through_up_to_the_most_of_the_window_and_says_when_one_more_fits(self):
        for _ in range(2):
            self.assertIsNone(self.limiter.acquire([self.user()]))
            self.clock.now += 10
        refused = self.limiter.acquire([self.user()])
        self.assertEqual((refused.scope, refused.window), ("user", 60))
        self.assertEqual(refused.wait, 41)  # the first use was 20 s ago and leaves the minute in 40 s (+1 rounded up)
        self.clock.now += refused.wait
        self.assertIsNone(self.limiter.acquire([self.user()]))

    def test_a_refused_use_is_not_recorded_so_waiting_is_enough(self):
        for _ in range(2):
            self.limiter.acquire([self.user()])
        for _ in range(50):
            self.assertIsNotNone(self.limiter.acquire([self.user()]))
        self.clock.now += 61
        self.assertIsNone(self.limiter.acquire([self.user()]))

    def test_each_window_has_its_own_most_and_the_longest_wait_is_told(self):
        scope = self.user(minute=5, hour=3)
        for _ in range(3):
            self.assertIsNone(self.limiter.acquire([scope]))
            self.clock.now += 5
        refused = self.limiter.acquire([scope])  # the minute still has room, the hour has not
        self.assertEqual((refused.window, refused.wait), (3600, 3586))
        both = self.user(minute=1, hour=1)
        self.limiter.clear()
        self.assertIsNone(self.limiter.acquire([both]))
        refused = self.limiter.acquire([both])  # both are used up: the one that frees last is told
        self.assertEqual(refused.window, 3600)

    def test_the_day_is_the_last_24_hours(self):
        scope = self.user(minute=0, day=2)
        self.assertIsNone(self.limiter.acquire([scope]))
        self.clock.now += 3600
        self.assertIsNone(self.limiter.acquire([scope]))
        self.assertEqual(self.limiter.acquire([scope]).window, 86400)
        self.clock.now += 86400 - 3600
        self.assertIsNone(self.limiter.acquire([scope]))  # the first one has left the 24 hours

    def test_users_do_not_share_their_allowance(self):
        for _ in range(2):
            self.limiter.acquire([self.user("ana")])
        self.assertIsNotNone(self.limiter.acquire([self.user("ana")]))
        self.assertIsNone(self.limiter.acquire([self.user("bob")]))

    def test_zero_is_no_limit_and_records_nothing(self):
        free = self.user(minute=0)
        for _ in range(500):
            self.assertIsNone(self.limiter.acquire([free]))
        self.assertEqual(self.limiter._uses, {})

    def test_the_group_scope_counts_everybody_and_a_refusal_there_does_not_spend_the_users_allowance(self):
        group = Scope("group", "group", ((60, 2), (3600, 0), (86400, 0)))
        self.assertIsNone(self.limiter.acquire([self.user("ana", minute=5), group]))
        self.assertIsNone(self.limiter.acquire([self.user("bob", minute=5), group]))
        refused = self.limiter.acquire([self.user("cris", minute=5), group])
        self.assertEqual(refused.scope, "group")
        self.assertNotIn("user:cris", self.limiter._uses)
        self.clock.now += 61
        self.assertIsNone(self.limiter.acquire([self.user("cris", minute=5), group]))

    def test_the_user_is_told_first_when_both_refuse(self):
        group = Scope("group", "group", ((60, 1), (3600, 0), (86400, 0)))
        self.limiter.acquire([self.user("ana", minute=1), group])
        self.assertEqual(self.limiter.acquire([self.user("ana", minute=1), group]).scope, "user")

    def test_the_memory_is_bounded_whatever_the_users(self):
        from src.utils import rate_limit

        for i in range(rate_limit.MAX_KEYS + 50):
            self.limiter.acquire([self.user(f"u{i}")])
        self.assertLessEqual(len(self.limiter._uses), rate_limit.MAX_KEYS)
