"""The saga of a game: what is read from RAWG's series, how long it is kept and how the rows are ordered (no database)."""
import asyncio
import unittest
from unittest import mock

from src.crud import game_series
from src.utils import rawg_series


def entry(rawg_id, name, released, **over):
    return {"rawg_id": rawg_id, "name": name, "slug": None, "image_url": None, "released": released, "game_id": None, "current": False, "next": False, "mine": None, "players": 0, **over}


class ParseTests(unittest.TestCase):
    def test_it_keeps_the_fields_the_app_uses_and_survives_nulls(self):
        series = rawg_series.parse([
            {"id": 1, "name": "Hades", "slug": "hades", "background_image": "http://img", "released": "2020-09-17", "extra": True},
            {"id": 2, "name": "Hades II", "slug": None, "background_image": None, "released": None},
            {"id": None, "name": "No id"}, {"id": 3, "name": ""}, {"id": 4},
        ])
        self.assertEqual(series, [
            {"rawg_id": 1, "name": "Hades", "slug": "hades", "image_url": "http://img", "released": "2020-09-17"},
            {"rawg_id": 2, "name": "Hades II", "slug": None, "image_url": None, "released": None},
        ])
        self.assertEqual(rawg_series.parse(None), [])


class OrderTests(unittest.TestCase):
    def test_by_release_the_undated_last_and_then_by_name(self):
        rows = [entry(1, "C", None), entry(2, "B", "2019-01-01"), entry(3, "A", "2018-05-05"), entry(4, "a", None)]
        self.assertEqual([r["rawg_id"] for r in game_series.order(rows)], [3, 2, 4, 1])

    def test_the_next_is_the_first_released_after_the_current_one_that_was_not_completed(self):
        rows = game_series.mark_next(game_series.order([
            entry(1, "I", "2010-01-01", mine={"has": True, "completed": True, "seconds": 1}),
            entry(2, "II", "2012-01-01", current=True),
            entry(3, "III", "2014-01-01", mine={"has": True, "completed": True, "seconds": 5}),
            entry(4, "IV", "2016-01-01"),
        ]))
        self.assertEqual([r["name"] for r in rows if r["next"]], ["IV"])  # III is done: the next one to play is IV

    def test_nothing_is_next_at_the_end_of_the_saga_or_without_a_date(self):
        last = game_series.mark_next(game_series.order([entry(1, "I", "2010-01-01"), entry(2, "II", "2012-01-01", current=True)]))
        self.assertFalse(any(r["next"] for r in last))
        undated = game_series.mark_next(game_series.order([entry(1, "I", "2010-01-01"), entry(2, "II", None, current=True), entry(3, "III", "2014-01-01")]))
        self.assertFalse(any(r["next"] for r in undated))


class CacheTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        rawg_series.clear()
        self.addCleanup(rawg_series.clear)
        self.key = mock.patch.object(type(rawg_series.config), "RAWG_API_KEY", new_callable=mock.PropertyMock, return_value="k")
        self.key.start()
        self.addCleanup(self.key.stop)
        self.clock = [1000.0]
        patcher = mock.patch.object(rawg_series.time, "time", side_effect=lambda: self.clock[0])
        patcher.start()
        self.addCleanup(patcher.stop)
        self.calls = []

    def answer(self, ok=True, results=None, error=None):
        async def get(url, params, timeout):
            self.calls.append((url, params))
            if error:
                raise error
            return mock.Mock(ok=ok, status_code=200 if ok else 500, content=b"", json=lambda: {"results": results or []})

        patcher = mock.patch.object(rawg_series.my_utils, "_http_get", new=get)
        patcher.start()
        self.addCleanup(patcher.stop)

    async def test_it_asks_once_a_day_and_the_key_goes_in_the_request(self):
        self.answer(results=[{"id": 5, "name": "Hades II", "released": "2025-05-06"}])
        first = await rawg_series.series_of(7)
        self.assertEqual([s["name"] for s in first], ["Hades II"])
        self.assertEqual(self.calls[0][0], "https://api.rawg.io/api/games/7/game-series")
        self.assertEqual(self.calls[0][1]["key"], "k")
        await rawg_series.series_of(7)
        self.assertEqual(len(self.calls), 1)  # from memory
        self.clock[0] += rawg_series.CACHE_SECONDS - 1
        await rawg_series.series_of(7)
        self.assertEqual(len(self.calls), 1)
        self.clock[0] += 2
        await rawg_series.series_of(7)
        self.assertEqual(len(self.calls), 2)  # a day later it asks again

    async def test_a_game_without_series_is_an_empty_list_that_is_also_kept(self):
        self.answer(results=[])
        self.assertEqual(await rawg_series.series_of(7), [])
        await rawg_series.series_of(7)
        self.assertEqual(len(self.calls), 1)

    async def test_a_failure_is_none_and_is_remembered_for_a_few_minutes_only(self):
        self.answer(ok=False)
        self.assertIsNone(await rawg_series.series_of(7))
        self.assertIsNone(await rawg_series.series_of(7))
        self.assertEqual(len(self.calls), 1)
        self.clock[0] += rawg_series.FAILURE_SECONDS + 1
        await rawg_series.series_of(7)
        self.assertEqual(len(self.calls), 2)

    async def test_a_network_error_is_none_and_never_raises(self):
        self.answer(error=RuntimeError("down"))
        self.assertIsNone(await rawg_series.series_of(7))

    async def test_without_a_key_nothing_is_asked(self):
        self.key.stop()
        self.answer()
        with mock.patch.object(type(rawg_series.config), "RAWG_API_KEY", new_callable=mock.PropertyMock, return_value=""):
            self.assertIsNone(await rawg_series.series_of(7))
        self.assertEqual(self.calls, [])
        self.key.start()

    async def test_the_memory_is_bounded_and_the_oldest_answer_goes_first(self):
        self.answer(results=[])
        with mock.patch.object(rawg_series, "MAX_CACHED", 3):
            for rawg_id in (1, 2, 3):
                await rawg_series.series_of(rawg_id)
                self.clock[0] += 1
            await rawg_series.series_of(4)
        self.assertEqual(sorted(rawg_series._cache), [2, 3, 4])

    async def test_simultaneous_requests_for_the_same_game_ask_rawg_once(self):
        async def slow(url, params, timeout):
            self.calls.append(url)
            await asyncio.sleep(0)
            return mock.Mock(ok=True, status_code=200, content=b"", json=lambda: {"results": [{"id": 9, "name": "Nine"}]})
        with mock.patch.object(rawg_series.my_utils, "_http_get", side_effect=slow):
            answers = await asyncio.gather(*(rawg_series.series_of(7) for _ in range(4)))
        self.assertEqual(len(self.calls), 1)
        self.assertTrue(all(a == answers[0] and a[0]["rawg_id"] == 9 for a in answers))
        self.assertEqual(rawg_series._asking, {})

    async def test_a_caller_that_goes_away_does_not_cancel_the_others(self):
        gate = asyncio.Event()

        async def slow(url, params, timeout):
            await gate.wait()
            return mock.Mock(ok=True, status_code=200, content=b"", json=lambda: {"results": []})
        with mock.patch.object(rawg_series.my_utils, "_http_get", side_effect=slow):
            first = asyncio.create_task(rawg_series.series_of(7))
            second = asyncio.create_task(rawg_series.series_of(7))
            await asyncio.sleep(0)
            first.cancel()
            gate.set()
            self.assertEqual(await second, [])


if __name__ == "__main__":
    unittest.main()
