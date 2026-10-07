import datetime
import unittest

from src.utils import external_events as events


class GamesTests(unittest.TestCase):
    def test_star_wars_by_name_or_by_tag(self):
        for name in ("STAR WARS Jedi: Fallen Order", "LEGO Star Wars: The Skywalker Saga", "Star Wars: Knights of the Old Republic",
                     "Star Wars: TIE Fighter", "Star Wars Battlefront II", "Jedi Knight: Dark Forces II", "Star  Wars Outlaws"):
            self.assertTrue(events.is_star_wars(name, None), name)
        self.assertTrue(events.is_star_wars("Rogue Squadron", "Singleplayer, Star Wars"))
        for name in ("Starfield", "Warframe", "Starcraft II", "Doom"):
            self.assertFalse(events.is_star_wars(name, "Singleplayer"), name)

    def test_mario_is_a_word_of_the_name(self):
        for name in ("Super Mario Odyssey", "Mario Kart 8 Deluxe", "Paper Mario: The Origami King", "Dr. Mario", "Mario & Luigi: Superstar Saga"):
            self.assertTrue(events.is_mario(name, None), name)
        for name in ("Marionette", "Mariokart", "Luigi's Mansion 3", "Maria"):
            self.assertFalse(events.is_mario(name, None), name)

    def test_horror_is_a_tag_because_there_is_no_such_genre(self):
        self.assertTrue(events.is_horror("Silent Hill 2", "Singleplayer,Horror,Atmospheric"))
        self.assertTrue(events.is_horror("Resident Evil 4", "Survival Horror"))
        self.assertFalse(events.is_horror("Doom", "Singleplayer,Action"))
        self.assertFalse(events.is_horror("Doom", None))


class DaysTests(unittest.TestCase):
    def test_fixed_days_of_every_year(self):
        years = range(2027, 2030)
        self.assertEqual(events.days_of("STAR_WARS_DAY_LIFETIME", years, None), {datetime.date(y, 5, 4) for y in years})
        self.assertEqual(events.days_of("MARIO_DAY_LIFETIME", years, None), {datetime.date(y, 3, 10) for y in years})

    def test_the_leap_day_exists_only_in_leap_years(self):
        self.assertEqual(events.days_of("LEAP_DAY_LIFETIME", range(2027, 2033), None), {datetime.date(2028, 2, 29), datetime.date(2032, 2, 29)})

    def test_a_birthday_needs_a_birth_date_and_a_leap_birthday_moves_to_the_28th(self):
        self.assertEqual(events.days_of("BIRTHDAY_LIFETIME", [2027], None), frozenset())
        born = datetime.date(1990, 6, 15)
        self.assertEqual(events.days_of("BIRTHDAY_LIFETIME", [2027, 2028], born), {datetime.date(2027, 6, 15), datetime.date(2028, 6, 15)})
        leap = datetime.date(1992, 2, 29)
        self.assertEqual(events.days_of("BIRTHDAY_LIFETIME", [2027, 2028], leap), {datetime.date(2027, 2, 28), datetime.date(2028, 2, 29)})

    def test_every_achievement_of_a_day_is_known(self):
        for key in events.DAYS:
            self.assertIsInstance(events.days_of(key, [2027], datetime.date(1990, 1, 1)), frozenset)
        self.assertTrue(set(events.GAME_RULES) <= set(events.DAYS))


class ArchaeologyTests(unittest.TestCase):
    def test_a_game_of_25_years_or_more(self):
        played = datetime.date(2027, 6, 10)
        self.assertTrue(events.is_archaeological(datetime.date(2002, 6, 10), played))  # exactly 25 years
        self.assertTrue(events.is_archaeological(datetime.date(1993, 12, 10), played))
        self.assertFalse(events.is_archaeological(datetime.date(2002, 6, 11), played))  # a day short
        self.assertFalse(events.is_archaeological(None, played))

    def test_a_game_of_the_29th_of_february(self):
        self.assertTrue(events.is_archaeological(datetime.date(2000, 2, 29), datetime.date(2025, 3, 1)))
        self.assertEqual(events.years_before(datetime.date(2028, 2, 29), 25), datetime.date(2003, 2, 28))
