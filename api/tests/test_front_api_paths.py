"""Every call the front makes to the API must match a route that exists, with that method.

The front is vanilla JS with no build step and no types, so a route renamed or a method changed on the API side
would only show up as an error in somebody's browser. This reads the front's source for `api('/...')` calls
(template literals included, `${...}` standing for a path parameter or a query string) and checks each
(method, path) against the routes the routers declare. No database or server needed.
"""
import re
import unittest
from pathlib import Path

from tests.app_routes import BASE, declared_routes

FRONT = Path(__file__).resolve().parents[2] / "front" / "js"
CALL = re.compile(r"\bapi\(\s*(?=[`'\"])")
EXPRESSION = "\x00"  # stands for a ${...} in a template literal


def skip_expression(source: str, i: int) -> int:
    """`i` points at `${`: the index just after its closing brace."""
    level, i = 1, i + 2
    while i < len(source) and level:
        level += {"{": 1, "}": -1}.get(source[i], 0)
        i += 1
    return i


def read_literal(source: str, i: int):
    """The string or template literal that starts at `i`: (its text with expressions as EXPRESSION, index after it)."""
    quote, i, text = source[i], i + 1, []
    while i < len(source) and source[i] != quote:
        if source[i] == "\\":
            text.append(source[i + 1])
            i += 2
        elif quote == "`" and source.startswith("${", i):
            text.append(EXPRESSION)
            i = skip_expression(source, i)
        else:
            text.append(source[i])
            i += 1
    return "".join(text), i + 1


def call_arguments(source: str, start: int) -> str:
    """The text of the call whose first argument starts at `start`, up to its closing parenthesis."""
    depth, i = 1, start
    while i < len(source) and depth:
        char = source[i]
        if char in "`'\"":
            _, i = read_literal(source, i)
            continue
        depth += {"(": 1, ")": -1}.get(char, 0)
        i += 1
    return source[start:i - 1]


def normalise(path: str) -> str:
    path = path.split("?", 1)[0]
    path = re.sub(rf"(?<=[A-Za-z0-9_-]){EXPRESSION}$", "", path)  # `/manage/users${query}`: a query string, not a segment
    return path.replace(EXPRESSION, "{param}")


def front_calls():
    """(file, method, normalised path) for every api(...) call whose path is a literal."""
    found = []
    for file in sorted(FRONT.rglob("*.js")):
        source = file.read_text(encoding="utf-8")
        for match in CALL.finditer(source):
            path, _ = read_literal(source, match.end())
            arguments = call_arguments(source, match.end())
            method = re.search(r"jsonRequest\(\s*['\"](\w+)['\"]", arguments) or re.search(r"method:\s*['\"](\w+)['\"]", arguments)
            found.append((file.relative_to(FRONT.parent).as_posix(), (method.group(1) if method else "GET").upper(), normalise(path)))
    return found


def route_pattern(path: str) -> re.Pattern:
    return re.compile("^" + re.sub(r"\\\{[^}]+\\\}", "[^/]+", re.escape(path)) + "$")


class FrontCallsMatchTheApiTests(unittest.TestCase):
    def test_the_scanner_reads_literals_expressions_and_methods(self):
        source = "x = api(`/users/${encodeURIComponent(name)}/library?limit=${n}`, { method: 'PATCH' });\ny = api('/utils/platforms');"
        match = list(CALL.finditer(source))
        self.assertEqual(len(match), 2)
        path, end = read_literal(source, match[0].end())
        self.assertEqual(normalise(path), "/users/{param}/library")
        self.assertIn("PATCH", call_arguments(source, match[0].end()))
        self.assertEqual(normalise(read_literal(source, match[1].end())[0]), "/utils/platforms")
        self.assertEqual(normalise(f"/manage/users{EXPRESSION}"), "/manage/users")  # a glued ${query} is no segment
        self.assertEqual(normalise(f"/manage/users/{EXPRESSION}"), "/manage/users/{param}")

    def test_the_scanner_finds_the_calls_of_the_front(self):
        self.assertGreater(len(front_calls()), 40, "it should find dozens of calls: did the front change shape?")

    def routes(self):
        return [(method, route_pattern(path.removeprefix(BASE))) for method, path in declared_routes()]

    def exists(self, method, path):
        candidate = path.replace("{param}", "X")
        return any(m == method and pattern.match(candidate) for m, pattern in self.routes())

    def test_every_call_goes_to_a_route_that_exists_with_that_method(self):
        missing = []
        checked = 0
        for file, method, path in front_calls():
            if path.startswith("{param}"):
                continue  # the base path is in a variable: checked below, where it is declared
            checked += 1
            if not self.exists(method, path):
                missing.append(f"{file}: {method} {path}")
        self.assertGreater(checked, 40)
        self.assertEqual(missing, [], "front calls with no route behind them:\n" + "\n".join(missing))

    def test_every_endpoint_of_the_admin_tables_has_a_list_route_and_row_edits(self):
        entities = (FRONT / "pages" / "admin" / "entities.js").read_text(encoding="utf-8")
        endpoints = re.findall(r"endpoint:\s*'([^']+)'", entities)
        self.assertGreaterEqual(len(endpoints), 7)
        # a table marked `readOnly: true` (the audit log and the challenges) is listed but has no edit button
        read_only = set(re.findall(r"endpoint:\s*'([^']+)',(?:(?!endpoint:)[\s\S])*?readOnly:\s*true", entities))
        self.assertEqual(read_only, {"/manage/audit", "/manage/challenges"})
        for endpoint in endpoints:
            with self.subTest(endpoint=endpoint):
                self.assertTrue(self.exists("GET", endpoint), "the table lists its rows with GET")
                if endpoint not in read_only:
                    self.assertTrue(self.exists("PATCH", endpoint + "/{param}"), "a row is edited with PATCH")

    def test_the_paths_the_front_builds_from_the_username_exist(self):
        for method, path in (
            ("GET", "/users/{param}/profile"), ("PATCH", "/users/{param}/profile"), ("GET", "/users/{param}/library"),
            ("PATCH", "/users/{param}/library/{param}/completion"), ("GET", "/users/{param}/recommendations"),
            ("GET", "/users/{param}/avatar"), ("PATCH", "/users/{param}/avatar"), ("GET", "/users/{param}/settings"),
            ("PATCH", "/users/{param}/settings"), ("POST", "/users/{param}/password"),
        ):
            with self.subTest(route=f"{method} {path}"):
                self.assertTrue(self.exists(method, path))
