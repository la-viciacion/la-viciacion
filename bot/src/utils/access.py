"""Who may use the bot (pure functions: no Telegram, no API, no config).

Two conditions, both required, both decided by ids and never by names:
- the chat is a private one or the group configured in the app;
- the sender's Telegram id is the `telegram_id` of an account of the app.
"""

PRIVATE = "private"
GROUP_TYPES = ("group", "supergroup")


def chat_allowed(chat_type: str, chat_id: int, group_id) -> bool:
    """Private chats (the sender is checked apart) and the app's group; any other group or channel is not."""
    if chat_type == PRIVATE:
        return True
    if chat_type not in GROUP_TYPES:
        return False
    try:
        return chat_id == int(group_id)
    except (TypeError, ValueError):
        return False


def find_app_user(users: list[dict], telegram_id: int) -> dict | None:
    """The account whose Telegram id is this one (None if nobody registered it)."""
    for user in users:
        if user.get("telegram_id") is not None and user["telegram_id"] == telegram_id:
            return user
    return None


def command_of(text: str | None) -> str | None:
    """'/menu@SomeBot arg' -> 'menu'; None if the text is not a command."""
    if not text or not text.startswith("/"):
        return None
    return text.split()[0][1:].split("@")[0].lower()


def addressed_to(text: str, bot_username: str | None) -> bool:
    """False for '/cmd@OtherBot': a command meant for another bot sharing the group."""
    target = text.split()[0].partition("@")[2]
    return not target or target.lower() == (bot_username or "").lower()


ACTIVATE_OK = "ok"
ACTIVATE_ALREADY = "already"  # this Telegram id is already linked to an account
ACTIVATE_NO_USERNAME = "no_username"
ACTIVATE_NO_ACCOUNT = "no_account"
ACTIVATE_INACTIVE = "inactive"
ACTIVATE_TAKEN = "taken"  # the account is linked to another Telegram id: only an admin may change that


def plan_activation(users: list[dict], telegram_id: int, username: str | None) -> tuple[str, dict | None]:
    """What /activate does for this sender: (outcome, the account to link when the outcome is ok).

    The account is the one whose app username equals the sender's Telegram @username (Telegram
    ignores case). Once linked, the id is what counts and the @username no longer matters.
    An account that already has an id is never overwritten.
    """
    if find_app_user(users, telegram_id) is not None:
        return ACTIVATE_ALREADY, None
    if not username:
        return ACTIVATE_NO_USERNAME, None
    account = next((u for u in users if (u.get("username") or "").lower() == username.lower()), None)
    if account is None:
        return ACTIVATE_NO_ACCOUNT, None
    if not account["is_active"]:
        return ACTIVATE_INACTIVE, None
    if account.get("telegram_id") is not None:
        return ACTIVATE_TAKEN, None
    return ACTIVATE_OK, account
