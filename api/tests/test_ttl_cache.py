import unittest
from unittest import mock

from src.utils import ttl_cache
from src.utils.ttl_cache import TtlCache


class TtlCacheTests(unittest.TestCase):
    def setUp(self):
        self.now = [100.0]
        patcher = mock.patch.object(ttl_cache.time, "monotonic", side_effect=lambda: self.now[0])
        patcher.start()
        self.addCleanup(patcher.stop)
        self.cache = TtlCache(60)
        self.calls = 0

    def compute(self):
        self.calls += 1
        return self.calls

    def test_an_answer_is_reused_while_fresh_and_recomputed_after(self):
        self.assertEqual([self.cache.get("a", self.compute), self.cache.get("a", self.compute)], [1, 1])
        self.now[0] += 59
        self.assertEqual(self.cache.get("a", self.compute), 1)
        self.now[0] += 2
        self.assertEqual(self.cache.get("a", self.compute), 2)

    def test_each_key_has_its_own_answer(self):
        self.assertEqual((self.cache.get("a", self.compute), self.cache.get("b", self.compute)), (1, 2))

    def test_clear_and_clear_all_forget_everything(self):
        self.cache.get("a", self.compute)
        self.cache.clear()
        self.assertEqual(self.cache.get("a", self.compute), 2)
        ttl_cache.clear_all()
        self.assertEqual(self.cache.get("a", self.compute), 3)

    def test_a_failure_is_not_remembered(self):
        with self.assertRaises(RuntimeError):
            self.cache.get("a", mock.Mock(side_effect=RuntimeError))
        self.assertEqual(self.cache.get("a", self.compute), 1)


if __name__ == "__main__":
    unittest.main()
