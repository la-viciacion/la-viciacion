"""Dev and prod share one host and a container name is global to it, so every container the main compose file names must be
named differently by the dev override. The monitoring services were once left out, and starting the second stack failed with
"the container name is already in use"."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def container_names(path: Path) -> dict[str, str]:
    """service -> container_name, read from the two-space service headers and four-space `container_name:` lines."""
    names, service = {}, None
    for line in path.read_text(encoding="utf-8").splitlines():
        header = re.match(r"^  ([a-z][\w-]*):\s*$", line)
        if header:
            service = header.group(1)
        named = re.match(r"^    container_name:\s*(\S+)", line)
        if named and service:
            names[service] = named.group(1)
    return names


class DevStackNamesTests(unittest.TestCase):
    main = container_names(ROOT / "docker-compose.yml")
    dev = container_names(ROOT / "docker-compose.dev.yml")

    def test_the_main_file_names_the_containers_it_runs(self):
        self.assertGreaterEqual(len(self.main), 6)  # front, bot, api, db and the two of the monitoring profile
        self.assertIn("laviciacion-node-exporter", self.main)

    def test_every_container_of_the_main_file_is_named_again_by_the_dev_override(self):
        missing = sorted(service for service in self.main if service not in self.dev)
        self.assertEqual(missing, [], "services whose container keeps the production name in the dev stack")

    def test_no_dev_name_is_a_production_one(self):
        clashes = {service: name for service, name in self.dev.items() if name in self.main.values()}
        self.assertEqual(clashes, {})


if __name__ == "__main__":
    unittest.main()
