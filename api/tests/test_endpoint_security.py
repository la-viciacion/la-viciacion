"""Every endpoint must be protected, and the open ones are a fixed, reviewed list.

Adding a route that is reachable without a login, or a per-user route that never
checks the caller owns the data, fails here. Adding a new public endpoint means
adding it to PUBLIC on purpose (and documenting why in docs/desarrollo/architecture.md).
"""
import ast
import inspect
import unittest

from fastapi.routing import APIRoute

from src.routers import activity, basic, challenges, chat, games, group, manage, notifications, push, server, statistics, timers, users, utils

ROUTER_MODULES = (activity, basic, challenges, chat, games, group, manage, notifications, push, server, statistics, timers, users, utils)

# (method, path relative to the router): reachable without a token
PUBLIC = {
    ("GET", "/keepalive"),
    ("POST", "/token"),  # login; throttled
    ("POST", "/auth/forgot-password"),  # same answer for any account; throttled; needs mail configured
    ("POST", "/auth/reset-password"),  # needs the emailed one-time token; throttled
    ("GET", "/utils/achievement-image/{achievement}"),  # loaded by <img>, which cannot send a token
}

# Path parameters that name a resource shared by the whole group (a game, an external id, a period...): anything else a
# route takes in its path is treated as "whose data is this?" and has to be answered, so a new `{entry_id}` or
# `{poll_id}` cannot slip through just because its name is not on a list.
SHARED_PARAMS = {"game_id", "igdb_id", "rawg_id", "achievement", "period", "egg"}
# Query parameters that name a user
OWNER_QUERY_PARAMS = {"username", "user_id", "player_id"}
OWNER_IN_BODY = {("POST", "/timers/start"), ("POST", "/timers/manual")}
# A real call, not a substring: `viewer.is_admin` in a comment or an unrelated variable must not satisfy the test
OWNER_CHECKS = ("ensure_self_or_admin(", "ensure_self(", "require_admin")

# Scoped routes with no ensure_* call, each reviewed by hand: why anyone logged in may call it, or how it is scoped
REVIEWED_SCOPED = {
    ("GET", "/users/photo/{player_id}"): "avatars are shown to the whole group",
    ("GET", "/group/players/{player_id}"): "the group's public profile of a player",
    ("GET", "/group/players/{player_id}/compare"): "group data, compared with the caller",
    ("GET", "/challenges/player/{player_id}"): "a player's public challenges; private ones are filtered by the viewer",
    ("GET", "/challenges/{challenge_id}"): "_challenge() hides non-public challenges from anyone but the owner and admins",
    ("GET", "/challenges/{challenge_id}/games"): "_challenge() visibility; the list is about the caller",
    ("PUT", "/challenges/{challenge_id}/participation"): "_challenge() visibility; changes only the caller's own participation",
    ("DELETE", "/challenges/{challenge_id}"): "refuses unless owner_user_id is the caller (group ones are the admins')",
    ("DELETE", "/challenges/proposals/{proposal_id}"): "404 unless the caller is the proposer",
    ("DELETE", "/notifications/{notification_id}"): "the delete is filtered by the caller's user_id",
}


def dependency_names(dependant, found=None):
    found = set() if found is None else found
    for sub in dependant.dependencies:
        if sub.call is not None:
            found.add(getattr(sub.call, "__name__", type(sub.call).__name__))
            dependency_names(sub, found)
    return found


def routes():
    for module in ROUTER_MODULES:
        for route in module.router.routes:
            if isinstance(route, APIRoute):
                for method in route.methods:
                    yield module, route, method


