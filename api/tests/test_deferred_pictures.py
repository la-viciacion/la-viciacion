import unittest

from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Query

from src.crud import users
from src.crud.achievements import Achievements
from src.database import models
from tests.sqlite_db import make_session


class DeferredAvatarTests(unittest.TestCase):
    def test_loading_a_user_does_not_select_the_picture(self):
        sql = str(Query(models.User).statement.compile(dialect=mysql.dialect()))
        self.assertNotIn("avatar", sql)

    def test_the_picture_can_still_be_stored_and_read(self):
        db = make_session()
        db.add(models.User(id=1, name="Ana", username="ana", is_active=1))
        db.commit()
        users.upload_avatar(db, "ana", b"\x89PNGdata")
        self.assertEqual(bytes(users.get_avatar(db, "ana")[0]), b"\x89PNGdata")

    def test_a_user_without_picture_reads_none(self):
        db = make_session()
        db.add(models.User(id=1, name="Ana", username="ana", is_active=1))
        db.commit()
        self.assertIsNone(users.get_avatar(db, "ana")[0])


class DeferredAchievementImageTests(unittest.TestCase):
    def test_loading_an_achievement_does_not_select_the_picture(self):
        # the admin's list of awards loads up to 200 achievements at once
        sql = str(Query(models.Achievement).statement.compile(dialect=mysql.dialect()))
        self.assertNotIn("image", sql)

    def test_the_picture_can_still_be_stored_and_read(self):
        db = make_session()
        db.add(models.Achievement(key="K", title="T", message="M"))
        db.commit()
        Achievements().upload_image(db, "K", b"PNGdata")
        self.assertEqual(bytes(Achievements().get_image(db, "K")[0]), b"PNGdata")


if __name__ == "__main__":
    unittest.main()
