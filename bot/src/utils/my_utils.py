import asyncio
import time
from collections import OrderedDict

import utils.access as access
import utils.messages as msgs
from telegram import Update
from telegram.ext import ApplicationHandlerStop, ContextTypes, ConversationHandler
from utils.config import Config
from utils.logger import LogManager

log_manager = LogManager()
logger = log_manager.get_logger()

config = Config()

# The gate needs the accounts for every update: they are asked for at most once in this many seconds. A Telegram id
# an admin links in the panel works after it at the latest; /activate forgets them at once.
USERS_TTL_SECONDS = 60

# The group's menus whose owner is remembered (the oldest are forgotten): a button is only for who opened its menu.
MENUS_KEPT = 500

# The API waits for the AI (up to 30 s) to write a welcome: a little more, so its answer is not cut off.
WELCOME_TIMEOUT_SECONDS = 40


class ApiError(Exception):
    """The API did not give a usable answer."""

    def __init__(self, status_code: int, detail: str = ""):
        super().__init__(f"API error {status_code}{': ' + detail if detail else ''}")
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
        self._users = None
        self._users_at = 0.0

    def make_request(self, method, url, json=None, timeout=None):
        return config.request(method, url, json=json, **({"timeout": timeout} if timeout else {}))

    async def fetch_json(self, method, url, json=None, timeout=None):
        """Request the API and return the parsed body; raise ApiError if it did not answer 200 with JSON.
        `timeout` (seconds) is only for what is slower than a query, like the text the AI writes.

        It does not log: the one report is the traceback the error handler writes, so a failure is not counted twice.

        The request runs in a thread: `requests` blocks, and one event loop serves every chat of the bot."""
        response = await asyncio.to_thread(self.make_request, method, url, json=json, **({"timeout": timeout} if timeout else {}))
        if response.status_code != 200:
            raise ApiError(response.status_code, f"{method} {url}: {response.text[:200]}")
        try:
            return response.json()
        except ValueError:
            raise ApiError(response.status_code, f"non-JSON body to {method} {url}: {response.text[:200]}")

    async def app_users(self) -> list[dict]:
        """The accounts of the app (GET /users/), asked again once they are USERS_TTL_SECONDS old."""
        now = time.monotonic()
        if self._users is None or now - self._users_at > USERS_TTL_SECONDS:
            self._users = await self.fetch_json("GET", config.API_URL + "/users/")
            self._users_at = now
        return self._users

    def forget_users(self) -> None:
        self._users = None

    def remember_menu(self, context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int, owner_id: int) -> None:
        """Note who opened the menu in this message. The conversation is per chat and user, not per message, so
        without this a second player with a menu of their own could drive somebody else's message.
        It lives in `bot_data`, the application's own shared data."""
        owners = context.bot_data.setdefault("menu_owners", OrderedDict())
        owners[(chat_id, message_id)] = owner_id
        owners.move_to_end((chat_id, message_id))
        while len(owners) > MENUS_KEPT:
            owners.popitem(last=False)

    def menu_belongs_to(self, context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int | None, user_id: int) -> bool:
        return context.bot_data.get("menu_owners", {}).get((chat_id, message_id)) == user_id

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
            if message.new_chat_members:
                return  # somebody joined the group: welcomed whether or not they are linked (the sender may be who added them)
            raise ApplicationHandlerStop  # group chatter is none of our business
        if chat.type != access.PRIVATE and update.callback_query:
            # in the group only who opened a menu may press its buttons (a menu from before a restart is nobody's)
            message_id = getattr(update.callback_query.message, "message_id", None)
            if not self.menu_belongs_to(context, chat.id, message_id, sender.id):
                await self._refuse_button(update)
                raise ApplicationHandlerStop
        if command in ("activate", "start"):
            # for people not linked yet, and only inside the app's group
            if chat.type != access.PRIVATE:
                return
            if command == "activate":
                raise ApplicationHandlerStop

        try:
            app_user = access.find_app_user(await self.app_users(), sender.id)
        except Exception as e:
            logger.error(f"Could not check user {sender.id}: {e}", exc_info=True)
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

    async def _refuse_button(self, update: Update) -> None:
        """A popup for whoever pressed; the message stays as it is."""
        try:
            await update.callback_query.answer(msgs.not_your_menu, show_alert=True)
        except Exception as e:  # e.g. Telegram refuses to answer a very old query
            logger.warning(f"Could not answer a button that is not theirs: {e}")

    async def _refuse(self, update: Update, text: str) -> None:
        """Tell the sender why (a pressed button just gets its spinner stopped)."""
        try:
            if update.callback_query:
                await update.callback_query.answer()
            elif update.message:
                await update.message.reply_text(text)
        except Exception as e:
            logger.error(f"Could not answer a refused update: {e}", exc_info=True)

    async def response_conversation(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, msg
    ):
        query = update.callback_query
        await query.answer()
        # plain text on purpose: nothing here is formatted, and Telegram's Markdown refuses a name with an
        # unbalanced _ or * (a game, a player) and drops the whole answer
        await query.edit_message_text(msg)
        return ConversationHandler.END

    async def activate(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Link the sender's Telegram id to the app account with their username (the bot's only write).

        Only reached from the app's group: the gate lets /activate through nowhere else.
        """
        sender = update.message.from_user
        # never the remembered accounts: whether the id or the account is already taken must be read now
        users = await self.fetch_json("GET", config.API_URL + "/users/")
        outcome, account = access.plan_activation(users, sender.id, sender.username)
        if outcome == access.ACTIVATE_OK:
            await self.fetch_json("PATCH", f"{config.API_URL}/manage/users/{account['id']}", json={"telegram_id": sender.id})
            self.forget_users()  # the gate lets them in from their next message
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

    async def welcome(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Greet whoever joined the group and tell them to /activate. The text is the AI's (written by the API);
        the bot's own when the AI is off or the API does not answer: a welcome must always go out.

        Only reached from the app's group: the gate refuses a join anywhere else."""
        for member in update.message.new_chat_members:
            if member.is_bot:
                continue
            name = (member.first_name or "").strip()[:64] or "jugador"
            try:
                reply = await self.fetch_json(
                    "POST",
                    config.API_URL + "/manage/welcome-message",
                    json={"name": name, "username": member.username},
                    timeout=WELCOME_TIMEOUT_SECONDS,
                )
                text = reply.get("message")
            except Exception as e:
                logger.error(f"Could not get the AI's welcome for {member.id}: {e}", exc_info=True)
                text = None
            await update.message.reply_text(text or msgs.welcome(name, member.username))

    async def poll_answer(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Tell the API what someone chose in one of the group's polls (the bot's second write, with /activate).

        The API keeps it only for a poll it launched and has not closed. Someone who is not in the app is kept as a bare
        Telegram id, so no account is needed to vote."""
        answer = update.poll_answer
        if answer.user is None or answer.user.is_bot:
            return  # voted as a chat (an anonymous admin): there is no person to count
        try:
            await self.fetch_json(
                "PUT",
                config.API_URL + "/manage/polls/answers",
                json={"poll_id": answer.poll_id, "user_id": answer.user.id, "option_ids": list(answer.option_ids)},
            )
        except Exception as e:  # the vote is lost for the app; the poll in Telegram still shows it
            logger.error(f"Could not report the answer of {answer.user.id} to poll {answer.poll_id}: {e}", exc_info=True)

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        in_group = update.message.chat.type != access.PRIVATE
        await update.message.reply_text(msgs.start(update.message.from_user.first_name, in_group))


# The one instance of the bot: it keeps state (the accounts the gate remembers), so two of them would mean a module
# writing where the gate never looks.
utils = MyUtils()
