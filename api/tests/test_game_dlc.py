"""A DLC / expansion is marked in the catalogue, with or without its base game: one from RAWG brings its base game
along (added when missing, and only then), a game typed by hand can be marked and linked, a RAWG failure never loses
the DLC, and the RAWG sync fills the mark of the games it visits."""
import unittest
from unittest import mock

from fastapi import HTTPException

from src.crud import game_catalog, games
from src.database import models, schemas
from src.routers import games as games_router
from src.utils import my_utils, rawg_sync
from tests.sqlite_db import make_session

DLC = schemas.NewGame(name="Diablo IV: Vessel Of Hatred", rawg_id=1011642, is_dlc=True, parent_rawg_id=388309)
BASE = schemas.NewGame(name="Diablo IV", rawg_id=388309, slug="diablo-iv")


def fake_details(by_rawg_id):
    """get_new_game_info answering from `by_rawg_id`; an unknown id is "RAWG has nothing": the game as typed."""
    async def get_new_game_info(game):
        found = by_rawg_id.get(game["rawg_id"] if isinstance(game, dict) else game.rawg_id)
        return found.model_copy() if found else schemas.NewGame(name=game["name"] if isinstance(game, dict) else game.name)
    return mock.patch.object(my_utils, "get_new_game_info", side_effect=get_new_game_info)


class BaseGameIsAddedTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = make_session(threads=True)  # new_game works in the threadpool

    def names(self):
        return sorted(name for (name,) in self.db.query(models.Game.name))

    async def test_a_dlc_is_stored_linked_to_its_base_game_and_the_base_game_is_added(self):
        with fake_details({1011642: DLC, 388309: BASE}):
            stored = await games.new_game(self.db, DLC)
        base = self.db.query(models.Game).filter_by(rawg_id=388309).one()
        self.assertEqual((stored.is_dlc, stored.parent_game_id), (True, base.id))
        self.assertEqual(self.names(), ["Diablo IV", "Diablo IV: Vessel Of Hatred"])
        self.assertEqual((base.is_dlc, base.parent_game_id), (False, None))

    async def test_a_base_game_already_in_the_catalogue_is_linked_not_added_again(self):
        self.db.add(models.Game(id="d4", name="Diablo IV", rawg_id=388309))
        self.db.commit()
        with fake_details({1011642: DLC}) as details:
            stored = await games.new_game(self.db, DLC)
        self.assertEqual(stored.parent_game_id, "d4")
        self.assertEqual(self.names(), ["Diablo IV", "Diablo IV: Vessel Of Hatred"])
        self.assertEqual(details.call_count, 1)  # RAWG was not asked for the base game

    async def test_a_game_of_its_own_adds_nothing_else(self):
        with fake_details({388309: BASE}):
            stored = await games.new_game(self.db, BASE)
        self.assertEqual(self.names(), ["Diablo IV"])
        self.assertEqual((stored.is_dlc, stored.parent_game_id), (False, None))

    async def test_without_an_answer_from_rawg_the_dlc_stays_marked_and_no_nameless_game_is_created(self):
        with fake_details({1011642: DLC}):  # nothing for 388309
            stored = await games.new_game(self.db, DLC)
        self.assertEqual((stored.name, stored.is_dlc, stored.parent_game_id), ("Diablo IV: Vessel Of Hatred", True, None))
        self.assertEqual(self.names(), ["Diablo IV: Vessel Of Hatred"])

    async def test_a_failure_adding_the_base_game_does_not_lose_the_dlc(self):
        real = games._store_game

        def store_or_fail(db, game, info):
            if info.rawg_id == 388309:
                raise RuntimeError("database gone")
            return real(db, game, info)

        with fake_details({1011642: DLC, 388309: BASE}), mock.patch.object(games, "_store_game", side_effect=store_or_fail):
            stored = await games.new_game(self.db, DLC)
        self.assertEqual((stored.name, stored.is_dlc, stored.parent_game_id), ("Diablo IV: Vessel Of Hatred", True, None))
        self.assertEqual(self.names(), ["Diablo IV: Vessel Of Hatred"])


class GameTypedByHandTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = make_session(threads=True)
        self.db.add(models.Game(id="d4", name="Diablo IV"))
        self.db.commit()

    async def create(self, **fields):
        return await games_router.create_game(schemas.NewGame(name="Mi expansión", **fields), self.db)

    async def test_it_can_be_a_dlc_without_saying_of_which_game(self):
        made = await self.create(is_dlc=True)
        self.assertEqual((made.is_dlc, made.parent_game_id), (True, None))

    async def test_it_can_be_a_dlc_of_a_game_in_the_catalogue(self):
        made = await self.create(is_dlc=True, parent_game_id="d4")
        self.assertEqual((made.is_dlc, made.parent_game_id), (True, "d4"))
        self.assertEqual(games.parent_of(self.db, made).name, "Diablo IV")

    async def test_naming_a_base_game_makes_it_a_dlc(self):
        made = await self.create(parent_game_id="d4")
        self.assertTrue(made.is_dlc)

    async def test_it_is_not_a_dlc_unless_marked(self):
        made = await self.create()
        self.assertEqual((made.is_dlc, made.parent_game_id), (False, None))

    async def test_a_base_game_that_is_not_in_the_catalogue_is_refused(self):
        with self.assertRaises(HTTPException) as refused:
            await self.create(is_dlc=True, parent_game_id="nope")
        self.assertEqual(refused.exception.status_code, 400)
        self.assertEqual(self.db.query(models.Game).count(), 1)


class ReadingTheMarkTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        self.db.add_all([
            models.Game(id="d4", name="Diablo IV", rawg_id=388309),
            models.Game(id="voh", name="Vessel Of Hatred", is_dlc=True, parent_game_id="d4"),
            models.Game(id="orphan", name="Some DLC", is_dlc=True),
        ])
        self.db.commit()

    def test_the_base_game_is_found_only_when_the_dlc_has_one(self):
        get = lambda game_id: games.parent_of(self.db, self.db.get(models.Game, game_id))  # noqa: E731
        self.assertEqual(get("voh").id, "d4")
        self.assertIsNone(get("orphan"))
        self.assertIsNone(get("d4"))

    def test_the_catalogue_says_which_games_are_dlcs(self):
        rows = {row["id"]: row["is_dlc"] for row in game_catalog.catalog(self.db, viewer_id=1)["items"]}
        self.assertEqual(rows, {"d4": False, "voh": True, "orphan": True})


class SyncFillsTheMarkTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        self.db.add(models.Game(id="d4", name="Diablo IV", rawg_id=388309))
        self.db.commit()

    def client(self, game, parents):
        def get(path, **params):
            if path.endswith("/parent-games"):
                return {"results": parents}
            return {**game}
        client = mock.Mock(spec=rawg_sync._Client)
        client.get.side_effect = get
        client.budget_left.return_value = True
        return client

    def test_a_dlc_is_marked_and_linked_to_its_base_game_when_the_catalogue_has_it(self):
        client = self.client({"slug": "voh", "parents_count": 1}, [{"id": 388309, "name": "Diablo IV"}])
        det = rawg_sync._details(client, 1011642, need_steam=False)
        game = models.Game(id="voh", name="Vessel Of Hatred")
        self.assertEqual({"is_dlc", "parent_game_id"} - set(rawg_sync._apply(self.db, game, det, overwrite=False)), set())
        self.assertEqual((game.is_dlc, game.parent_game_id), (True, "d4"))

    def test_a_dlc_whose_base_game_is_missing_is_marked_and_the_sync_adds_no_game(self):
        client = self.client({"slug": "voh", "parents_count": 1}, [{"id": 999, "name": "Unknown"}])
        det = rawg_sync._details(client, 1011642, need_steam=False)
        game = models.Game(id="voh", name="Vessel Of Hatred")
        rawg_sync._apply(self.db, game, det, overwrite=False)
        self.assertEqual((game.is_dlc, game.parent_game_id), (True, None))
        self.assertEqual(self.db.query(models.Game).count(), 1)

    def test_a_game_of_its_own_costs_no_extra_request_and_keeps_what_it_had(self):
        client = self.client({"slug": "d4", "parents_count": 0}, [])
        det = rawg_sync._details(client, 388309, need_steam=False)
        self.assertEqual([call.args[0] for call in client.get.call_args_list], ["/games/388309"])
        game = models.Game(id="x", name="Marked by hand", is_dlc=True, parent_game_id="d4")
        rawg_sync._apply(self.db, game, det, overwrite=True)
        self.assertEqual((game.is_dlc, game.parent_game_id), (True, "d4"))  # RAWG saying nothing never unmarks ours

    def test_a_link_chosen_by_hand_is_kept_unless_the_sync_overwrites(self):
        self.db.add(models.Game(id="other", name="Other", rawg_id=5))
        self.db.commit()
        game = models.Game(id="voh", name="Vessel", is_dlc=True, parent_game_id="other")
        det = {"rawg_id": 1, "is_dlc": True, "parent_rawg_id": 388309}
        rawg_sync._apply(self.db, game, det, overwrite=False)
        self.assertEqual(game.parent_game_id, "other")
        rawg_sync._apply(self.db, game, det, overwrite=True)
        self.assertEqual(game.parent_game_id, "d4")


if __name__ == "__main__":
    unittest.main()
