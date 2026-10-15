"""Every module of the API can be imported on its own, in a fresh interpreter.

crud/ and utils/ import each other (utils.actions runs the checks of crud.achievements, which notifies through
utils.my_utils...). A cycle only works in the order the app happens to import things; imported first by a test
or a script, a module that is part of one fails with "partially initialized module". This finds it the day it
is introduced instead of the day somebody imports the module from elsewhere.
"""
import os
import subprocess
import sys
import unittest
from pathlib import Path

API = Path(__file__).resolve().parent.parent
SKIPPED = {"src.main"}  # it opens the database at import: what it imports is checked one by one anyway

# Run in one fresh interpreter: before each module every `src` module is forgotten, so each one is imported as if
# it were the first (the libraries stay loaded: they are not what can form a cycle, and reloading them is slow).
CHECK = """
import importlib, sys
failures = []
for name in sys.argv[1:]:
    for loaded in [m for m in sys.modules if m == "src" or m.startswith("src.")]:
        del sys.modules[loaded]
    try:
        importlib.import_module(name)
    except Exception as e:
        failures.append(f"{name}: {type(e).__name__}: {e}")
print("\\n".join(failures))
"""


def modules() -> list[str]:
    found = []
    for path in sorted((API / "src").rglob("*.py")):
        parts = path.relative_to(API).with_suffix("").parts
        name = ".".join(parts[:-1] if parts[-1] == "__init__" else parts)
        if name not in SKIPPED:
            found.append(name)
    return found


class ImportCycleTests(unittest.TestCase):
    def test_every_module_imports_on_its_own(self):
        done = subprocess.run(
            [sys.executable, "-c", CHECK, *modules()], cwd=API, env=os.environ.copy(), capture_output=True, text=True
        )
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.strip(), "")


if __name__ == "__main__":
    unittest.main()
