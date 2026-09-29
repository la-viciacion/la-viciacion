from telegram import InlineKeyboardButton

EXIT = "❌ Salir"

MAIN_MENU = [
    [
        InlineKeyboardButton("🕺 Mis estadísticas", callback_data="my_data"),
        InlineKeyboardButton("🏅 Rankings", callback_data="rankings"),
    ],
    [
        InlineKeyboardButton(EXIT, callback_data="cancel"),
    ],
]

MY_DATA = [
    [
        InlineKeyboardButton("🎮 Juegos", callback_data="my_games"),
        InlineKeyboardButton("✅ Completados", callback_data="my_completed_games"),
    ],
    [
        InlineKeyboardButton("⏳ Top juegos", callback_data="my_top_games"),
        InlineKeyboardButton("🥇 Logros", callback_data="my_achievements"),
    ],
    [
        InlineKeyboardButton("✨ Racha", callback_data="my_streak"),
    ],
    [
        InlineKeyboardButton("🔙 Atrás", callback_data="back"),
        InlineKeyboardButton(EXIT, callback_data="cancel"),
    ],
]

RANKING_MENU = [
    [
        InlineKeyboardButton("📅 Días", callback_data="user_days"),
        InlineKeyboardButton("⌚ Horas", callback_data="user_hours"),
    ],
    [
        InlineKeyboardButton("🎮 Jugados", callback_data="user_played_games"),
        InlineKeyboardButton("✅ Completados", callback_data="user_completed_games"),
    ],
    [
        InlineKeyboardButton("🥇 Logros", callback_data="user_achievements"),
        InlineKeyboardButton("🆚 Ratio", callback_data="user_ratio"),
    ],
    [
        InlineKeyboardButton("✨ R. actual", callback_data="user_current_streak"),
        InlineKeyboardButton("⭐ R. máx.", callback_data="user_best_streak"),
    ],
    # [
    #     InlineKeyboardButton("💸 Deuda técnica", callback_data="debt"),
    #     InlineKeyboardButton("🆕 Últimos jugados", callback_data="games_last_played"),
    # ],
    [
        InlineKeyboardButton("🏟️ Más jugados", callback_data="games_most_played"),
        # InlineKeyboardButton("🖥 Plataforma", callback_data="ranking_platform"),
    ],
    [
        InlineKeyboardButton("🔙 Atrás", callback_data="back"),
        InlineKeyboardButton(EXIT, callback_data="cancel"),
    ],
]

CANCEL = [EXIT]
