"""The details of a RAWG game (utils/my_utils.get_game_details_by_rawg_id): what each source gives and that the slow
ones are asked at the same time, not one after the other."""
import asyncio
import unittest
from types import SimpleNamespace
from unittest import mock

from src.utils import my_utils

GAME = {"name": "Celeste", "slug": "celeste", "released": "2018-01-25", "background_image": "https://img/c.jpg",
        "genres": [{"name": "Platformer"}], "developers": [], "publishers": [],
        "tags": [{"name": "Singleplayer", "language": "eng"}, {"name": "Одиночная", "language": "rus"}]}


class Sources:
    """RAWG and HowLongToBeat as fakes that note how many of them are being asked at once."""

    def __init__(self, stores=None, hltb=None, game_ok=True):
        self.stores, self.hltb, self.game_ok = stores or [], hltb or [], game_ok
        self.in_flight = self.most_in_flight = 0

    async def _wait(self):
        self.in_flight += 1
        self.most_in_flight = max(self.most_in_flight, self.in_flight)
        await asyncio.sleep(0.01)
        self.in_flight -= 1

    async def http_get(self, url, params, timeout):
        await self._wait()
        if url.endswith("/stores"):
            return SimpleNamespace(ok=True, json=lambda: {"results": self.stores})
        return SimpleNamespace(ok=self.game_ok, status_code=200 if self.game_ok else 404, content=b"", json=lambda: GAME)

    def hltb_class(self):
        sources = self

        class Fake:
            async def async_search(self, name):
                await sources._wait()
                return list(sources.hltb)

        return Fake


def hit(seconds=3600, dev="HLTB Studio", steam=None):
    return SimpleNamespace(similarity=0.9, game_id=1, game_name="Celeste", game_alias=None, game_type="game", release_world=2018,
                           profile_dev=dev, profile_steam=steam, json_content={"comp_main": seconds})


class GameDetailsTests(unittest.IsolatedAsyncioTestCase):
    async def details(self, sources):
        with mock.patch.object(type(my_utils.config), "RAWG_API_KEY", new_callable=mock.PropertyMock, return_value="k"), \
                mock.patch.object(my_utils, "_http_get", new=sources.http_get), \
                mock.patch.object(my_utils, "HowLongToBeat", new=sources.hltb_class()):
            return await my_utils.get_game_details_by_rawg_id(101)

    async def test_the_stores_and_howlongtobeat_are_asked_at_the_same_time(self):
        sources = Sources()
        await self.details(sources)
        self.assertGreaterEqual(sources.most_in_flight, 2)

    async def test_rawg_gives_the_game_and_its_steam_id_and_howlongtobeat_the_time(self):
        sources = Sources(stores=[{"url": "https://store.steampowered.com/app/504230/Celeste/"}], hltb=[hit(seconds=29000)])
        found = await self.details(sources)
        self.assertEqual((found["name"], found["steam_id"], found["avg_time"]), ("Celeste", "504230", 29000))
        self.assertEqual((found["genres"], found["tags"]), ("Platformer", "Singleplayer"))
        self.assertEqual(str(found["release_date"]), "2018-01-25")

    async def test_howlongtobeat_fills_the_developer_and_the_steam_id_rawg_lacks(self):
        found = await self.details(Sources(hltb=[hit(dev="Maddy Makes Games", steam=504230)]))
        self.assertEqual((found["dev"], found["steam_id"]), ("Maddy Makes Games", "504230"))

    async def test_without_any_source_the_developer_is_a_dash_and_the_time_zero(self):
        found = await self.details(Sources())
        self.assertEqual((found["dev"], found["steam_id"], found["avg_time"]), ("-", "", 0))

    async def test_a_game_rawg_does_not_have_gives_nothing(self):
        self.assertIsNone(await self.details(Sources(game_ok=False)))


if __name__ == "__main__":
    unittest.main()
