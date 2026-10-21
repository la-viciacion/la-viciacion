"""The update processor: different users at the same time, one user's updates in order."""
import asyncio
import unittest

from tests import support  # noqa: F401  (sets the environment and the path before the bot is imported)

from telegram import Update

from utils.updates import PerUserUpdateProcessor


def update_of(user_id: int) -> Update:
    return Update.de_json({"update_id": 1, "message": {
        "message_id": 1, "date": 0, "text": "hi", "chat": {"id": user_id, "type": "private"},
        "from": {"id": user_id, "is_bot": False, "first_name": "U"},
    }}, None)


class PerUserUpdateProcessorTests(unittest.IsolatedAsyncioTestCase):
    async def test_updates_of_different_users_run_at_the_same_time(self):
        processor = PerUserUpdateProcessor()
        started = {1: asyncio.Event(), 2: asyncio.Event()}

        async def work(me, other):
            started[me].set()
            await asyncio.wait_for(started[other].wait(), 2)  # times out if the other user is waited for

        await asyncio.gather(processor.process_update(update_of(1), work(1, 2)), processor.process_update(update_of(2), work(2, 1)))

    async def test_updates_of_one_user_run_one_by_one_in_the_order_they_came(self):
        processor = PerUserUpdateProcessor()
        log = []

        async def work(name, pause):
            log.append(("start", name))
            await asyncio.sleep(pause)
            log.append(("end", name))

        await asyncio.gather(
            processor.process_update(update_of(1), work("first", 0.05)),
            processor.process_update(update_of(1), work("second", 0)),
            processor.process_update(update_of(1), work("third", 0)),
        )
        self.assertEqual(log, [("start", "first"), ("end", "first"), ("start", "second"), ("end", "second"), ("start", "third"), ("end", "third")])

    async def test_a_slow_user_does_not_hold_back_the_others(self):
        processor = PerUserUpdateProcessor()
        release = asyncio.Event()
        done = []

        async def slow():
            await release.wait()

        async def quick():
            done.append("quick")

        slow_one = asyncio.create_task(processor.process_update(update_of(1), slow()))
        await asyncio.sleep(0)
        await asyncio.wait_for(processor.process_update(update_of(2), quick()), 2)
        self.assertEqual(done, ["quick"])
        release.set()
        await slow_one

    async def test_something_that_is_not_a_user_update_just_runs(self):
        done = []

        async def work():
            done.append(1)

        await PerUserUpdateProcessor().process_update(object(), work())
        await PerUserUpdateProcessor().process_update("a job", work())
        self.assertEqual(done, [1, 1])

    async def test_nothing_is_kept_for_users_who_are_done_not_even_after_a_failure(self):
        processor = PerUserUpdateProcessor()

        async def fails():
            raise RuntimeError("boom")

        async def works():
            pass

        await processor.process_update(update_of(1), works())
        with self.assertRaises(RuntimeError):
            await processor.process_update(update_of(2), fails())
        self.assertEqual(processor._locks, {})
        await processor.process_update(update_of(2), works())  # the failed user is not stuck

    async def test_no_more_than_the_cap_run_at_once(self):
        processor = PerUserUpdateProcessor(max_concurrent_updates=2)
        running = peak = 0

        async def work():
            nonlocal running, peak
            running += 1
            peak = max(peak, running)
            await asyncio.sleep(0.01)
            running -= 1

        await asyncio.gather(*(processor.process_update(update_of(user), work()) for user in range(1, 6)))
        self.assertEqual(peak, 2)


if __name__ == "__main__":
    unittest.main()
