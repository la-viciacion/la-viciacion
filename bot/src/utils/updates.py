"""How the bot takes its updates: several at a time, but each user's one at a time and in order."""
import asyncio

from telegram import Update
from telegram.ext import SimpleUpdateProcessor

MAX_CONCURRENT_UPDATES = 8


class PerUserUpdateProcessor(SimpleUpdateProcessor):
    """Updates of different users are processed at the same time, so a slow answer from the API for one chat does
    not stall every other; the updates of one user keep being processed one by one, in the order they came.

    That order is what the menu conversation relies on (the library warns that concurrent updates and a
    ConversationHandler do not mix): two quick taps on a button must not both edit the same message.
    The cap is shared, so a user who floods the bot can fill the slots, but only with their own updates."""

    def __init__(self, max_concurrent_updates: int = MAX_CONCURRENT_UPDATES):
        super().__init__(max_concurrent_updates)
        self._locks: dict[int, list] = {}  # user id -> [lock, how many updates hold or wait for it]

    async def do_process_update(self, update: object, coroutine) -> None:
        user = update.effective_user if isinstance(update, Update) else None
        if user is None:
            await coroutine
            return
        entry = self._locks.setdefault(user.id, [asyncio.Lock(), 0])
        entry[1] += 1
        try:
            async with entry[0]:
                await coroutine
        finally:
            entry[1] -= 1
            if not entry[1]:
                del self._locks[user.id]  # nobody waits: the registry does not grow with the users
