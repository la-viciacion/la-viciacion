import telegram
import telegram.ext.filters as FILTERS
from routes.basic_routes import BasicRoutes
from routes.my_routes import MyRoutes
from routes.ranking_routes import RankingRoutes
from telegram import BotCommand, Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)
from utils.config import Config
from utils.my_utils import MyUtils
from utils.logger import LogManager
from utils.read_messages import ReadMessages

read_messages = ReadMessages()
log_manager = LogManager()
logger = log_manager.get_logger()
import sentry_sdk
from sentry_sdk.types import Event, Hint

##########
## INIT ##
##########

utils = MyUtils()
config = Config()
my_routes = MyRoutes()
basic_routes = BasicRoutes()
ranking_routes = RankingRoutes()


def before_send(event: Event, hint: Hint):
    # modify event here
    logger.info("------BEFORE SENTRY------")
    logger.info("Hint:")
    logger.info(hint)
    # exc_info_str = str(hint.get("exc_info"))
    # logger.info(exc_info_str)
    return event


if config.SENTRY_URL is not None and config.SENTRY_URL != "":
    sentry_sdk.init(
        dsn=config.SENTRY_URL,
        # Set traces_sample_rate to 1.0 to capture 100%
        # of transactions for tracing.
        traces_sample_rate=1.0,
        # Set profiles_sample_rate to 1.0 to profile 100%
        # of sampled transactions.
        # We recommend adjusting this value in production.
        ignore_errors=[telegram.error.NetworkError],
        profiles_sample_rate=1.0,
        environment=config.ENVIRONMENT,
        before_send=before_send,
    )



async def post_init(application: Application):
    await application.bot.set_my_commands(
        [
            BotCommand("/start", "Iniciar el chat"),
            BotCommand("/menu", "Menú principal"),
            BotCommand("/help", "Ayuda"),
        ]
    )


def main() -> None:
    app = ApplicationBuilder().token(config.TELEGRAM_TOKEN).post_init(post_init).build()
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("menu", basic_routes.menu),
        ],
        states={
            utils.MAIN_MENU: [
                CallbackQueryHandler(my_routes.my_data, pattern="^" + "my_data" + "$"),
                CallbackQueryHandler(
                    ranking_routes.rankings, pattern="^" + "rankings" + "$"
                ),
                CallbackQueryHandler(basic_routes.end, pattern="^" + "cancel" + "$"),
            ],
            utils.MY_ROUTES: [
                CallbackQueryHandler(
                    my_routes.my_games, pattern="^" + "my_games" + "$"
                ),
                CallbackQueryHandler(
                    my_routes.my_completed_games,
                    pattern="^" + "my_completed_games" + "$",
                ),
                CallbackQueryHandler(
                    my_routes.my_achievements, pattern="^" + "my_achievements" + "$"
                ),
                CallbackQueryHandler(
                    my_routes.my_top_games, pattern="^" + "my_top_games" + "$"
                ),
                CallbackQueryHandler(
                    my_routes.my_streak, pattern="^" + "my_streak" + "$"
                ),
                CallbackQueryHandler(basic_routes.back, pattern="^" + "back" + "$"),
                CallbackQueryHandler(basic_routes.end, pattern="^" + "cancel" + "$"),
            ],
            utils.RANKING_ROUTES: [
                CallbackQueryHandler(
                    ranking_routes.user_achievements,
                    pattern="^" + "user_achievements" + "$",
                ),
                CallbackQueryHandler(
                    ranking_routes.user_completed_games,
                    pattern="^" + "user_completed_games" + "$",
                ),
                CallbackQueryHandler(
                    ranking_routes.user_days,
                    pattern="^" + "user_days" + "$",
                ),
                CallbackQueryHandler(
                    ranking_routes.user_hours,
                    pattern="^" + "user_hours" + "$",
                ),
                CallbackQueryHandler(
                    ranking_routes.user_played_games,
                    pattern="^" + "user_played_games" + "$",
                ),
                CallbackQueryHandler(
                    ranking_routes.user_ratio, pattern="^" + "user_ratio" + "$"
                ),
                CallbackQueryHandler(
                    ranking_routes.user_best_streak,
                    pattern="^" + "user_best_streak" + "$",
                ),
                CallbackQueryHandler(ranking_routes.debt, pattern="^" + "debt" + "$"),
                CallbackQueryHandler(
                    ranking_routes.games_last_played,
                    pattern="^" + "games_last_played" + "$",
                ),
                CallbackQueryHandler(
                    ranking_routes.games_most_played,
                    pattern="^" + "games_most_played" + "$",
                ),
                CallbackQueryHandler(
                    ranking_routes.user_current_streak,
                    pattern="^" + "user_current_streak" + "$",
                ),
                CallbackQueryHandler(basic_routes.back, pattern="^" + "back" + "$"),
                CallbackQueryHandler(basic_routes.end, pattern="^" + "cancel" + "$"),
            ],
        },
        fallbacks=[CommandHandler("menu", basic_routes.menu)],
        per_user=True,
        conversation_timeout=60,
    )
    app.add_handler(CommandHandler("info_dev", utils.info_dev))
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("start", utils.start))
    app.add_handler(CommandHandler("help", utils.help))
    # app.add_handler(MessageHandler(None, other_routes.random_response))
    app.add_handler(MessageHandler(None, read_messages.read_message))
    app.run_polling()


if __name__ == "__main__":
    main()
