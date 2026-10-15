import utils.keyboard as kb
from telegram import InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from utils.config import Config
from utils.duration import format_duration
from utils.my_utils import MyUtils
from utils.logger import LogManager

log_manager = LogManager()
logger = log_manager.get_logger()

utils = MyUtils()
config = Config()


def _debt_line(elem: dict) -> str:
    return f"{format_duration(elem['debt_time'])} en {elem['games']} juegos"


class RankingRoutes:
    async def rankings(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        logger.info("Ranking")
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(text="Elije un ranking:", reply_markup=InlineKeyboardMarkup(kb.RANKING_MENU))
        return utils.RANKING_ROUTES

    async def _ranking(self, update: Update, context: ContextTypes.DEFAULT_TYPE, ranking: str, title: str, value) -> None:
        """One line per player (or game) of the group's ranking `ranking` of the running season: `value(elem)` is what
        follows the name."""
        logger.info(f"Ranking {ranking}")
        answer = await utils.fetch_json("GET", f"{config.API_URL}/statistics/rankings?ranking={ranking}&only_active=true")
        lines = [f"{i}. {elem['name']}: {value(elem)}\n" for i, elem in enumerate(answer[0]["data"], start=1)]
        await utils.response_conversation(update, context, title + "\n" + "".join(lines))

    async def user_hours(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._ranking(update, context, "user_hours", "Así está el ranking de horas de vicio:",
                            lambda e: format_duration(e["played_time"]))

    async def user_days(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._ranking(update, context, "user_days", "Así está el ranking de días de vicio:", lambda e: e["played_days"])

    async def user_played_games(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._ranking(update, context, "user_played_games", "Ranking de juegos jugados:", lambda e: e["played_games"])

    async def user_achievements(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._ranking(update, context, "achievements", "Ranking de logros:", lambda e: e["achievements"])

    async def user_best_streak(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._ranking(update, context, "user_best_streak", "Así va el ranking de racha de días:", lambda e: e["best_streak"])

    async def user_current_streak(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._ranking(update, context, "user_current_streak", "Estas son las rachas de días actuales:",
                            lambda e: e["current_streak"])

    async def user_ratio(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._ranking(update, context, "user_ratio", "Así está el ranking de ratio (completados / jugados):",
                            lambda e: e["ratio"])

    async def user_completed_games(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._ranking(update, context, "user_completed_games", "Ranking de juegos completados:",
                            lambda e: e["completed_games"])

    async def games_most_played(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._ranking(update, context, "games_most_played", "Ranking de juegos más jugados:",
                            lambda e: format_duration(e["played_time"]))

    async def user_debt(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._ranking(update, context, "debt", "Lo que le queda a cada uno por jugar esta temporada (según HLTB):",
                            _debt_line)

    async def user_debt_total(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._ranking(update, context, "debt_total", "Lo que le queda a cada uno por jugar en total (según HLTB):",
                            _debt_line)
