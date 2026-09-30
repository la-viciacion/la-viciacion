"""Every endpoint must be protected, and the open ones are a fixed, reviewed list.

Adding a route that is reachable without a login, or a per-user route that never
checks the caller owns the data, fails here. Adding a new public endpoint means
adding it to PUBLIC on purpose (and documenting why in docs/architecture.md).
"""
import ast
import inspect
import unittest

from fastapi.routing import APIRoute

from src.routers import basic, games, manage, statistics, timers, users, utils

ROUTER_MODULES = (basic, games, manage, statistics, timers, users, utils)

# (method, path relative to the router): reachable without a token
PUBLIC = {
    ("GET", "/"),
    ("GET", "/keepalive"),
    ("POST", "/token"),  # login; throttled
    ("POST", "/signup"),  # needs the invitation key; throttled
    ("GET", "/utils/achievement-image/{achievement}"),  # loaded by <img>, which cannot send a token
}

# Path parameters that identify whose data is touched, plus the routes that carry the owner in the body
OWNER_PARAMS = {"username", "user_id", "timer_id"}
OWNER_IN_BODY = {("POST", "/timers/start"), ("POST", "/timers/manual")}
OWNER_CHECKS = ("ensure_self_or_admin", "ensure_self(", "require_admin", "is_admin")


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

    def test_the_admin_panel_api_is_admin_only(self):
        for module, route, method in routes():
            if module is manage:
                self.assertIn("require_admin", dependency_names(route.dependant), f"{method} {route.path}")

    def test_user_scoped_endpoints_check_the_owner(self):
        for module, route, method in routes():
            if module is manage or (method, route.path) in PUBLIC:
                continue
            scoped = OWNER_PARAMS & {p.name for p in route.dependant.path_params} or (method, route.path) in OWNER_IN_BODY
            if not scoped:
                continue
            if "require_admin" in dependency_names(route.dependant):
                continue
            source = called_source(module, route.endpoint)
            self.assertTrue(
                any(check in source for check in OWNER_CHECKS),
                f"{method} {route.path} handles a user's data but never checks the caller is that user or an admin",
            )

    def test_no_interactive_docs_route_is_registered_by_the_routers(self):
        paths = {route.path for _, route, _ in routes()}
        self.assertFalse({"/docs", "/redoc", "/openapi.json"} & paths)


if __name__ == "__main__":
    unittest.main()
