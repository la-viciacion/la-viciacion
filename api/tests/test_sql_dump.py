import datetime
import decimal
import unittest

from src.utils import sql_dump


class SqlValueTests(unittest.TestCase):
    def test_plain_values(self):
        self.assertEqual(sql_dump.sql_value(None), "NULL")
        self.assertEqual(sql_dump.sql_value(7), "7")
        self.assertEqual(sql_dump.sql_value(True), "1")
        self.assertEqual(sql_dump.sql_value(False), "0")
        self.assertEqual(sql_dump.sql_value(2.5), "2.5")
        self.assertEqual(sql_dump.sql_value(decimal.Decimal("8.50")), "8.50")

    def test_text_is_escaped_so_it_cannot_break_out_of_its_quotes(self):
        self.assertEqual(sql_dump.sql_value("O'Hara"), "'O\\'Hara'")
        self.assertEqual(sql_dump.sql_value("a\\b"), "'a\\\\b'")
        self.assertEqual(sql_dump.sql_value("x'; DROP TABLE users; --"), "'x\\'; DROP TABLE users; --'")
        self.assertEqual(sql_dump.sql_value("one\ntwo\r\0\x1a"), "'one\\ntwo\\r\\0\\Z'")

    def test_accents_and_emoji_travel_as_they_are(self):
        self.assertEqual(sql_dump.sql_value("Viciación 🎮"), "'Viciación 🎮'")

    def test_binary_values_are_hex(self):
        self.assertEqual(sql_dump.sql_value(b"\x89PNG"), "0x89504e47")
        self.assertEqual(sql_dump.sql_value(bytearray(b"\x00\xff")), "0x00ff")
        self.assertEqual(sql_dump.sql_value(b""), "''")

    def test_dates_and_times_are_quoted_text(self):
        self.assertEqual(sql_dump.sql_value(datetime.datetime(2026, 3, 1, 10, 5, 7)), "'2026-03-01 10:05:07'")
        self.assertEqual(sql_dump.sql_value(datetime.date(2026, 3, 1)), "'2026-03-01'")
        self.assertEqual(sql_dump.sql_value(datetime.time(9, 30)), "'09:30:00'")


class StatementTests(unittest.TestCase):
    def test_identifiers_are_quoted(self):
        self.assertEqual(sql_dump.quote_identifier("users"), "`users`")
        self.assertEqual(sql_dump.quote_identifier("we`ird"), "`we``ird`")

    def test_rows_go_in_one_insert(self):
        sql = sql_dump.insert_statement("games", ["id", "name", "dev"], [("g1", "Doom", None), ("g2", "Hades", "Supergiant")])
        self.assertEqual(sql, "INSERT INTO `games` (`id`, `name`, `dev`) VALUES\n('g1', 'Doom', NULL),\n('g2', 'Hades', 'Supergiant');\n")


if __name__ == "__main__":
    unittest.main()
