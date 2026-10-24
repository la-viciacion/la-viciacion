"""A DLC / expansion is marked in the catalogue and brings its base game along: the base game is added when it is
missing (and only then), a RAWG failure never loses the DLC, and the RAWG sync fills the mark of the games it visits."""
import unittest
from unittest import mock

from src.crud import game_catalog, games
from src.database import models, schemas
from src.utils import my_utils, rawg_sync
from tests.sqlite_db import make_session

DLC = schemas.NewGame(name="Diablo IV: Vessel Of Hatred", rawg_id=1011642, parent_rawg_id=388309)
BASE = schemas.NewGame(name="Diablo IV", rawg_id=388309, slug="diablo-iv")


def fake_details(by_rawg_id):
    """get_new_game_info answering from `by_rawg_id`; an unknown id is "RAWG has nothing": the game as typed."""
    async def get_new_game_info(game):
        found = by_rawg_id.get(game["rawg_id"] if isinstance(game, dict) else game.rawg_id)
        return found or schemas.NewGame(name=game["name"] if isinstance(game, dict) else game.name)
    return mock.patch.object(my_utils, "get_new_game_info", side_effect=get_new_game_info)


class BaseGameIsAddedTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = make_session(threads=True)  # new_game works in the threadpool

    def names(self):
        return sorted(name for (name,) in self.db.query(models.Game.name))

    async def test_a_dlc_is_stored_with_its_base_game_id_and_the_base_game_is_added(self):
        with fake_details({1011642: DLC, 388309: BASE}):
            stored = await games.new_game(self.db, DLC)
        self.assertEqual(stored.parent_rawg_id, 388309)
        self.assertEqual(self.names(), ["Diablo IV", "Diablo IV: Vessel Of Hatred"])
        self.assertIsNone(self.db.query(models.Game).filter_by(rawg_id=388309).one().parent_rawg_id)

    async def test_a_base_game_already_in_the_catalogue_is_not_added_again(self):
        self.db.add(models.Game(id="d4", name="Diablo IV", rawg_id=388309))
        self.db.commit()
        with fake_details({1011642: DLC}) as details:
            await games.new_game(self.db, DLC)
        self.assertEqual(self.names(), ["Diablo IV", "Diablo IV: Vessel Of Hatred"])
        self.assertEqual(details.call_count, 1)  # RAWG was not asked for the base game

    async def test_a_game_of_its_own_adds_nothing_else(self):
        with fake_details({388309: BASE}):
            await games.new_game(self.db, BASE)
        self.assertEqual(self.names(), ["Diablo IV"])

    async def test_without_an_answer_from_rawg_the_dlc_stays_and_no_nameless_game_is_created(self):
        with fake_details({1011642: DLC}):  # nothing for 388309
            stored = await games.new_game(self.db, DLC)
        self.assertEqual((stored.name, stored.parent_rawg_id), ("Diablo IV: Vessel Of Hatred", 388309))
        self.assertEqual(self.names(), ["Diablo IV: Vessel Of Hatred"])

    async def test_a_failure_adding_the_base_game_does_not_lose_the_dlc(self):
        real = games._store_game

        def store_or_fail(db, game, info):
            if info.rawg_id == 388309:
                raise RuntimeError("database gone")
            return real(db, game, info)

        with fake_details({1011642: DLC, 388309: BASE}), mock.patch.object(games, "_store_game", side_effect=store_or_fail):
            stored = await games.new_game(self.db, DLC)
        self.assertEqual(stored.name, "Diablo IV: Vessel Of Hatred")
        self.assertEqual(self.names(), ["Diablo IV: Vessel Of Hatred"])


class ReadingTheMarkTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        self.db.add_all([
            models.Game(id="d4", name="Diablo IV", rawg_id=388309),
            models.Game(id="voh", name="Vessel Of Hatred", rawg_id=1011642, parent_rawg_id=388309),
            models.Game(id="orphan", name="Some DLC", rawg_id=5, parent_rawg_id=999),
        ])
        self.db.commit()

    def test_the_base_game_is_found_only_when_it_is_in_the_catalogue(self):
        get = lambda game_id: games.parent_of(self.db, self.db.get(models.Game, game_id))  # noqa: E731
        self.assertEqual(get("voh").id, "d4")
        self.assertIsNone(get("orphan"))
        self.assertIsNone(get("d4"))

    def test_the_catalogue_says_which_games_are_dlcs(self):
        rows = {row["id"]: row["is_dlc"] for row in game_catalog.catalog(self.db, viewer_id=1)["items"]}
        self.assertEqual(rows, {"d4": False, "voh": True, "orphan": True})


class SyncFillsTheMarkTests(unittest.TestCase):
    def client(self, game, parents):
        def get(path, **params):
            if path.endswith("/parent-games"):
                return {"results": parents}
            return {**game}
        client = mock.Mock(spec=rawg_sync._Client)
        client.get.side_effect = get
        client.budget_left.return_value = True
        return client

    def test_a_dlc_gets_the_id_of_its_base_game(self):
        client = self.client({"slug": "voh", "parents_count": 1}, [{"id": 388309, "name": "Diablo IV"}])
        det = rawg_sync._details(client, 1011642, need_steam=False)
        game = models.Game(id="voh", name="Vessel Of Hatred")
        self.assertIn("parent_rawg_id", rawg_sync._apply(game, det, overwrite=False))
        self.assertEqual(game.parent_rawg_id, 388309)

    def test_a_game_of_its_own_costs_no_extra_request_and_keeps_what_it_had(self):
        client = self.client({"slug": "d4", "parents_count": 0}, [])
        det = rawg_sync._details(client, 388309, need_steam=False)
        self.assertEqual([call.args[0] for call in client.get.call_args_list], ["/games/388309"])
        game = models.Game(id="d4", name="Diablo IV", parent_rawg_id=7)
        rawg_sync._apply(game, det, overwrite=True)
        self.assertEqual(game.parent_rawg_id, 7)  # RAWG saying nothing never blanks ours


if __name__ == "__main__":
    unittest.main()
