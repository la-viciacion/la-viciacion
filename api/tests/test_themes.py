"""The curated themes of the group challenges (utils/themes.py): the list itself must be consistent with the filter that
decides which tags the games keep, or a theme would count nothing."""
import unittest

from src.utils import game_tags, themes


class ThemesTests(unittest.TestCase):
    def test_every_tag_of_a_theme_is_one_the_games_keep(self):
        dropped = {(name, tag): game_tags.drop_reason(tag) for name, tags in themes.THEMES.items() for tag in tags if not game_tags.keeps(tag)}
        self.assertEqual(dropped, {})

    def test_a_theme_has_tags_and_names_are_not_repeated_whatever_their_case(self):
        names = [name.casefold() for name in themes.THEMES]
        self.assertEqual(len(names), len(set(names)))
        self.assertTrue(all(tags for tags in themes.THEMES.values()))

    def test_the_three_lists_do_not_share_a_theme(self):
        everything = [name for group in (themes.GENRES, themes.SETTINGS, themes.SUBJECTS) for name in group]
        self.assertEqual(len(everything), len(set(everything)))
        self.assertEqual(len(themes.THEMES), len(everything))

    def test_a_theme_name_fits_in_a_challenge_title(self):
        self.assertTrue(all(len(f"Temático: {name}") <= 120 for name in themes.THEMES))


if __name__ == "__main__":
    unittest.main()
