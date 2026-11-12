"""How many questions the guide may be asked. Apart from the chat's: a question here searches the web, which costs the
project's quota several times what a chat question does (the admin sets the numbers, 0 = no limit)."""
from ..utils import settings
from ..utils.rate_limit import Scope, UsageLimiter

USER_LIMITS = (("guide.limit_user_hour", 3600), ("guide.limit_user_day", 86400))
GROUP_LIMITS = (("guide.limit_group_day", 86400),)
GROUP_KEY = "guide-group"

limiter = UsageLimiter()


def scopes_of(user_id: int) -> list[Scope]:
    def limits(table):
        return tuple((window, settings.get(key)) for key, window in table)

    return [Scope(f"guide:{user_id}", "user", limits(USER_LIMITS)), Scope(GROUP_KEY, "group", limits(GROUP_LIMITS))]
