from urllib.parse import quote

import utils.keyboard as kb
from telegram import InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from utils.config import Config
from utils.duration import format_duration, format_players
from utils.my_utils import utils
from utils.logger import LogManager

log_manager = LogManager()
logger = log_manager.get_logger()

RECOMMENDATIONS = 10
LATEST = 10  # how many games the lists of "your games" show

config = Config()


async def _my_statistic(context: ContextTypes.DEFAULT_TYPE, ranking: str) -> list | dict:
    """The `data` of one of the sender's own statistics (GET /statistics/users/{username}?ranking=...)."""
    username = quote(context.user_data["app_user"]["username"])
    answer = await utils.fetch_json("GET", f"{config.API_URL}/statistics/users/{username}?ranking={ranking}")
    return answer[0]["data"]


def _numbered(items, line) -> str:
    return "".join(f"{i}. {line(elem)}\n" for i, elem in enumerate(items, start=1))


class MyRoutes:
    async def my_data(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        logger.info("My data")
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(text="¿Qué quieres consultar?", reply_markup=InlineKeyboardMarkup(kb.MY_DATA))
        return utils.MY_ROUTES

    async def my_games(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        logger.info("My games")
        games = await _my_statistic(context, "played_games")
        msg = f"Has jugado a {len(games)} juegos. Estos son los 10 últimos:\n"
        msg += _numbered(games[:LATEST], lambda e: f"{e['game_name']} ({format_duration(e['played_time'])})")
        await utils.response_conversation(update, context, msg)

    async def my_top_games(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        logger.info("My top games")
        games = await _my_statistic(context, "top_games")
        msg = "Este es tu top de juegos:\n" + _numbered(
            games[:LATEST], lambda e: f"{e['game_name']} - {format_duration(e['played_time'])}"
        )
        await utils.response_conversation(update, context, msg)

    async def my_completed_games(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        logger.info("My completed games")
        games = await _my_statistic(context, "completed_games")
        msg = "Estos son tus últimos juegos completados:\n" + _numbered(games, lambda e: e["game_name"])
        await utils.response_conversation(update, context, msg)

    async def my_achievements(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        logger.info("My achievements")
        achievements = await _my_statistic(context, "achievements")
        msg = "Estos son tus logros:\n" + _numbered(achievements, lambda e: e["title"])
        await utils.response_conversation(update, context, msg)

    async def my_streak(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        logger.info("My streak")
        data = await _my_statistic(context, "streak")
        msg = (
            "Estos son tus rachas:\n"
            f"Racha actual: {data['current_streak']}\n"
            f"Mejor racha: {data['best_streak']}\n"
            f"Fin mejor racha: {data['best_streak_date']}"
        )
        await utils.response_conversation(update, context, msg)

    async def recommendations(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        logger.info("Recommendations")
        username = quote(context.user_data["app_user"]["username"])
        games = await utils.fetch_json("GET", f"{config.API_URL}/users/{username}/recommendations?limit={RECOMMENDATIONS}")
        if not games:
            msg = "No hay nada que recomendarte: ya has probado todo lo que tienen los demás."
        else:
            msg = "Juegos que tienen los demás y tú no has jugado:\n" + _numbered(
                games, lambda e: f"{e['game_name']} ({format_players(e['players'])})"
            )
        await utils.response_conversation(update, context, msg)
