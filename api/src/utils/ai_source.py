"""Whose key pays for a question to the chat or the guide: the player's own or the group's.

Each feature has a mode (admin setting `chat.key_source`, `guide.key_source`):

  user_only       only with the player's own key (nothing is asked of the group's quota)
  group_then_user the group's key first; the player's own, if they saved one, when the group's cannot pay: before the call, because
                  its monthly budget is spent (the group's or the player's share of it), and after it, because the provider says the
                  group's quota or balance is gone or refuses its key (utils/ai_fallback.py); if they have none they are told so
  group_only      always the group's, whatever the players have saved (for the day the group agrees to pay for everybody)

The answer is a `Decision`: a `Source` and, behind it, the sources to go on with if its key fails. A `Source` is whose key it is (`key_source`, written to the usage record), the provider, the key and the model.
The player's own is one of the keys they saved, one per provider (utils/user_ai.py), with the model they chose for it: the provider
they prefer, else the one the group uses for that feature if they have a key there, else the first they have. It can only be opened
with the data key of their session (utils/ai_vault.py): a session without it is **locked** (`Decision.locked`) and the player is asked
for their password. The group's is the provider in use and its key (utils/ai_providers.py) with the chat's model. `None` means
nobody can pay for it now."""
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from . import ai_budget, ai_ledger, ai_providers, messages, settings, user_ai

USER_ONLY, GROUP_THEN_USER, GROUP_ONLY = "user_only", "group_then_user", "group_only"
MODES = (USER_ONLY, GROUP_THEN_USER, GROUP_ONLY)
FEATURES = ("chat", "guide")
MAX_OWN_KEYS = 2  # how many of the player's own keys a question may try: with the group's, at most three calls


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


def group_source(feature: str = "chat") -> Source | None:
    """The group's key for a feature, if the .env has a provider, a key and a model for it."""
    found = ai_providers.group_credentials(feature)
    return Source(ai_ledger.GROUP, *found) if found else None


def own_sources(db: Session, user_id: int, dek: bytes | None, use: str | None = None) -> list[Source]:
    """The player's own keys that can pay for `use` (a feature, or None for the first they have), best first, at most `MAX_OWN_KEYS`:
    empty if they have none or this session cannot open them. The order is their preference, the group's provider for `use`, the rest;
    a key that does not open is left out."""
    held = user_ai.providers_with_key(db, user_id)
    order = []
    for provider in (user_ai.preferred(db, user_id), ai_providers.selected(use) if use else None, *held):
        if provider in held and provider not in order:
            order.append(provider)
    found = []
    for provider in order:
        credentials = user_ai.credentials(db, user_id, dek, provider)
        if credentials:
            found.append(Source(ai_ledger.USER, provider, credentials[0], credentials[1]))
    return found[:MAX_OWN_KEYS]


def _locked(db: Session, user_id: int, dek: bytes | None) -> bool:
    """The player has keys that this session cannot open because it carries no data key."""
    return dek is None and bool(user_ai.providers_with_key(db, user_id))


@dataclass(frozen=True)
class Decision:
    source: Source | None
    # ai_budget.USER: the player has spent their monthly share of the group's key; ai_budget.USER_OFF: it is 0 (an admin gave them
    # nothing of it); ai_budget.WALLET: the player's wallet balance is spent. With no source it is what stopped the
    # question; with the player's own as the source it is why the group's was not used (they went on with theirs)
    blocked: str | None = None
    # the player has keys of their own but this session cannot open them (it carries no data key): the front asks for their password
    locked: bool = False
    # the keys to go on with if `source` fails because its own quota or balance is gone or the provider refuses it (utils/ai_fallback.py):
    # the player's own ones, only where the mode lets them pay after the group's (and, with the player's own as the source, the others)
    fallback: tuple[Source, ...] = ()
    # the group's key is the source and the player has keys that this session cannot open: if it fails they are told to unlock them
    fallback_locked: bool = False

    @property
    def sources(self) -> tuple[Source, ...]:
        """Every key that may pay for the question, in the order they are tried."""
        return (self.source, *self.fallback) if self.source is not None else ()


