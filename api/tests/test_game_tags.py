"""Which of RAWG's tags a game keeps (utils/game_tags.py): the themes stay, the noise of the Steam store, the other
alphabets and the repeated ones go."""
import unittest

from src.utils import game_tags


class CleanTests(unittest.TestCase):
    def test_the_themes_stay_in_the_order_rawg_gave_them(self):
        names = ["Metroidvania", "Horror", "Open World", "Souls-like", "Crafting", "1990's", "Beat 'em up", "FPS", "Multiple Endings"]
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
        self.assertEqual(game_tags.clean(["Steampunk", "Steam Cloud"]), "Steampunk")

    def test_a_name_in_another_script_or_in_lower_case_goes(self):
        self.assertEqual(game_tags.clean(["Протагонистка", "2D-платформер", "cooperative", "steam-trading-cards", "nature", "RPG"]), "RPG")

    def test_an_accented_name_is_a_translation_except_the_english_ones_that_have_an_accent(self):
        self.assertEqual(game_tags.clean(["Pokémon-like", "Jeu de rôle", "Stratégie", "HDR verfügbar", "Fantasy"]), "Pokémon-like,Fantasy")

    def test_the_steam_features_translated_go(self):
        translations = ["Compat. total con mando", "Compatibilidade parcial com controle", "Compras em aplicativo", "Cooperativo online",
                        "Un jugador", "Um jogador", "Einzelspieler", "Mehrspieler", "JcJ en línea", "Partage familial", "4 giocatori divano", "Tek Oyunculu"]
        self.assertEqual(game_tags.clean([*translations, "Mind Control"]), "Mind Control")

    def test_how_it_is_shown_how_many_play_its_sound_and_opinions_of_it_go(self):
        noise = [
            "2D", "3D", "2.5D", "2D Platformer", "3D Fighter", "First-Person", "Third Person", "3rd-person", "3rd-Person Perspective",
            "Third-Person Shooter", "Top-Down", "Top-Down Shooter", "Isometric", "Side Scroller",
            "Singleplayer", "Multiplayer", "2 players", "4 Player Local", "Online multiplayer", "Asynchronous Multiplayer", "Solo",
            "Soundtrack", "Great Soundtrack", "Music", "Instrumental Music",
            "Masterpiece", "Epic", "Beautiful", "Replay Value",
        ]
        self.assertEqual(game_tags.clean([*noise, "Co-op", "FPS", "Platformer", "Multiple Endings", "Rhythm"]), "Co-op,FPS,Platformer,Multiple Endings,Rhythm")

    def test_the_reason_a_tag_goes_is_named(self):
        reasons = {name: game_tags.drop_reason(name) for name in ["Steam Cloud", "3D", "Multiplayer", "Soundtrack", "Un jugador", "cooperative", "Early Access", "Horror"]}
        self.assertEqual(reasons, {"Steam Cloud": "store", "3D": "view", "Multiplayer": "players", "Soundtrack": "sound", "Un jugador": "translation", "cooperative": "lower case", "Early Access": "listed", "Horror": None})

    def test_what_the_game_offers_as_a_product_goes_and_what_it_is_stays(self):
        product = ["Early Access", "Free to Play", "Moddable", "Level Editor", "Save Anytime", "Ludum Dare 33", "Kickstarter", "VR Supported"]
        self.assertEqual(game_tags.clean([*product, "Metroidvania", "Cozy", "Warhammer 40K"]), "Metroidvania,Cozy,Warhammer 40K")

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
