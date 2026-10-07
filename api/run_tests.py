"""Runs the API tests in parallel, one process per test module (or test class, for the slow ones), longest first.

    python run_tests.py                 # every module, with the MariaDB ones if TEST_MARIADB_URL is set
    python run_tests.py --db            # the same, starting (or reusing) a MariaDB made for tests (needs Docker)
    python run_tests.py --no-db         # only the modules that need no MariaDB
    python run_tests.py --db --skip-migrations   # without the ones that run every migration (when none changed)
    python run_tests.py achievements    # only the modules whose name has "achievements"
    python run_tests.py -j 12 --db      # twelve processes at once

`unittest discover` runs everything in one process, one test after another. The MariaDB tests spend their time
waiting for the server and for the alembic command (every class creates and drops its own database, and several run
the real migrations, a second and a half to start each one), so the modules can run side by side against the same
server: they never touch each other's data. A module that takes more than a minute is split by test class, which has
a database of its own too. The slowest jobs start first (their times are kept in `.test_timings.json` after each
run, not in git), so the whole run lasts about as long as the slowest job. CI keeps running `unittest discover`;
this is only for the machine of whoever is developing.

`--db` uses a container made for tests: its data lives in memory (`--tmpfs`) and it does not wait for the disk
(`flush_log_at_trx_commit=0`, no doublewrite, no binary log). That is fine for a database that is thrown away and
would never be for one with real data: it is not the one of `docker-compose.yml`.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

API_DIR = Path(__file__).resolve().parent
TESTS_DIR = API_DIR / "tests"
TIMINGS = API_DIR / ".test_timings.json"
CONTAINER = "lavi-test-db"
PORT = 3399
PASSWORD = "testpw"
# the version docker-compose.yml pins is what CI runs against: this one has to follow it
IMAGE = "mariadb:12.3.3"
DB_URL = f"mysql+pymysql://root:{PASSWORD}@127.0.0.1:{PORT}"
# a job nobody has timed yet is assumed to be this slow (seconds), so it does not start last by accident
UNKNOWN_SECONDS = 60.0
# a module that takes longer than this is run by test class, in parallel
SPLIT_SECONDS = 60.0

# What a subprocess runs to list the test classes of a module (a job is `test_module` or `test_module.Class`)
LIST_CLASSES = """
import sys, unittest

def flat(suite):
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from flat(test)
        else:
            yield test

for name in sorted({type(t).__module__ + '.' + type(t).__qualname__ for t in flat(unittest.defaultTestLoader.loadTestsFromName(sys.argv[1]))}):
    print(name)
