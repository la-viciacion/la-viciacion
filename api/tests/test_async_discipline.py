"""The event loop must only run code that waits: every blocking call (database, bcrypt, image
decoding) belongs in a plain `def`, which FastAPI runs in a worker thread."""
import ast
import unittest
from pathlib import Path

ROUTERS = Path(__file__).resolve().parent.parent / "src" / "routers"

# async on purpose: they await the network (RAWG, Telegram, push) and hand their database work
# to the thread pool (run_in_threadpool) or do none
ALLOWED_ASYNC_ROUTES = {
    "games.py": {"search_rawg", "create_game"},
    "manage/notices.py": {"send_announcement", "send_telegram_announcement"},
    "manage/system.py": {"send_test_message"},
    "users.py": {"test_telegram_id"},
}


def relative(path: Path) -> str:
    """"games.py", or "manage/notices.py" for a module of the admin panel's package."""
    return path.relative_to(ROUTERS).as_posix()


def async_functions(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef):
            awaits = any(isinstance(n, ast.Await) for n in ast.walk(node))
            yield node.name, awaits


class RouterAsyncTests(unittest.TestCase):
    def test_an_async_route_always_awaits_something(self):
        # an `async def` without `await` runs its blocking code on the event loop for nothing
        for path in sorted(ROUTERS.rglob("*.py")):
            for name, awaits in async_functions(path):
                self.assertTrue(awaits, f"{relative(path)}:{name} is async but never awaits: make it a plain def")

    def test_the_async_routes_are_the_known_ones(self):
        found = {
            relative(path): {name for name, _ in async_functions(path)}
            for path in ROUTERS.rglob("*.py")
        }
        found = {file: names for file, names in found.items() if names}
        self.assertEqual(found, ALLOWED_ASYNC_ROUTES)


if __name__ == "__main__":
    unittest.main()
