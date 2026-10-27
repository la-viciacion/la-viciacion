"""The outside data of a game through real requests (MariaDB required, see api_support.py); Steam and RAWG are replaced by a recorder."""
from unittest import mock

from src.utils import game_extras
from tests.api_support import ApiTestCase


class GameExtrasTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.ana = self.user("ana")
        self.game("hades", "Hades", rawg_id=100, steam_id="1145360")
        self.game("alone", "Alone")  # no RAWG nor Steam id
        self.extras = mock.AsyncMock(return_value={"description": "Un juego", "trailer": None, "screenshots": [], "metacritic": 93, "esrb": None})
        patcher = mock.patch.object(game_extras, "extras_of", self.extras)
        patcher.start()
        self.addCleanup(patcher.stop)

    def get(self, game="hades"):
        return self.api("GET", f"/games/{game}/extras", as_user="ana")

    def test_it_needs_a_login_and_an_unknown_game_is_a_404(self):
        self.assertEqual(self.api("GET", "/games/hades/extras").status_code, 401)
        self.assertEqual(self.get("nope").status_code, 404)

    def test_it_asks_with_the_ids_of_the_game_and_adds_available(self):
        body = self.get().json()
        self.extras.assert_awaited_once_with(100, "1145360")
        self.assertEqual((body["available"], body["description"], body["metacritic"]), (True, "Un juego", 93))

    def test_when_nobody_can_be_asked_the_page_has_no_card(self):
        self.extras.return_value = None
        self.assertEqual(self.get("alone").json(), {"available": False})
