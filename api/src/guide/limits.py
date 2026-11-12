"""How many questions the guide may be asked. Apart from the chat's: a question here searches the web, which costs the
project's quota several times what a chat question does (the admin sets the numbers, 0 = no limit)."""
from ..utils import settings
from ..utils.rate_limit import Scope, UsageLimiter

USER_LIMITS = (("guide.limit_user_hour", 3600), ("guide.limit_user_day", 86400))
GROUP_LIMITS = (("guide.limit_group_day", 86400),)
GROUP_KEY = "guide-group"

limiter = UsageLimiter()


def scopes_of(user_id: int, own_key: bool = False) -> list[Scope]:
    """The player's limits and the group's. A question paid with the player's own key spends nobody else's quota: only the
    chat's per-minute limit stays, against a runaway loop."""
    def limits(table):
        return tuple((window, settings.get(key)) for key, window in table)

    if own_key:
        return [Scope(f"guide:{user_id}", "user", ((60, settings.get("chat.limit_user_minute")),))]
    return [Scope(f"guide:{user_id}", "user", limits(USER_LIMITS)), Scope(GROUP_KEY, "group", limits(GROUP_LIMITS))]