def called_source(module, function) -> str:
    """Source of `function` plus every function of the same module it (transitively) calls."""
    tree = ast.parse(inspect.getsource(module))
    local = {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    seen, queue, chunks = set(), [function.__name__], []
    while queue:
        name = queue.pop()
        if name in seen or name not in local:
            continue
        seen.add(name)
        node = local[name]
        chunks.append(ast.unparse(node))
        for call in ast.walk(node):
            if isinstance(call, ast.Call):
                target = call.func
                queue.append(target.id if isinstance(target, ast.Name) else getattr(target, "attr", ""))
    return "\n".join(chunks)


class EndpointSecurityTests(unittest.TestCase):
    def test_only_the_reviewed_endpoints_are_public(self):
        open_routes = set()
        for _, route, method in routes():
            names = dependency_names(route.dependant)
            if not names & {"get_current_active_user", "get_current_user", "require_admin"}:
                open_routes.add((method, route.path))
        self.assertEqual(open_routes, PUBLIC)

    def test_the_server_panel_needs_a_logged_in_user(self):
        for module, route, method in routes():
            if module is server:
                self.assertIn("get_current_active_user", dependency_names(route.dependant), f"{method} {route.path}")

    def test_the_admin_panel_api_is_admin_only(self):
        for module, route, method in routes():
            if module is manage:
                self.assertIn("require_admin", dependency_names(route.dependant), f"{method} {route.path}")

    @staticmethod
    def scoped(route, method) -> bool:
        path_params = {p.name for p in route.dependant.path_params}
        query_params = {p.name for p in route.dependant.query_params}
        return bool(path_params - SHARED_PARAMS) or bool(query_params & OWNER_QUERY_PARAMS) or (method, route.path) in OWNER_IN_BODY

    def test_user_scoped_endpoints_check_the_owner(self):
        for module, route, method in routes():
            if module is manage or (method, route.path) in PUBLIC or (method, route.path) in REVIEWED_SCOPED:
                continue
            if not self.scoped(route, method):
                continue
            if "require_admin" in dependency_names(route.dependant):
                continue
            source = called_source(module, route.endpoint)
            self.assertTrue(
                any(check in source for check in OWNER_CHECKS),
                f"{method} {route.path} handles a user's data but never checks the caller is that user or an admin "
                "(add the check, or list the route in REVIEWED_SCOPED with the reason it is safe)",
            )

    def test_the_reviewed_list_has_no_stale_or_needless_entries(self):
        scoped = {(method, route.path): module for module, route, method in routes() if self.scoped(route, method)}
        for entry in REVIEWED_SCOPED:
            self.assertIn(entry, scoped, f"{entry} is in REVIEWED_SCOPED but no such scoped route exists any more")
        for module, route, method in routes():
            if (method, route.path) in REVIEWED_SCOPED:
                source = called_source(module, route.endpoint)
                self.assertFalse(
                    any(check in source for check in OWNER_CHECKS),
                    f"{method} {route.path} now has an owner check: drop it from REVIEWED_SCOPED",
                )

    def test_every_router_module_is_registered_in_the_app(self):
        """A router module left out of main.py is dead code; one left out of ROUTER_MODULES escapes every test above."""
        import pathlib

        names = {m.__name__.rsplit(".", 1)[-1] for m in ROUTER_MODULES if m is not manage}
        on_disk = {p.stem for p in pathlib.Path(inspect.getsourcefile(basic)).parent.glob("*.py") if p.stem != "__init__"}  # manage is a package, tested apart
        self.assertEqual(on_disk, names)

    def test_every_manage_route_comes_from_the_one_admin_router(self):
        """Routes of the admin panel must hang from manage.router; a stray APIRouter inside the package would skip require_admin."""
        import pathlib

        package = pathlib.Path(inspect.getsourcefile(manage)).parent
        for path in package.glob("*.py"):
            if path.name != "common.py":
                self.assertNotIn("APIRouter(", path.read_text(encoding="utf-8"), f"{path.name} creates its own router")

    def test_no_interactive_docs_route_is_registered_by_the_routers(self):
        paths = {route.path for _, route, _ in routes()}
        self.assertFalse({"/docs", "/redoc", "/openapi.json"} & paths)


if __name__ == "__main__":
    unittest.main()