def decide(db: Session, user_id: int, feature: str, dek: bytes | None = None) -> Decision:
    """The source that pays for this player's next question to `feature`, or why none can: the feature is off, the mode wants
    a key they have not saved, the group's is missing (all three: no source and nothing blocked) or the group's key is the one
    to use and the player's monthly share of it, or their wallet balance, is spent (`blocked`). With `group_then_user` the group's
    key comes first and the player's own takes over when that is spent (or the group has none) and, through `fallback`, when the
    provider refuses it during the question."""
    if not settings.get(f"{feature}.enabled"):
        return Decision(None)
    wanted = mode(feature)
    if wanted == USER_ONLY:
        own = own_sources(db, user_id, dek, feature)
        return Decision(own[0] if own else None, locked=not own and _locked(db, user_id, dek), fallback=tuple(own[1:]))
    group = group_source(feature)
    blocked = ai_budget.exceeded(db, user_id) if group is not None else None
    if group is not None and not blocked:
        if wanted == GROUP_ONLY:
            return Decision(group)
        own = own_sources(db, user_id, dek, feature)
        return Decision(group, fallback=tuple(own), fallback_locked=not own and _locked(db, user_id, dek))
    if wanted == GROUP_ONLY:
        return Decision(None, blocked)
    own = own_sources(db, user_id, dek, feature)  # the group's is spent (or missing): the player's own, if they have one
    return Decision(own[0] if own else None, blocked, locked=not own and _locked(db, user_id, dek), fallback=tuple(own[1:]))


def resolve(db: Session, user_id: int, feature: str, dek: bytes | None = None) -> Source | None:
    """The source that pays for this player's next question to `feature`, or None if none can (see `decide`)."""
    return decide(db, user_id, feature, dek).source


def way_out(feature: str, locked: bool = False) -> str:
    """What follows a refusal of the group's key to tell the player how to go on with their own, if the mode lets them: that they can
    save one, or that the ones they have are locked in this session. Nothing where the group's key is the only one that counts."""
    if mode(feature) == GROUP_ONLY:
        return ""
    return messages.OWN_KEY_LOCKED if locked else messages.OWN_KEY_WAY_OUT


def blocked_message(blocked: str, feature: str, locked: bool = False) -> str:
    """What a player is told when their cap or balance stops the group's key: whose it was and, where their own key would be used, the way out."""
    base = {
        ai_budget.USER_OFF: messages.USER_AI_OFF, ai_budget.WALLET: messages.WALLET_EMPTY,
    }.get(blocked, messages.USER_BUDGET_REACHED)
    return base + way_out(feature, locked)


def state_of(feature: str, decision: Decision) -> dict:
    """What a decision means for the front (see `availability`), so a route that already decided does not decide again."""
    if not settings.get(f"{feature}.enabled"):
        return {"available": False, "needs_key": False, "paid_by": None, "blocked": None, "locked": False}
    source = decision.source
    paid_by = source.key_source if source else None
    if mode(feature) == GROUP_ONLY:
        return {"available": source is not None or decision.blocked is not None, "needs_key": False, "paid_by": paid_by, "blocked": decision.blocked, "locked": False}
    return {"available": True, "needs_key": source is None and not decision.locked, "paid_by": paid_by, "blocked": decision.blocked, "locked": decision.locked}


def availability(db: Session, user_id: int, feature: str, dek: bytes | None = None) -> dict:
    """For the front: `available` (the feature is on and somebody could pay for it) and `needs_key` (the player has to
    save their own key to use it: the group does not cover it). `paid_by` is who would pay now, `blocked` which budget of the
    group's key is spent, if that is what stops it."""
    return state_of(feature, decide(db, user_id, feature, dek))
