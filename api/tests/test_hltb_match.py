"""Which HowLongToBeat result is the game (utils/hltb_sync.pick): clear matches only, never a guess."""
import unittest
from types import SimpleNamespace

from src.utils import hltb_sync


def result(name, seconds=36000, year=None, kind="game", alias=None, game_id=1):
    return SimpleNamespace(
        game_id=game_id, game_name=name, game_alias=alias, game_type=kind, release_world=year, json_content={"comp_main": seconds}
    )


def pick(name, results, year=None):
    outcome, chosen = hltb_sync.pick(name, year, hltb_sync.candidates(results))
    return outcome, [c["name"] for c in chosen]


class PickTests(unittest.TestCase):
    def test_an_exact_name_matches_whatever_the_case_accents_and_punctuation(self):
        for wanted, found in (("hades", "Hades"), ("Pokemon: Rojo", "Pokémon Rojo"), ("The Witcher 3", "Witcher 3"), ("Tom & Jerry", "Tom and Jerry")):
            self.assertEqual(pick(wanted, [result(found), result("Something else")]), ("match", [found]), wanted)

    def test_the_alias_counts_as_the_name(self):
        self.assertEqual(pick("GTA V", [result("Grand Theft Auto V", alias="GTA V")]), ("match", ["Grand Theft Auto V"]))

    def test_a_sequel_is_not_the_game(self):
        self.assertEqual(pick("Hades", [result("Hades II")]), ("ambiguous", ["Hades II"]))
        self.assertEqual(pick("Hades 2", [result("Hades"), result("Hades II")]), ("match", ["Hades II"]))  # roman numerals read as digits
        self.assertEqual(pick("Hades 2", [result("Hades")])[0], "ambiguous")

    def test_an_online_only_game_is_still_the_game(self):
        self.assertEqual(pick("Helldivers II", [result("Helldivers 2", kind="multi")]), ("match", ["Helldivers 2"]))

    def test_a_game_without_an_end_is_still_the_game(self):
        self.assertEqual(pick("The Sims 4", [result("The Sims 4", kind="endless"), result("The Sims 4: Get to Work", kind="dlc")]), ("match", ["The Sims 4"]))

    def test_a_publisher_in_front_of_the_name_is_the_same_game(self):
        self.assertEqual(pick("UFC 5", [result("EA Sports UFC 5")]), ("match", ["EA Sports UFC 5"]))
        self.assertEqual(pick("Sid Meier's Civilization VI", [result("Civilization VI")]), ("match", ["Civilization VI"]))

    def test_words_added_at_the_end_or_other_numbers_are_another_game(self):
        self.assertNotEqual(pick("Doom", [result("Doom Eternal")])[0], "match")
        self.assertNotEqual(pick("Portal", [result("Aperture Portal")])[0], "match")  # one word is too little to go by
        self.assertNotEqual(pick("UFC 5", [result("EA Sports UFC 4")])[0], "match")
        self.assertNotEqual(pick("UFC 5", [result("EA Sports UFC 5"), result("Fight UFC 5")])[0], "match")  # two to choose from

    def test_any_type_but_the_ones_that_hang_from_a_game_is_the_game(self):
        for kind in ("multi", "endless", "compil", "a-type-hltb-has-not-invented-yet"):
            self.assertEqual(pick("Some Game", [result("Some Game", kind=kind)]), ("match", ["Some Game"]), kind)

    def test_mods_and_hacks_never_match(self):
        for kind in ("mod", "hack"):
            self.assertEqual(pick("Super Mario 64", [result("Super Mario 64", kind=kind)]), ("not_found", []), kind)

    def test_a_plain_game_comes_before_a_compilation_of_the_same_name(self):
        self.assertEqual(pick("Portal", [result("Portal", kind="compil", game_id=1), result("Portal", game_id=2)]), ("match", ["Portal"]))
        self.assertEqual(pick("Portal", [result("Portal", kind="compil", game_id=1), result("Portal", kind="endless", game_id=2)])[0], "ambiguous")

    def test_dlcs_never_match(self):
        self.assertEqual(pick("Hades", [result("Hades", kind="dlc")]), ("not_found", []))
        self.assertEqual(pick("Hades", [result("Hades", kind="dlc", game_id=1), result("Hades", game_id=2)])[0], "match")

    def test_two_exact_names_are_told_apart_by_the_year(self):
        old, new = result("Prey", year=2006, game_id=1), result("Prey", year=2017, game_id=2)
        outcome, chosen = hltb_sync.pick("Prey", 2017, hltb_sync.candidates([old, new]))
        self.assertEqual((outcome, [c["id"] for c in chosen]), ("match", [2]))
        self.assertEqual(hltb_sync.pick("Prey", None, hltb_sync.candidates([old, new]))[0], "ambiguous")
        self.assertEqual(hltb_sync.pick("Prey", 1999, hltb_sync.candidates([old, new]))[0], "ambiguous")

    def test_a_very_close_name_clearly_ahead_of_the_rest_matches(self):
        self.assertEqual(pick("Celeste", [result("Celest"), result("Knight")]), ("match", ["Celest"]))

    def test_a_close_name_with_a_rival_is_left_to_a_person(self):
        outcome, names = pick("Resident Evil", [result("Resident Evil 4"), result("Resident Evil 5")])
        self.assertEqual(outcome, "ambiguous")
        self.assertEqual(sorted(names), ["Resident Evil 4", "Resident Evil 5"])

    def test_nothing_alike_is_not_found(self):
        self.assertEqual(pick("Hades", [result("Zelda")]), ("not_found", []))
        self.assertEqual(pick("Hades", []), ("not_found", []))

    def test_best_entry_returns_the_entry_only_for_a_clear_match(self):
        hades = result("Hades", seconds=72000)
        self.assertIs(hltb_sync.best_entry("Hades", None, [hades, result("Zelda")]), hades)
        self.assertIsNone(hltb_sync.best_entry("Hades", None, [result("Hades II")]))
        self.assertIsNone(hltb_sync.best_entry("Hades", None, None))

    def test_the_time_is_the_main_story_in_seconds_and_zero_when_there_is_none(self):
        self.assertEqual(hltb_sync.candidates([result("Hades", seconds=72000)])[0]["seconds"], 72000)
        self.assertEqual(hltb_sync.candidates([result("Hades", seconds=None)])[0]["seconds"], 0)

    def test_the_search_is_given_the_name_without_colons_and_slashes(self):
        self.assertEqual(hltb_sync.clean_name("Zelda: A/B"), "Zelda A B")
        self.assertEqual(hltb_sync.clean_name("NieR:Automata"), "NieR Automata")  # joined, HLTB finds nothing

    def test_the_search_is_given_plain_quotes_because_hltb_finds_nothing_with_typographic_ones(self):
        self.assertEqual(hltb_sync.clean_name("Sid Meier’s Civilization VI"), "Sid Meier's Civilization VI")
        self.assertEqual(hltb_sync.clean_name("‘Quoted’ “Game”"), "'Quoted' \"Game\"")


if __name__ == "__main__":
    unittest.main()