"""


# the modules that run the migrations one by one on a real MariaDB: the slowest by far, and only about migrations
MIGRATION_MODULES = ("test_mariadb_migration", "test_mariadb_v1_upgrade")


def modules(pattern: str | None = None, with_db: bool = True, with_migrations: bool = True) -> list[str]:
    """The test modules, by name (`test_foo`), optionally the ones whose name has `pattern`, without the MariaDB ones
    and without the ones that run every migration."""
    names = sorted(path.stem for path in TESTS_DIR.glob("test_*.py"))
    if not with_db:
        names = [name for name in names if not name.startswith("test_mariadb_")]
    if not with_migrations:
        names = [name for name in names if not name.startswith(MIGRATION_MODULES)]
    if pattern:
        names = [name for name in names if pattern in name]
    return names


def order(jobs: list[str], timings: dict[str, float]) -> list[str]:
    """The slowest first: with several workers that is what makes the whole run end soonest."""
    return sorted(jobs, key=lambda job: (-timings.get(job, UNKNOWN_SECONDS), job))


def weight(name: str, timings: dict[str, float]) -> float | None:
    """How long a module took the last time (the sum of its classes if it was split), None if it was never timed."""
    if name in timings:
        return timings[name]
    parts = [seconds for job, seconds in timings.items() if job.startswith(name + ".")]
    return sum(parts) if parts else None


def classes_of(name: str, env: dict) -> list[str]:
    """The jobs of a module split by class (`test_module.Class`): what the unittest loader finds in it, so a class
    that is not found here would not have been run by `unittest discover` either. The module itself if it cannot be told."""
    result = subprocess.run(
        [sys.executable, "-c", LIST_CLASSES, f"tests.{name}"], cwd=API_DIR, env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    found = [line.strip().removeprefix("tests.") for line in result.stdout.splitlines() if line.strip().startswith(f"tests.{name}.")]
    return found or [name]


def jobs_for(names: list[str], timings: dict[str, float], env: dict) -> list[str]:
    """What to run: each module as one job, except the slow ones, which are one job per test class."""
    jobs = []
    for name in names:
        seconds = weight(name, timings)
        jobs.extend(classes_of(name, env) if seconds is not None and seconds > SPLIT_SECONDS else [name])
    return jobs


def summary_of(output: str) -> tuple[int, bool]:
    """(how many tests ran, whether the job passed) out of what `python -m unittest` printed."""
    ran = re.search(r"^Ran (\d+) tests?", output, re.MULTILINE)
    return (int(ran.group(1)) if ran else 0), bool(re.search(r"^OK\b", output, re.MULTILINE))


def start_database() -> str:
    """Starts the container for tests (or reuses it) and waits for it; returns the URL of the server."""
    if shutil.which("docker") is None:
        sys.exit("--db needs Docker; or set TEST_MARIADB_URL to a MariaDB you can throw data away from")
    running = subprocess.run(["docker", "ps", "-q", "-f", f"name=^{CONTAINER}$"], capture_output=True, text=True).stdout.strip()
    if not running:
        subprocess.run(["docker", "rm", "-f", CONTAINER], capture_output=True)
        started = subprocess.run(
            ["docker", "run", "-d", "--name", CONTAINER, "-e", f"MARIADB_ROOT_PASSWORD={PASSWORD}",
             "-p", f"127.0.0.1:{PORT}:3306", "--tmpfs", "/var/lib/mysql:rw", IMAGE,
             "--innodb-flush-log-at-trx-commit=0", "--innodb-doublewrite=0", "--skip-log-bin", "--sync-binlog=0",
             "--innodb-flush-method=fsync", "--max-connections=500"],
            capture_output=True, text=True,
        )
        if started.returncode != 0:
            sys.exit("could not start the database: " + started.stderr.strip())
    for _ in range(60):
        ready = subprocess.run(
            ["docker", "exec", CONTAINER, "mariadb", "-uroot", f"-p{PASSWORD}", "-e", "SELECT 1"], capture_output=True
        )
        if ready.returncode == 0:
            return DB_URL
        time.sleep(1)
    sys.exit("the database did not come up in a minute")


def run_job(job: str, env: dict) -> dict:
    began = time.monotonic()
    result = subprocess.run(
        [sys.executable, "-m", "unittest", f"tests.{job}"], cwd=API_DIR, env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    output = result.stdout + result.stderr
    ran, passed = summary_of(output)
    return {"name": job, "seconds": time.monotonic() - began, "ran": ran, "passed": passed and result.returncode == 0, "output": output}


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(errors="replace")  # a failure may print text that the console of Windows cannot encode
    parser = argparse.ArgumentParser(description="Runs the API tests in parallel, one process per module (or class).")
    parser.add_argument("pattern", nargs="?", help="only the modules whose name has this text")
    parser.add_argument("-j", "--jobs", type=int, default=min(os.cpu_count() or 4, 8), help="processes at once (default: the CPUs, at most 8)")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--db", action="store_true", help="start (or reuse) a MariaDB made for tests with Docker")
    group.add_argument("--no-db", action="store_true", help="skip the modules that need a MariaDB")
    parser.add_argument("--skip-migrations", action="store_true", help="skip the modules that run every migration on MariaDB (fine when no migration or model changed; CI runs them anyway)")
    args = parser.parse_args(argv)

    env = {**os.environ, "PYTHONPATH": str(API_DIR)}
    if args.db:
        env["TEST_MARIADB_URL"] = start_database()
    with_db = not args.no_db and bool(env.get("TEST_MARIADB_URL"))
    if env.get("TEST_MARIADB_URL"):
        env["REQUIRE_MARIADB_TESTS"] = "1"
    if not args.no_db and not with_db:
        print("TEST_MARIADB_URL is not set: the MariaDB modules are left out (use --db to start one)")

    names = modules(args.pattern, with_db, not args.skip_migrations)
    if not names:
        sys.exit("no test module matches")
    try:
        timings = {key: float(value) for key, value in json.loads(TIMINGS.read_text()).items()}
    except (OSError, ValueError, AttributeError):
        timings = {}

    began = time.monotonic()
    results = []
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        for result in pool.map(lambda job: run_job(job, env), order(jobs_for(names, timings, env), timings)):
            results.append(result)
            print(f"{'ok  ' if result['passed'] else 'FAIL'} {result['name']:<62} {result['ran']:>4} tests {result['seconds']:>6.1f}s", flush=True)

    for name in names:  # a module that was split no longer has a time of its own, and one that is whole has no classes
        split = any(result["name"].startswith(name + ".") for result in results)
        timings = {job: seconds for job, seconds in timings.items() if not (job == name and split) and not (job.startswith(name + ".") and not split)}
    timings.update({result["name"]: round(result["seconds"], 1) for result in results})
    try:
        TIMINGS.write_text(json.dumps(timings, indent=1, sort_keys=True))
    except OSError:
        pass
    failed = [result for result in results if not result["passed"]]
    for result in failed:
        lines = [line for line in result["output"].splitlines() if " | INFO | " not in line and " | WARNING | " not in line]
        print(f"\n===== {result['name']} =====\n" + "\n".join(lines)[-6000:])
    total = sum(result["ran"] for result in results)
    print(f"\n{total} tests in {len(results)} jobs, {time.monotonic() - began:.0f}s: " + (f"{len(failed)} job(s) FAILED" if failed else "all passed"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
