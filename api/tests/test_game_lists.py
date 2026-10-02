import unittest
from unittest import mock

from sqlalchemy.dialects import mysql

from src.crud import rankings, users


def rows(*game_ids):
    return [{"game_id": g, "platform_id": f"p{i}"} for i, g in enumerate(game_ids)]


class FirstEntryPerGameTests(unittest.TestCase):
    def test_a_game_on_two_platforms_counts_once_keeping_the_first(self):
        result = users.first_entry_per_game(rows("a", "a", "b"))
        self.assertEqual([r["game_id"] for r in result], ["a", "b"])
        self.assertEqual(result[0]["platform_id"], "p0")

    def test_the_limit_counts_games_not_rows(self):
        result = users.first_entry_per_game(rows("a", "a", "a", "b", "c"), limit=2)
        self.assertEqual([r["game_id"] for r in result], ["a", "b"])

    def test_no_limit_returns_everything(self):
        self.assertEqual(len(users.first_entry_per_game(rows("a", "b", "c"))), 3)


def statement_of(call):
    db = mock.MagicMock()
    db.execute.return_value.mappings.return_value.all.return_value = []
    call(db)
    return str(db.execute.call_args.args[0].compile(dialect=mysql.dialect()))


class StatementTests(unittest.TestCase):
    def test_the_library_query_filters_and_defers_the_limit(self):
        sql = statement_of(lambda db: users.get_games(db, 1, limit=5, completed=True, season=2026))
        self.assertIn("coalesce(users_games.completed", sql)
        self.assertNotIn("LIMIT", sql)  # limited after deduplicating, in Python

    def test_games_last_played_groups_and_limits_in_sql(self):
        sql = statement_of(lambda db: rankings.games_last_played(db, 10))
        self.assertIn("GROUP BY", sql)
        self.assertIn("LIMIT", sql)
        self.assertIn("max(", sql)


if __name__ == "__main__":
    unittest.main()
