"""Which checks a pull request needs, from the files it changes.

Reads the changed paths (one per line) on stdin and prints two lines for GITHUB_OUTPUT:

    scope=api-tests,mariadb,...     the checks to run, or `all`
    build_services=["api","bot"]    the images to build and inspect

The rule that keeps this safe: a path nobody classified runs everything. Only the paths listed in INERT run
nothing, and only a component's own paths run that component's checks. The cross-component entries below exist
because some tests read files outside their own directory (tests/test_ci_scope.py pins them).
"""
import json
import sys

ALL_CHECKS = ("api-tests", "bot-tests", "front-tests", "mariadb")
ALL_SERVICES = ("api", "front", "bot")

# Nothing in these is executed, built or read by a test.
INERT_PREFIXES = ("docs/", "design/")
INERT_FILES = {
    "README.md", "CONTRIBUTING.md", "AGENTS.md", "CLAUDE.md", "LICENSE", ".gitignore", ".gitattributes",
    ".github/pull_request_template.md", ".github/dependabot.yml", ".github/copilot-instructions.md",
}

# Checks that run when a path starts with the prefix (or equals the file).
RULES = (
    # the API: its own tests, the tests on a real MariaDB and the image
    ("api/", {"api-tests", "mariadb"}, {"api"}),
    # the bot: its tests and image; the API tests that use the bot as the real client (test_mariadb_bot_contract)
    # and the one that checks the variables it reads against .env.template
    ("bot/src/", {"bot-tests", "api-tests", "mariadb"}, {"bot"}),
    ("bot/", {"bot-tests"}, {"bot"}),
    # the front: its tests and image; the API test that checks every path the pages call has a route
    ("front/js/", {"front-tests", "api-tests"}, {"front"}),
    ("front/Dockerfile", {"front-tests", "api-tests"}, {"front"}),  # test_deployment_pins reads every Dockerfile
    ("front/", {"front-tests"}, {"front"}),
    # test_env_template and test_deployment_pins read these from the repository root
    (".env.template", {"api-tests"}, set()),
    ("docker-compose.yml", {"api-tests", "mariadb"}, set()),  # it pins the MariaDB version the tests run on
    ("docker-compose.dev.yml", {"api-tests"}, set()),
)


def scope(paths):
    checks, services = set(), set()
    for path in paths:
        path = path.strip().replace("\\", "/")
        if not path or path in INERT_FILES or path.startswith(INERT_PREFIXES):
            continue
        matched = False
        for prefix, rule_checks, rule_services in RULES:
            if path == prefix or (prefix.endswith("/") and path.startswith(prefix)):
                # the specific rules are listed first and do not stop the broader ones: bot/src/ also
                # matches bot/, which only adds what it already has
                checks |= rule_checks
                services |= rule_services
                matched = True
        if not matched:
            return set(ALL_CHECKS), set(ALL_SERVICES)  # workflows, new top-level files, anything unknown
    return checks, services


def render(checks, services):
    everything = checks == set(ALL_CHECKS) and services == set(ALL_SERVICES)
    return (
        f"scope={'all' if everything else ','.join(c for c in ALL_CHECKS if c in checks)}\n"
        f"build_services={json.dumps([s for s in ALL_SERVICES if s in services])}\n"
    )


if __name__ == "__main__":
    sys.stdout.write(render(*scope(sys.stdin.read().splitlines())))
