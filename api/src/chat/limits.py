"""What the chat limits, in one place so the agent can also tell it to whoever asks: what one question may cost (the
UsageLimits of a run) and how many questions may be asked (the usage limiter, with the numbers the admin sets)."""
from pydantic_ai.usage import UsageLimits

from ..utils import settings
from ..utils.rate_limit import Scope, UsageLimiter

MAX_QUESTION = 500  # characters of a question
MAX_HISTORY = 10  # messages of the conversation the model sees: older ones are dropped

# The tokens are those of the whole run (every request of it, the thinking of a reasoning model included): a cap on the
# output alone would cut a plain question short. This one only stops a conversation that runs away.
LIMITS = UsageLimits(request_limit=10, tool_calls_limit=8, total_tokens_limit=60_000)

# Each question costs several calls to a model whose quota is the project's: the admin panel sets how many a player may ask per
# minute, hour and 24 hours, and how many the group may in all (0 = no limit), so one account, a leaked token or the whole
# group together cannot empty it. It counts the questions asked, whether the model then answered or not.
USER_LIMITS = (("chat.limit_user_minute", 60), ("chat.limit_user_hour", 3600), ("chat.limit_user_day", 86400))
GROUP_LIMITS = (("chat.limit_group_minute", 60), ("chat.limit_group_day", 86400))
GROUP_KEY = "group"
WINDOW_NAMES = {60: "minute", 3600: "hour", 86400: "day"}

limiter = UsageLimiter()


def scopes_of(user_id: int) -> list[Scope]:
    """The player's limits and then the group's, as the settings have them now."""
    def limits(table):
        return tuple((window, settings.get(key)) for key, window in table)

    return [Scope(f"user:{user_id}", "user", limits(USER_LIMITS)), Scope(GROUP_KEY, "group", limits(GROUP_LIMITS))]


def usage_of(user_id: int) -> dict:
    """How many questions each limit allows and how many are left to this player and to the group, now."""
    return {
        scope.name: {WINDOW_NAMES[row["window"]]: {k: row[k] for k in ("limit", "used", "remaining")} for row in limiter.usage(scope)}
        for scope in scopes_of(user_id)
    }
