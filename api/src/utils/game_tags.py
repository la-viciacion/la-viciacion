"""Which of RAWG's tags a game keeps. RAWG's tags mix real themes (Horror, Open World, Souls-like) with the
features of the Steam store (achievements, cloud saves, controller support), duplicates in another case or
language and accessibility switches, which is noise for everything that reads them (the page of a game, the chat
search, the themed challenges). Both places that write `games.tags` (the RAWG sync and adding a game) build the
text through `clean`, so the noise never gets in.

The rules are on purpose few and general, so the list does not need a new line for each odd tag; an exception is
added to `IGNORED` or, for a general rule that catches something good, to `KEPT`."""
import re

# Dropped by name (compared without case)
IGNORED = frozenset({
    "family sharing", "in-app purchases", "includes level editor", "adjustable difficulty", "valve anti-cheat enabled",
    "playable without timed input", "camera comfort", "color alternatives", "stereo sound", "surround sound",
    "custom volume controls", "subtitle options", "hdr available", "captions available", "true exclusive",
})

# Dropped when the name has one of these words in it: the features of the Steam store and of the accessibility menus
IGNORED_WORDS = re.compile(r"steam|controller|support|available|remote play|captions|subtitle|volume", re.IGNORECASE)

# Kept whatever the rules say (what the code itself reads, see utils/external_events.py)
KEPT = frozenset({"horror"})

# The letters of English and of the Latin alphabet with accents; a name in another script is the translation of one
NON_LATIN = re.compile(r"[^\x20-\x7e -ɏ]")


def keeps(name: str) -> bool:
    """Is a tag worth keeping? Not if it is on the list, has one of the words of the Steam features, is in another
    script, or starts in lower case (the tags that people add to RAWG: `cooperative`, `steam-trading-cards`, `nature`,
    which repeat a proper one)."""
    key = name.strip().casefold()
    if not key:
        return False
    if key in KEPT or any(word in key for word in KEPT):
        return True
    return not (key in IGNORED or IGNORED_WORDS.search(key) or NON_LATIN.search(key) or name.strip()[0].islower())


def clean(names) -> str:
    """The text for `games.tags` from RAWG's tag names: the ones worth keeping, each once (whatever its case), in the
    order RAWG gave them, comma separated. Nothing worth keeping gives the empty text."""
    seen: dict[str, str] = {}
    for name in names:
        name = (name or "").strip()
        if keeps(name):
            seen.setdefault(name.casefold(), name)
    return ",".join(seen.values())
