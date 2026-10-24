"""The details of a RAWG game (utils/my_utils.get_game_details_by_rawg_id): what each source gives and that the slow
ones are asked at the same time, not one after the other."""
import asyncio
import unittest
from types import SimpleNamespace
from unittest import mock

from src.database import models
from src.utils import my_utils
from tests.sqlite_db import make_session

GAME = {"name": "Celeste", "slug": "celeste", "released": "2018-01-25", "background_image": "https://img/c.jpg",
        "genres": [{"name": "Platformer"}], "developers": [], "publishers": [],
        "tags": [{"name": "Singleplayer", "language": "eng"}, {"name": "Одиночная", "language": "rus"}]}


class Sources:
    """RAWG and HowLongToBeat as fakes that note how many of them are being asked at once."""

    def __init__(self, stores=None, hltb=None, game_ok=True, parents=None):
        self.stores, self.hltb, self.game_ok = stores or [], hltb or [], game_ok
        self.parents = parents  # the games this one is an addition of (None: RAWG does not count any)
        self.asked = []
        self.in_flight = self.most_in_flight = 0

    async def _wait(self):
        self.in_flight += 1
        self.most_in_flight = max(self.most_in_flight, self.in_flight)
        await asyncio.sleep(0.01)
        self.in_flight -= 1

    async def http_get(self, url, params, timeout):
        await self._wait()
        self.asked.append(url.rsplit("/", 1)[-1])
        if url.endswith("/stores"):
            return SimpleNamespace(ok=True, json=lambda: {"results": self.stores})
        if url.endswith("/parent-games"):
            return SimpleNamespace(ok=True, json=lambda: {"results": self.parents or []})
        game = {**GAME, "parents_count": len(self.parents)} if self.parents else GAME
        return SimpleNamespace(ok=self.game_ok, status_code=200 if self.game_ok else 404, content=b"", json=lambda: game)

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

    async def test_a_dlc_carries_the_id_of_its_base_game(self):
        sources = Sources(parents=[{"id": 388309, "name": "Diablo IV"}])
        found = await self.details(sources)
        self.assertEqual((found["is_dlc"], found["parent_rawg_id"]), (True, 388309))
        self.assertIn("parent-games", sources.asked)

    async def test_a_game_of_its_own_does_not_ask_for_a_base_game(self):
        sources = Sources()
        found = await self.details(sources)
        self.assertEqual((found["is_dlc"], found["parent_rawg_id"]), (False, None))
        self.assertNotIn("parent-games", sources.asked)


class ParentCandidateTests(unittest.IsolatedAsyncioTestCase):
    """The notice of the "add game" step: the base game of a RAWG game, and whether the catalogue has it."""

    async def parent(self, sources, db):
        with mock.patch.object(type(my_utils.config), "RAWG_API_KEY", new_callable=mock.PropertyMock, return_value="k"), \
                mock.patch.object(my_utils, "_http_get", new=sources.http_get):
            return await my_utils.rawg_parent_candidate(1011642, db)

    async def test_a_game_of_its_own_has_no_base_game(self):
        self.assertIsNone(await self.parent(Sources(), make_session(threads=True)))

    async def test_the_base_game_is_flagged_when_it_is_in_the_catalogue(self):
        db = make_session(threads=True)
        sources = Sources(parents=[{"id": 388309, "name": "Diablo IV"}])
        missing = await self.parent(sources, db)
        self.assertEqual((missing.rawg_id, missing.name, missing.exists_in_db), (388309, "Diablo IV", False))
        db.add(models.Game(id="d4", name="Diablo IV", rawg_id=388309))
        db.commit()
        there = await self.parent(sources, db)
        self.assertEqual((there.exists_in_db, there.db_game_id), (True, "d4"))


if __name__ == "__main__":
    unittest.main()
