"""The curated themes of the group challenges (utils/themes.py): the list itself must be consistent with the filter that
decides which tags the games keep, or a theme would count nothing."""
import unittest

from src.utils import game_tags, themes


class ThemesTests(unittest.TestCase):
    def test_every_tag_of_a_theme_is_one_the_games_keep(self):
        dropped = {
            (name, tag): game_tags.drop_reason(tag)
            for name, tags in themes.THEMES.items() for tag in tags if tag not in themes.IGDB_ONLY and not game_tags.keeps(tag)
        }
        self.assertEqual(dropped, {})

    def test_the_names_only_igdb_uses_are_in_a_theme_and_would_really_be_dropped_for_rawg(self):
        in_themes = {tag for tags in themes.THEMES.values() for tag in tags}
        self.assertEqual(themes.IGDB_ONLY - in_themes, set())
        self.assertTrue(all(not game_tags.keeps(tag) for tag in themes.IGDB_ONLY))

    def test_igdbs_names_count_for_the_themes_like_rawgs(self):
        owned = lambda name, *words: {w.casefold() for w in words} & {t.casefold() for t in themes.THEMES[name]}  # noqa: E731
        self.assertTrue(owned("Rol", "Role-playing (RPG)"))
        self.assertTrue(owned("Ciencia ficción", "Science fiction"))
        self.assertTrue(owned("Terror", "Psychological horror"))
        self.assertTrue(owned("Estrategia en tiempo real", "Real Time Strategy (RTS)"))
        self.assertTrue(owned("Souls-like", "Soulslike"))
        self.assertTrue(owned("Guerra", "Warfare"))

    def test_the_broad_genres_are_themes_in_both_vocabularies(self):
        owned = lambda name, word: word.casefold() in {t.casefold() for t in themes.THEMES[name]}  # noqa: E731
        for name, words in (("Puzles", ("Puzzle",)), ("Estrategia (paraguas)", ("Strategy",)), ("Conducción", ("Racing",)), ("Deportes (paraguas)", ("Sport", "Sports"))):
            self.assertTrue(all(owned(name, word) for word in words), name)

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
