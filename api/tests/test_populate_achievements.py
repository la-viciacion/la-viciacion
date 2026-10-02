import unittest
from unittest import mock

from src.crud.achievements import Achievements
from src.database import models
from src.utils.achievements import AchievementsElems


def db_with(existing_keys):
    db = mock.MagicMock()
    db.query.return_value.all.return_value = [(k,) for k in existing_keys]
    return db


class PopulateAchievementsTests(unittest.TestCase):
    def test_an_empty_table_gets_every_achievement(self):
        db = db_with([])
        Achievements().populate_achievements(db)
        added = [c.args[0] for c in db.add.call_args_list]
        self.assertEqual({a.key for a in added}, {e.name for e in AchievementsElems})
        db.commit.assert_called_once()

    def test_only_the_missing_ones_are_created(self):
        keys = [e.name for e in AchievementsElems]
        db = db_with(keys[1:])
        Achievements().populate_achievements(db)
        self.assertEqual([c.args[0].key for c in db.add.call_args_list], [keys[0]])

    def test_existing_rows_are_never_rewritten(self):
        db = db_with([e.name for e in AchievementsElems])
        Achievements().populate_achievements(db)
        db.add.assert_not_called()
        db.execute.assert_not_called()
        db.commit.assert_not_called()

    def test_a_database_error_is_rolled_back_not_raised(self):
        from sqlalchemy.exc import SQLAlchemyError

        db = db_with([])
        db.commit.side_effect = SQLAlchemyError("boom")
        Achievements().populate_achievements(db)
        db.rollback.assert_called_once()


if __name__ == "__main__":
    unittest.main()
