import unittest

from fastapi.encoders import jsonable_encoder
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, select

from src.routers.statistics import plain


class PlainTests(unittest.TestCase):
    def setUp(self):
        metadata = MetaData()
        table = Table("t", metadata, Column("id", Integer), Column("name", String))
        engine = create_engine("sqlite://")
        metadata.create_all(engine)
        with engine.begin() as conn:
            conn.execute(table.insert(), [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}])
        with engine.connect() as conn:
            self.rows = conn.execute(select(table.c.id.label("user_id"), table.c.name)).fetchall()

    def test_rows_become_dicts_the_api_can_serialize(self):
        self.assertEqual(jsonable_encoder(plain(self.rows)), [{"user_id": 1, "name": "a"}, {"user_id": 2, "name": "b"}])

    def test_single_row_and_plain_values_pass_through(self):
        self.assertEqual(plain(self.rows[0]), {"user_id": 1, "name": "a"})
        self.assertEqual(plain({"message": "x"}), {"message": "x"})
        self.assertEqual(plain([]), [])


if __name__ == "__main__":
    unittest.main()
