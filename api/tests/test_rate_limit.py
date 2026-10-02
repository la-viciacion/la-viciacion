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
