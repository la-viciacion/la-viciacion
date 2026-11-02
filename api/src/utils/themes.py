"""The themes a group challenge can be about: the genres, settings and themes of the games, each one the tags of the
games that belong to it (the tags are RAWG's, `utils/game_tags.py` keeps the ones that say what a game is). A tag
that is only a feature (Crafting, Loot, Classes), a mode (Co-op), a look (Pixel Graphics) or a mood (Atmospheric)
is not a theme and is not here. A theme counts a game when it has **any** of its tags, so Terror is Horror, Survival
Horror... and the duplicates of a tag (Football, Soccer) are one theme.

A few themes overlap on purpose: Estrategia and Deportes are umbrellas of narrower ones. The names are what the
players see. When a challenge is launched the tags of its theme are written in its definition, so changing this list
never changes a challenge that already exists.

A game is described by RAWG's tags and by IGDB's themes, keywords, franchises, collections and genres (`game_tags.words`),
two vocabularies that call the same thing differently ("Sci-fi" and "Science fiction", "RPG" and "Role-playing (RPG)"):
a theme lists the names of both. The names of IGDB were chosen by looking at what its games say that RAWG's say as a
theme of this list."""

# Names of IGDB that the filter of RAWG's tags would drop (`game_tags`): IGDB's go to `games` without passing through it
IGDB_ONLY = frozenset({"Music and rhythm", "Massively Multiplayer Online (MMO)"})

# Genres and subgenres
GENRES = {
    "Rol": ("RPG", "Role Playing Game", "Role-playing (RPG)"),
    "Rol de acción": ("Action RPG", "Action-RPG", "ARPG"),
    "Rol japonés (JRPG)": ("JRPG",),
    "Rol de PC clásico (CRPG)": ("CRPG", "Party-Based RPG", "Party-based"),
    "Rol táctico": ("Tactical RPG", "Strategy RPG"),
    "MMORPG": ("MMORPG", "Massively Multiplayer Online (MMO)"),
    "Aventura de acción": ("Action-Adventure",),
    "Roguelike": ("Roguelike", "Roguelite", "Action Roguelike", "Roguelike Deckbuilder", "Roguevania"),
    "Metroidvania": ("Metroidvania", "Roguevania"),
    "Souls-like": ("Souls-like", "Soulslike"),
    "Hack and slash": ("Hack and Slash", "Character Action Game", "Spectacle fighter", "Hack and slash/Beat 'em up"),
    "Beat 'em up": ("Beat 'em up", "Hack and slash/Beat 'em up"),
    "Shooter en primera persona (FPS)": ("FPS",),
    "Otros shooters": ("Arena Shooter", "Hero Shooter", "Extraction Shooter", "Twin Stick Shooter"),
    "Battle royale": ("Battle Royale",),
    "Shoot 'em up y bullet hell": ("Shoot 'Em Up", "Bullet Hell"),
    "MOBA": ("MOBA",),
    "Sigilo": ("Stealth",),
    "Supervivencia": ("Survival", "Open World Survival Craft"),
    "Terror": ("Horror", "Survival Horror", "psychological-horror", "Psychological horror", "Spooky"),
    "Mundo abierto": ("Open World",),
    "Sandbox": ("Sandbox",),
    "Plataformas": ("Puzzle Platformer", "Puzzle-Platformer", "Precision Platformer"),
    "Puzles": ("Logic", "Sokoban", "Escape Room", "Hidden Object", "Puzzle"),
    "Point & click": ("Point & Click", "Point-and-click"),
    "Novela visual y ficción interactiva": ("Visual Novel", "Interactive Fiction", "Choose Your Own Adventure", "Text-Based"),
    "Walking simulator": ("Walking Simulator",),
    "Immersive sim": ("Immersive Sim",),
    "Estrategia (paraguas)": ("4X", "Grand Strategy", "RTS", "Real Time Tactics", "Action RTS", "Turn-Based Strategy", "Turn-Based Tactics", "Tactical", "Wargame", "Strategy", "Real Time Strategy (RTS)", "Turn-based strategy (TBS)"),
    "Estrategia en tiempo real": ("RTS", "Real Time Tactics", "Action RTS", "Real Time Strategy (RTS)"),
    "Estrategia por turnos": ("Turn-Based Strategy", "Turn-Based Tactics", "Turn-Based Combat", "Turn-Based", "Turn-based strategy (TBS)"),
    "4X y gran estrategia": ("4X", "Grand Strategy"),
    "Defensa de torres": ("Tower Defense",),
    "Gestión": ("Management", "Resource Management", "Time Management", "Economy", "Trading", "Business"),
    "Construcción": ("City Builder", "Colony Sim", "Colony Simulator", "Base Building", "Building"),
    "Automatización": ("Automation",),
    "Granjas y vida cotidiana": ("Farming Sim", "Farming", "Agriculture", "Life Sim", "Hobby Sim"),
    "Citas (dating sim)": ("Dating Sim",),
    "Espacio": ("Space", "Space Sim", "Mars", "Space combat", "Space simulation", "Space exploration"),
    "Conducción": ("Driving", "Automobile Sim", "Offroad", "Vehicular Combat", "Racing", "Vehicle simulation"),
    "Vuelo": ("Flight", "Flight simulator"),
    "Naval": ("Naval", "Naval Combat", "Sailing"),
    "Submarino": ("Underwater",),
    "Trenes": ("Trains",),
    "Deportes (paraguas)": ("Football", "Soccer", "Football (Soccer)", "Basketball", "Golf", "Bowling", "Wrestling", "Sport", "Sports"),
    "Fútbol": ("Football", "Soccer", "Football (Soccer)"),
    "Pesca y caza": ("Fishing", "Hunting"),
    "Cartas": ("Card Game", "Card Battler", "Trading Card Game", "Roguelike Deckbuilder", "Auto Battler", "Card & Board Game"),
    "Juegos de mesa": ("Board Game", "Card & Board Game"),
    "Ritmo": ("Rhythm", "Music and rhythm"),
    "Hackers": ("Hacking",),
    "Detectives y misterio": ("Detective", "Investigation", "Mystery", "Noir"),
    "Crimen y atracos": ("Crime", "Heist"),
}

