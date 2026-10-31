"""Which of RAWG's tags a game keeps. A tag is kept when it says what the game *is*: its genre, setting, theme or
mechanics (Horror, Open World, Souls-like, Crafting). It is dropped when it says something else: about the product or
the store (Steam features, controller support, accessibility menus, how it is sold), how it is shown (2D, third
person), how many play it, its sound, an opinion of it, or when it is a translation, a duplicate or a typo. The
genres of the games are in `games.genres`, so a tag that mixes one with a perspective ("2D Platformer") loses
nothing. How many games have a tag never matters: a genre only one game has is still a genre.

Both places that write `games.tags` (the RAWG sync and adding a game) build the text through `clean`, and
`utils/clean_game_tags.py` passes what is already stored through the same rules. `drop_reason` says which rule drops a
tag (for the reports); `keeps` is whether none does.

The rules are few and general so the list does not need a line for each odd tag; an exception goes to `IGNORED` (by
name) or, for a general rule that catches something good, to `KEPT`."""
import re

# Dropped by name (compared without case)
IGNORED = frozenset({
    # store and account features
    "family sharing", "in-app purchases", "includes level editor", "level editor", "includes source sdk", "valve anti-cheat enabled",
    "hdr available", "captions available", "3d vision", "trackir", "touch-friendly", "mouse only", "keyboard only option",
    "game engine", "unity", "mod", "moddable", "vr supported",
    # accessibility menus and options
    "adjustable difficulty", "adjustable text size", "playable without timed input", "camera comfort", "color alternatives",
    "stereo sound", "surround sound", "custom volume controls", "subtitle options", "chat speech-to-text", "chat text-to-speech",
    "narrated game menus", "save anytime",
    # how it is sold, made or released
    "early access", "free to play", "crowdfunded", "kickstarter", "true exclusive", "game maker's toolkit jam", "import",
    # an opinion of the game
    "masterpiece", "epic", "beautiful", "cult classic", "replay value", "difficult", "unforgiving",
    # not about the game
    "other", "experience", "foreign", "single player only", "solo",
    # typos of a tag that exists
    "mutliplayer", "philisophical",
})

# Dropped when the name has one of these words (whole words, so Steampunk stays): the features of the Steam store and of
# the accessibility menus, and the contests the game was made for
STORE_WORDS = frozenset({"steam", "available", "captions", "subtitle", "volume", "ludum"})

# How the game is shown, by word and by run of words (the hyphens count as spaces: "Third-Person Shooter"), and its sound
VIEW_WORDS = frozenset({"2d", "3d", "2.5d", "isometric"})
VIEW_PHRASES = ("first person", "third person", "3rd person", "top down", "side scroller")
SOUND_WORDS = frozenset({"soundtrack", "music"})

# Words of the other languages RAWG's tags come in (the Steam features translated: "Compat. total con mando", "Un
# jugador", "Mehrspieler"). A name with any of them, or with an accented letter (English tags have none), is a
# translation. They are words that mean nothing in English, so a real tag never has one
FOREIGN_WORDS = frozenset({
    "con", "del", "mando", "jugador", "multijugador", "cooperativo", "compras", "aplicativo", "jogador", "compatibilidade",
    "controle", "spieler", "einzelspieler", "mehrspieler", "familienbibliothek", "und", "mit", "partage",
    "familial", "aventure", "jcj", "jxj", "compat", "giocatori", "divano", "oyunculu",
})
FIRST_ACCENTED = 0xC0  # from here to LAST_LATIN: Latin letters with accents; the English names written with one are listed
ENGLISH_ACCENTS = ("pokémon",)

# Kept whatever the rules say (what the code itself reads, see utils/external_events.py)
KEPT = "horror"

# The highest character of the Latin alphabets with accents (U+024F); a name with anything above it is in another script
LAST_LATIN = 0x24F


def _foreign(name: str) -> bool:
    key = name.casefold()
    for english in ENGLISH_ACCENTS:
        key = key.replace(english, "")
    return any(FIRST_ACCENTED <= ord(letter) <= LAST_LATIN for letter in key) or any(word in FOREIGN_WORDS for word in re.findall(r"[a-z]+", key))


def drop_reason(name: str) -> str | None:
    """Why a tag is dropped (`empty`, `listed`, `players`, `view`, `sound`, `store`, `script`, `translation` or
    `lower case`), or None when it is kept."""
    name = name.strip()
    key = name.casefold()
    if not key:
        return "empty"
    if KEPT in key:
        return None
    words = re.findall(r"[a-z0-9.]+", key.replace("-", " "))
    phrase = " ".join(words)
    if key in IGNORED:
        return "listed"
    if "player" in key or any(word.startswith("multi") and not word.startswith("multiple") for word in words):
        return "players"
    if VIEW_WORDS.intersection(words) or any(view in phrase for view in VIEW_PHRASES):
        return "view"
    if SOUND_WORDS.intersection(words):
        return "sound"
    if "remote play" in phrase or STORE_WORDS.intersection(words) or any(word.startswith("controller") for word in words):
        return "store"
    if max(map(ord, name)) > LAST_LATIN:
        return "script"
    if _foreign(name):
        return "translation"
    if name[0].islower():
        return "lower case"
    return None


def keeps(name: str) -> bool:
    """Is a tag worth keeping? See `drop_reason`."""
    return drop_reason(name) is None


def clean(names) -> str:
    """The text for `games.tags` from RAWG's tag names: the ones worth keeping, each once (whatever its case), in the
    order RAWG gave them, comma separated. Nothing worth keeping gives the empty text."""
    seen: dict[str, str] = {}
    for name in names:
        name = (name or "").strip()
        if keeps(name):
            seen.setdefault(name.casefold(), name)
    return ",".join(seen.values())
