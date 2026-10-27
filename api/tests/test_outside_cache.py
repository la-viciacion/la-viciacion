"""The memory kept of what the outside world answers: how long it lasts, what a failure costs and what a burst of requests does."""
import asyncio
import unittest
from unittest import mock

from src.utils import outside_cache
from src.utils.outside_cache import OutsideCache, Partial


class OutsideCacheTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.cache = OutsideCache(seconds=100, failure_seconds=10, max_items=3)
        self.clock = [1000.0]
        patcher = mock.patch.object(outside_cache.time, "time", side_effect=lambda: self.clock[0])
        patcher.start()
        self.addCleanup(patcher.stop)
        self.asked = []

    def fetch(self, answer):
        async def fetch():
            self.asked.append(answer)
            return answer
        return fetch

    async def test_an_answer_is_kept_for_its_time_and_asked_again_after_it(self):
        self.assertEqual(await self.cache.get("a", self.fetch("one")), "one")
        self.assertEqual(await self.cache.get("a", self.fetch("two")), "one")  # from memory
        self.clock[0] += 99
        self.assertEqual(await self.cache.get("a", self.fetch("two")), "one")
        self.clock[0] += 2
        self.assertEqual(await self.cache.get("a", self.fetch("two")), "two")
        self.assertEqual(self.asked, ["one", "two"])

    async def test_an_empty_answer_is_an_answer_and_is_kept_like_any(self):
        self.assertEqual(await self.cache.get("a", self.fetch([])), [])
        await self.cache.get("a", self.fetch([]))
        self.assertEqual(len(self.asked), 1)

    async def test_a_failure_is_none_and_remembered_for_the_short_time_only(self):
        self.assertIsNone(await self.cache.get("a", self.fetch(None)))
        self.assertIsNone(await self.cache.get("a", self.fetch("back")))
        self.assertEqual(len(self.asked), 1)
        self.clock[0] += 11
        self.assertEqual(await self.cache.get("a", self.fetch("back")), "back")

    async def test_a_partial_answer_is_used_but_remembered_only_for_the_short_time(self):
        self.assertEqual(await self.cache.get("a", self.fetch(Partial("half"))), "half")
        self.assertEqual(await self.cache.get("a", self.fetch("whole")), "half")  # from memory
        self.clock[0] += 11
        self.assertEqual(await self.cache.get("a", self.fetch("whole")), "whole")  # not a day later: soon
        self.assertEqual(len(self.asked), 2)

    async def test_the_memory_is_bounded_and_the_oldest_answer_goes_first(self):
        for key in (1, 2, 3):
            await self.cache.get(key, self.fetch(key))
            self.clock[0] += 1
        await self.cache.get(4, self.fetch(4))
        self.assertEqual(sorted(self.cache._items), [2, 3, 4])
        await self.cache.get(4, self.fetch(4))  # a key already there never pushes another one out
        self.assertEqual(sorted(self.cache._items), [2, 3, 4])

    async def test_simultaneous_requests_for_a_key_ask_once(self):
        async def slow():
            self.asked.append("slow")
            await asyncio.sleep(0)
            return "done"
        answers = await asyncio.gather(*(self.cache.get("a", slow) for _ in range(4)))
        self.assertEqual(answers, ["done"] * 4)
        self.assertEqual(self.asked, ["slow"])
        self.assertEqual(self.cache._asking, {})

    async def test_a_caller_that_goes_away_does_not_cancel_the_others(self):
        gate = asyncio.Event()

        async def slow():
            await gate.wait()
            return "done"
        first = asyncio.create_task(self.cache.get("a", slow))
        second = asyncio.create_task(self.cache.get("a", slow))
        await asyncio.sleep(0)
        first.cancel()
        gate.set()
        self.assertEqual(await second, "done")

    async def test_clear_forgets_everything(self):
        await self.cache.get("a", self.fetch("one"))
        self.cache.clear()
        await self.cache.get("a", self.fetch("two"))
        self.assertEqual(self.asked, ["one", "two"])


if __name__ == "__main__":
    unittest.main()
