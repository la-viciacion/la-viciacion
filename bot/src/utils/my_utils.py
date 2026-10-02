import json

import telegram
import utils.access as access
import utils.messages as msgs
from telegram import Update
from telegram.ext import ApplicationHandlerStop, ContextTypes, ConversationHandler
from utils.config import Config
from utils.logger import LogManager

log_manager = LogManager()
logger = log_manager.get_logger()

config = Config()


class ApiError(Exception):
    """The API did not give a usable answer."""

    def __init__(self, status_code: int):
        super().__init__(f"API error {status_code}")
        self.status_code = status_code


class MyUtils:
    """API access, the access gate and the handlers shared by every flow."""

    def __init__(self):
        # Conversation routes
        (
            self.MAIN_MENU,
            self.MY_ROUTES,
            self.RANKING_ROUTES,
        ) = range(3)

    def make_request(self, method, url, json=None):
        return config.request(method, url, json=json)

    def fetch_json(self, method, url, json=None):
        """Request the API and return the parsed body; raise ApiError if it did not answer 200 with JSON."""
        response = self.make_request(method, url, json=json)
        if response.status_code != 200:
            logger.error(f"API answered {response.status_code} to {method} {url}: {response.text[:200]}")
            raise ApiError(response.status_code)
        try:
            return response.json()
        except ValueError:
            logger.error(f"API answered a non-JSON body to {method} {url}: {response.text[:200]}")
            raise ApiError(response.status_code)

    async def gate(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Runs before every handler: nothing gets past it unless the chat and the sender are the app's.

        Other groups and channels get no answer at all (not even an error), so the bot
        gives no sign of life there. The account is found by the sender's Telegram id.
        """
        chat, sender, message = update.effective_chat, update.effective_user, update.message
        if chat is None or sender is None or sender.is_bot or not (message or update.callback_query):
            raise ApplicationHandlerStop  # edits, membership changes...: nothing here handles them
        command = access.command_of(message.text if message else None)
        if command and not access.addressed_to(message.text, context.bot.username):
            raise ApplicationHandlerStop  # a command for another bot in the group
        if not access.chat_allowed(chat.type, chat.id, config.TELEGRAM_GROUP_ID):
            raise ApplicationHandlerStop
        if chat.type != access.PRIVATE and message and command is None:
            raise ApplicationHandlerStop  # group chatter is none of our business
        if command in ("activate", "start"):
            # for people not linked yet, and only inside the app's group
            if chat.type != access.PRIVATE:
                return
            if command == "activate":
                raise ApplicationHandlerStop

        try:
            app_user = access.find_app_user(self.fetch_json("GET", config.API_URL + "/users/"), sender.id)
        except Exception as e:
            logger.error(f"Could not check user {sender.id}: {e}")
            await self._refuse(update, msgs.api_error)
            raise ApplicationHandlerStop
        if app_user is None:
            logger.warning(f"Refused telegram id {sender.id} in chat {chat.id}: not registered in the app")
            forbidden = msgs.forbidden if chat.type == access.PRIVATE else msgs.forbidden_in_group
            await self._refuse(update, forbidden)
            raise ApplicationHandlerStop
        if not app_user["is_active"]:
            await self._refuse(update, msgs.inactive)
            raise ApplicationHandlerStop
        context.user_data["app_user"] = app_user

    async def _refuse(self, update: Update, text: str) -> None:
        """Tell the sender why (a pressed button just gets its spinner stopped)."""
        try:
            if update.callback_query:
                await update.callback_query.answer()
            elif update.message:
                await update.message.reply_text(text)
        except Exception as e:
            logger.error(f"Could not answer a refused update: {e}")

    async def reply_message(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, msg
    ) -> None:
        await update.message.reply_text(
            msg,
            disable_notification=True,
            disable_web_page_preview=None,
            parse_mode=telegram.constants.ParseMode.MARKDOWN,
        )
        return ConversationHandler.END

    async def response_conversation(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, msg
    ):
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(
            msg, parse_mode=telegram.constants.ParseMode.MARKDOWN
        )
        return ConversationHandler.END

    async def activate(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Link the sender's Telegram id to the app account with their username (the bot's only write).

        Only reached from the app's group: the gate lets /activate through nowhere else.
        """
        sender = update.message.from_user
        users = self.fetch_json("GET", config.API_URL + "/users/")
        outcome, account = access.plan_activation(users, sender.id, sender.username)
        if outcome == access.ACTIVATE_OK:
            self.fetch_json("PATCH", f"{config.API_URL}/manage/users/{account['id']}", json={"telegram_id": sender.id})
            logger.info(f"Linked telegram id {sender.id} to {account['username']}")
            text = msgs.activated.format(name=account.get("name") or account["username"])
        else:
            text = {
                access.ACTIVATE_ALREADY: msgs.already_activated,
                access.ACTIVATE_NO_USERNAME: msgs.activate_no_username,
                access.ACTIVATE_NO_ACCOUNT: msgs.activate_no_account,
                access.ACTIVATE_INACTIVE: msgs.inactive,
                access.ACTIVATE_TAKEN: msgs.activate_taken,
            }[outcome]
        await update.message.reply_text(text)

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        in_group = update.message.chat.type != access.PRIVATE
        await update.message.reply_text(msgs.start(update.message.from_user.first_name, in_group))

    def load_json_response(self, response):
        return json.loads(json.dumps(response))