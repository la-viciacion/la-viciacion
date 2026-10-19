import types
import unittest
from unittest import mock

from src.crud import games, users


class GenreListTests(unittest.TestCase):
    def test_the_stored_string_is_split_into_genres(self):
        self.assertEqual(games.genre_list("Action, RPG,Indie"), ["Action", "RPG", "Indie"])

    def test_lists_are_cleaned_too(self):
        self.assertEqual(games.genre_list([" Action", "", "RPG "]), ["Action", "RPG"])

    def test_nothing_gives_no_genres(self):
        for value in (None, "", " , "):
            self.assertEqual(games.genre_list(value), [], repr(value))


class AfterCompletionAvgTimeTests(unittest.IsolatedAsyncioTestCase):
    async def run_completion(self, hltb, stored_avg):
        game = types.SimpleNamespace(id="g", name="Doom", genres=None, avg_time=stored_avg)
        entry = types.SimpleNamespace(game_id="g", user_id=1, season=2026)
        update = mock.MagicMock()
        ach = mock.MagicMock(
            just_in_time=mock.AsyncMock(), user_completed_total_games=mock.AsyncMock(), completed_in_a_day=mock.AsyncMock(),
            lifetime_views=mock.MagicMock(return_value=[]),
        )
        with mock.patch.object(users.games, "get_game_by_id", return_value=game), \
                mock.patch.object(users, "get_user_by_id", return_value=types.SimpleNamespace(id=1, name="Ana")), \
                mock.patch.object(users.utils, "get_game_info", new=mock.AsyncMock(return_value={"rawg": None, "hltb": hltb})), \
                mock.patch.object(users.games, "update_avg_time_game", update), \
                mock.patch.object(users.games, "completion_suggestion", return_value=None), \
                mock.patch.object(users.settings, "get", return_value=True), \
                mock.patch.object(users, "count_completed_games", return_value=1), \
                mock.patch.object(users.utils, "send_message", new=mock.AsyncMock()), \
                mock.patch("src.crud.time_entries.played_time_of_run", return_value=0), \
                mock.patch("src.crud.achievements.Achievements", return_value=ach):
            await users.after_completion(mock.MagicMock(), entry, silent=True)
        return update, ach

    async def test_a_failed_lookup_keeps_the_stored_time(self):
        update, ach = await self.run_completion(hltb=None, stored_avg=36000)
        update.assert_not_called()
        self.assertEqual(ach.just_in_time.await_args.args[3], 36000)  # avg_time

    async def test_a_fresh_value_replaces_the_stored_one(self):
        update, _ = await self.run_completion(hltb={"comp_main": 40000}, stored_avg=36000)
        update.assert_called_once_with(mock.ANY, "g", 40000)

    async def test_an_unchanged_value_is_not_written(self):
        update, _ = await self.run_completion(hltb={"comp_main": 36000}, stored_avg=36000)
        update.assert_not_called()


class CompletionRecommendationSwitchTests(unittest.IsolatedAsyncioTestCase):
    async def completion(self, recommend):
        game = types.SimpleNamespace(id="g", name="Doom", genres="RPG", avg_time=3600)
        entry = types.SimpleNamespace(game_id="g", user_id=1, season=2026)
        ach = mock.MagicMock(
            just_in_time=mock.AsyncMock(), user_completed_total_games=mock.AsyncMock(), completed_in_a_day=mock.AsyncMock(),
            lifetime_views=mock.MagicMock(return_value=[]),
        )
        suggest = mock.MagicMock(return_value={"game": "Hades", "reasons": ["Lo tiene 1 jugador del grupo"]})
        send = mock.AsyncMock()
        with mock.patch.object(users.games, "get_game_by_id", return_value=game), \
                mock.patch.object(users, "get_user_by_id", return_value=types.SimpleNamespace(id=1, name="Ana")), \
                mock.patch.object(users.utils, "get_game_info", new=mock.AsyncMock(return_value={"rawg": None, "hltb": None})), \
                mock.patch.object(users.games, "completion_suggestion", suggest), \
                mock.patch.object(users, "count_completed_games", return_value=1), \
                mock.patch.object(users.utils, "send_message", new=send), \
                mock.patch.object(users.settings, "get", side_effect=lambda key: {"completed_game.recommend": recommend}[key]), \
                mock.patch("src.crud.time_entries.played_time_of_run", return_value=0), \
                mock.patch("src.crud.achievements.Achievements", return_value=ach):
            await users.after_completion(mock.MagicMock(), entry, silent=True)
        return suggest, send

    async def test_on_by_default_the_notice_carries_a_suggestion(self):
        self.assertIs(users.settings.REGISTRY["completed_game.recommend"].default, True)
        suggest, send = await self.completion(True)
        suggest.assert_called_once()
        self.assertEqual(send.await_args.kwargs["new_game_recommended"], {"game": "Hades", "reasons": ["Lo tiene 1 jugador del grupo"]})

    async def test_switched_off_no_game_is_looked_up_and_none_is_suggested(self):
        suggest, send = await self.completion(False)
        suggest.assert_not_called()
        self.assertIsNone(send.await_args.kwargs["new_game_recommended"])


if __name__ == "__main__":
    unittest.main()
