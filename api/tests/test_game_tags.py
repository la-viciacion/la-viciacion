"""Which of RAWG's tags a game keeps (utils/game_tags.py): the themes stay, the noise of the Steam store, the other
alphabets and the repeated ones go."""
import unittest

from src.utils import game_tags


class CleanTests(unittest.TestCase):
    def test_the_themes_stay_in_the_order_rawg_gave_them(self):
        names = ["Singleplayer", "Horror", "Open World", "Souls-like", "2.5D", "1990's", "Beat 'em up", "FPS"]
        self.assertEqual(game_tags.clean(names), ",".join(names))

    def test_the_features_of_the_steam_store_and_the_accessibility_menus_go(self):
        noise = [
            "Steam Achievements", "Steam Cloud", "Steam Trading Cards", "Steam Workshop", "Full controller support",
            "Partial Controller Support", "Controller", "Family Sharing", "In-App Purchases", "HDR available",
            "Captions available", "Custom Volume Controls", "Stereo Sound", "Surround Sound", "Subtitle Options",
            "Remote Play Together", "Remote Play on TV", "Camera Comfort", "Color Alternatives",
        ]
        self.assertEqual(game_tags.clean(["Horror", *noise, "Co-op"]), "Horror,Co-op")

    def test_a_word_of_the_noise_inside_another_word_does_not_drop_a_theme(self):
        self.assertEqual(game_tags.clean(["Steampunk", "VR Supported", "Steam Cloud"]), "Steampunk,VR Supported")

    def test_a_name_in_another_script_or_in_lower_case_goes(self):
        self.assertEqual(game_tags.clean(["Протагонистка", "2D-платформер", "cooperative", "steam-trading-cards", "nature", "RPG"]), "RPG")

    def test_accents_are_not_another_script(self):
        self.assertEqual(game_tags.clean(["Fantasía", "Pokémon-like"]), "Fantasía,Pokémon-like")

    def test_every_horror_tag_stays_because_the_achievements_read_them(self):
        names = ["Horror", "Survival Horror", "Psychological Horror", "horror"]
        self.assertEqual(game_tags.clean(names), "Horror,Survival Horror,Psychological Horror")

    def test_a_tag_is_kept_once_whatever_its_case(self):
        self.assertEqual(game_tags.clean(["Co-op", "CO-OP", "Sci-fi"]), "Co-op,Sci-fi")

    def test_nothing_worth_keeping_is_the_empty_text_and_blanks_are_ignored(self):
        self.assertEqual(game_tags.clean(["Steam Cloud", "", None, "  "]), "")
        self.assertEqual(game_tags.clean([]), "")

    def test_cleaning_twice_changes_nothing(self):
        once = game_tags.clean(["Horror", "Steam Cloud", "cooperative", "Open World", "open world"])
        self.assertEqual(game_tags.clean(once.split(",")), once)


if __name__ == "__main__":
    unittest.main()
