"""The themes a group challenge can be about: the genres, settings and themes of the games, each one the tags of the
games that belong to it (the tags are RAWG's, `utils/game_tags.py` keeps the ones that say what a game is). A tag
that is only a feature (Crafting, Loot, Classes), a mode (Co-op), a look (Pixel Graphics) or a mood (Atmospheric)
is not a theme and is not here. A theme counts a game when it has **any** of its tags, so Terror is Horror, Survival
Horror... and the duplicates of a tag (Football, Soccer) are one theme.

A few themes overlap on purpose: Estrategia and Deportes are umbrellas of narrower ones. The names are what the
players see. When a challenge is launched the tags of its theme are written in its definition, so changing this list
never changes a challenge that already exists."""

# Genres and subgenres
GENRES = {
    "Rol": ("RPG", "Role Playing Game"),
    "Rol de acción": ("Action RPG",),
    "Rol japonés (JRPG)": ("JRPG",),
    "Rol de PC clásico (CRPG)": ("CRPG", "Party-Based RPG"),
    "Rol táctico": ("Tactical RPG", "Strategy RPG"),
    "MMORPG": ("MMORPG",),
    "Aventura de acción": ("Action-Adventure",),
    "Roguelike": ("Roguelike", "Roguelite", "Action Roguelike", "Roguelike Deckbuilder", "Roguevania"),
    "Metroidvania": ("Metroidvania", "Roguevania"),
    "Souls-like": ("Souls-like",),
    "Hack and slash": ("Hack and Slash", "Character Action Game", "Spectacle fighter"),
    "Beat 'em up": ("Beat 'em up",),
    "Shooter en primera persona (FPS)": ("FPS",),
    "Otros shooters": ("Arena Shooter", "Hero Shooter", "Extraction Shooter", "Twin Stick Shooter"),
    "Battle royale": ("Battle Royale",),
    "Shoot 'em up y bullet hell": ("Shoot 'Em Up", "Bullet Hell"),
    "MOBA": ("MOBA",),
    "Sigilo": ("Stealth",),
    "Supervivencia": ("Survival", "Open World Survival Craft"),
    "Terror": ("Horror", "Survival Horror", "psychological-horror", "Spooky"),
    "Mundo abierto": ("Open World",),
    "Sandbox": ("Sandbox",),
    "Plataformas": ("Puzzle Platformer", "Puzzle-Platformer", "Precision Platformer"),
    "Puzles": ("Logic", "Sokoban", "Escape Room", "Hidden Object"),
    "Point & click": ("Point & Click",),
    "Novela visual y ficción interactiva": ("Visual Novel", "Interactive Fiction", "Choose Your Own Adventure", "Text-Based"),
    "Walking simulator": ("Walking Simulator",),
    "Immersive sim": ("Immersive Sim",),
    "Estrategia (paraguas)": ("4X", "Grand Strategy", "RTS", "Real Time Tactics", "Action RTS", "Turn-Based Strategy", "Turn-Based Tactics", "Tactical", "Wargame"),
    "Estrategia en tiempo real": ("RTS", "Real Time Tactics", "Action RTS"),
    "Estrategia por turnos": ("Turn-Based Strategy", "Turn-Based Tactics", "Turn-Based Combat", "Turn-Based"),
    "4X y gran estrategia": ("4X", "Grand Strategy"),
    "Defensa de torres": ("Tower Defense",),
    "Gestión": ("Management", "Resource Management", "Time Management", "Economy", "Trading"),
    "Construcción": ("City Builder", "Colony Sim", "Base Building", "Building"),
    "Automatización": ("Automation",),
    "Granjas y vida cotidiana": ("Farming Sim", "Farming", "Agriculture", "Life Sim", "Hobby Sim"),
    "Citas (dating sim)": ("Dating Sim",),
    "Espacio": ("Space", "Space Sim", "Mars"),
    "Conducción": ("Driving", "Automobile Sim", "Offroad", "Vehicular Combat"),
    "Vuelo": ("Flight",),
    "Naval": ("Naval", "Naval Combat", "Sailing"),
    "Submarino": ("Underwater",),
    "Trenes": ("Trains",),
    "Deportes (paraguas)": ("Football", "Soccer", "Football (Soccer)", "Basketball", "Golf", "Bowling", "Wrestling"),
    "Fútbol": ("Football", "Soccer", "Football (Soccer)"),
    "Pesca y caza": ("Fishing", "Hunting"),
    "Cartas": ("Card Game", "Card Battler", "Trading Card Game", "Roguelike Deckbuilder", "Auto Battler"),
    "Juegos de mesa": ("Board Game",),
    "Ritmo": ("Rhythm",),
    "Hackers": ("Hacking",),
    "Detectives y misterio": ("Detective", "Investigation", "Mystery", "Noir"),
    "Crimen y atracos": ("Crime", "Heist"),
}

# Settings: where, when and with what the game happens
SETTINGS = {
    "Fantasía": ("Fantasy", "Dark Fantasy", "Dragons", "Magic", "Fairy Tale"),
    "Fantasía oscura": ("Dark Fantasy",),
    "Ciencia ficción": ("Sci-fi", "Futuristic", "Aliens", "Robots", "Mechs", "Artificial Intelligence"),
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
    "Guerra": ("War", "Military", "World War I", "World War II", "Wargame"),
    "Segunda Guerra Mundial": ("World War II",),
    "Western": ("Western",),
    "Piratas": ("Pirates",),
    "Ninjas y artes marciales": ("Ninja", "Martial Arts"),
    "Superhéroes": ("Superhero",),
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
    "Educación": ("Education",),
    "Surrealismo": ("Surreal", "Psychedelic", "Dreams", "Abstract"),
    "Acogedor (cozy)": ("Cozy", "Feel Good"),
}

THEMES = {**GENRES, **SETTINGS, **SUBJECTS}