# Settings: where, when and with what the game happens
SETTINGS = {
    "Fantasía": ("Fantasy", "Dark Fantasy", "Dragons", "Magic", "Fairy Tale"),
    "Fantasía oscura": ("Dark Fantasy",),
    "Ciencia ficción": ("Sci-fi", "Science fiction", "Futuristic", "Aliens", "Robots", "Mechs", "Artificial Intelligence"),
    "Cyberpunk": ("Cyberpunk",),
    "Distopía": ("Dystopian",),
    "Steampunk": ("Steampunk",),
    "Postapocalíptico": ("Post-apocalyptic",),
    "Zombis": ("Zombies",),
    "Vampiros": ("Vampire",),
    "Sobrenatural": ("Supernatural", "Ghosts", "Demons", "Skeletons", "Monsters"),
    "Lovecraftiano": ("Lovecraftian",),
    "Gótico": ("Gothic",),
    "Medieval": ("Medieval", "Swordplay", "Swords"),
    "Histórico": ("Historical", "Rome", "Alternate History"),
    "Mitología": ("Mythology", "Norse"),
    "Guerra": ("War", "Warfare", "Military", "World War I", "World War II", "World War II - WW2", "Wargame"),
    "Segunda Guerra Mundial": ("World War II", "World War II - WW2"),
    "Western": ("Western",),
    "Piratas": ("Pirates",),
    "Ninjas y artes marciales": ("Ninja", "Martial Arts"),
    "Superhéroes": ("Superhero", "Marvel"),
    "Anime": ("Anime",),
    "Dinosaurios": ("Dinosaurs",),
    "Animales": ("Dog", "Dogs", "Horses"),
    "Moderno": ("Modern",),
    "Estados Unidos": ("America",),
    "Años 80": ("1980s",),
    "Años 90": ("1990's",),
    "Retro": ("Retro", "Old School", "8-Bit"),
    "Star Wars": ("Star Wars",),
    "Warhammer": ("Warhammer 40K", "Games Workshop"),
    "LEGO": ("LEGO",),
    "Dungeons & Dragons": ("Dungeons & Dragons",),
}

# Themes the story is about
SUBJECTS = {
    "Política": ("Politics", "Political", "Political Sim", "Capitalism"),
    "Conspiraciones": ("Conspiracy", "Illuminati"),
    "Romance": ("Romance",),
    "Comedia y sátira": ("Comedy", "Parody", "Satire", "Dark Humor", "Memes"),
    "Drama": ("Drama",),
    "Thriller": ("Thriller",),
    "Salud mental": ("Mental Health",),
    "Educación": ("Education", "Educational"),
    "Surrealismo": ("Surreal", "Psychedelic", "Dreams", "Abstract"),
    "Acogedor (cozy)": ("Cozy", "Feel Good"),
}

THEMES = {**GENRES, **SETTINGS, **SUBJECTS}

