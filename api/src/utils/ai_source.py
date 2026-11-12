"""Whose key pays for a question to the chat or the guide: the player's own or the group's.

Each feature has a mode (admin setting `chat.key_source`, `guide.key_source`):

  user_only       only with the player's own key (nothing is asked of the group's quota)
  group_then_user the group's key first; when its monthly budget is spent (the group's or the player's share of it) the player's
                  own, if they saved one, and if not they are told so
  group_only      always the group's, whatever the players have saved (for the day the group agrees to pay for everybody)

The answer is a `Source`: whose key it is (`key_source`, written to the usage record), the provider, the key and the model.
The player's own is OpenAI's, with the model they chose; the group's is the provider in use and its key (utils/ai_providers.py)
with the chat's model. `None` means nobody can pay for it now."""
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from . import ai_budget, ai_ledger, ai_providers, messages, settings, user_ai

USER_ONLY, GROUP_THEN_USER, GROUP_ONLY = "user_only", "group_then_user", "group_only"
MODES = (USER_ONLY, GROUP_THEN_USER, GROUP_ONLY)
FEATURES = ("chat", "guide")


@dataclass(frozen=True)
class Source:
    key_source: str  # ai_ledger.GROUP or ai_ledger.USER
    provider: str
    api_key: str = field(repr=False)  # never in a log or a message
    model: str

    @property
    def own(self) -> bool:
        return self.key_source == ai_ledger.USER


def mode(feature: str) -> str:
    """The mode of a feature; a value that is not one of ours (an old name stored by an earlier version) is the feature's default."""
    wanted = settings.get(f"{feature}.key_source")
    return wanted if wanted in MODES else settings.REGISTRY[f"{feature}.key_source"].default


def group_source() -> Source | None:
    """The group's key, if the .env has a provider, a key and a model for it."""
    found = ai_providers.group_credentials(ai_providers.CHAT)
    return Source(ai_ledger.GROUP, *found) if found else None


def own_source(db: Session, user_id: int) -> Source | None:
    found = user_ai.credentials(db, user_id)
    return Source(ai_ledger.USER, user_ai.PROVIDER, found[0], found[1]) if found else None


@dataclass(frozen=True)
class Decision:
    source: Source | None
    # ai_budget.GROUP or ai_budget.USER: the monthly budget of the group's key is spent. With no source it is what stopped the
    # question; with the player's own as the source it is why the group's was not used (they went on with theirs)
    blocked: str | None = None


def decide(db: Session, user_id: int, feature: str) -> Decision:
    """The source that pays for this player's next question to `feature`, or why none can: the feature is off, the mode wants
    a key they have not saved, the group's is missing (all three: no source and nothing blocked) or the group's key is the one
    to use and its monthly budget, the group's or the player's share, is spent (`blocked`). With `group_then_user` the group's
    key comes first and the player's own takes over only when that budget is spent (or the group has none)."""
    if not settings.get(f"{feature}.enabled"):
        return Decision(None)
    wanted = mode(feature)
    if wanted == USER_ONLY:
        return Decision(own_source(db, user_id))
    group = group_source()
    blocked = ai_budget.exceeded(db, user_id) if group is not None else None
    if group is not None and not blocked:
        return Decision(group)
    if wanted == GROUP_ONLY:
        return Decision(None, blocked)
    return Decision(own_source(db, user_id), blocked)  # the group's is spent (or missing): the player's own, if they have one


def resolve(db: Session, user_id: int, feature: str) -> Source | None:
    """The source that pays for this player's next question to `feature`, or None if none can (see `decide`)."""
    return decide(db, user_id, feature).source


def blocked_message(blocked: str, feature: str) -> str:
    """What a player is told when the budget stops the group's key: whose it was and, where their own key would be used, the way out."""
    base = messages.GROUP_BUDGET_REACHED if blocked == ai_budget.GROUP else messages.USER_BUDGET_REACHED
    return base + (messages.OWN_KEY_WAY_OUT if mode(feature) != GROUP_ONLY else "")


def state_of(feature: str, decision: Decision) -> dict:
    """What a decision means for the front (see `availability`), so a route that already decided does not decide again."""
    if not settings.get(f"{feature}.enabled"):
        return {"available": False, "needs_key": False, "paid_by": None, "blocked": None}
    source = decision.source
    paid_by = source.key_source if source else None
    if mode(feature) == GROUP_ONLY:
        return {"available": source is not None or decision.blocked is not None, "needs_key": False, "paid_by": paid_by, "blocked": decision.blocked}
    return {"available": True, "needs_key": source is None, "paid_by": paid_by, "blocked": decision.blocked}


def availability(db: Session, user_id: int, feature: str) -> dict:
    """For the front: `available` (the feature is on and somebody could pay for it) and `needs_key` (the player has to
    save their own key to use it: the group does not cover it). `paid_by` is who would pay now, `blocked` which budget of the
    group's key is spent, if that is what stops it."""
    return state_of(feature, decide(db, user_id, feature))
