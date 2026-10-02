"""The MariaDB under test is the one docker-compose.yml pins (MariaDB required).

CI starts the server from the tag it reads in docker-compose.yml; this proves the server that answered
really is that version, so a service image that silently resolved to something else cannot pass. It
only runs where EXPECT_MARIADB_PIN is set (the pull request gate); the weekly run against the moving
tags tests other versions on purpose.
"""
import os
import re
import unittest

from sqlalchemy import text

from tests.mariadb_db import MariaDBTestCase
from tests.test_deployment_pins import compose_mariadb_images


@unittest.skipUnless(os.environ.get("EXPECT_MARIADB_PIN"), "only the pull request gate checks the pin")
class ServerIsThePinnedOneTests(MariaDBTestCase):
    def test_the_server_version_is_the_pinned_version(self):
        (image,) = compose_mariadb_images()
        pinned = image.split(":", 1)[1]
        with self.engine.connect() as conn:
            version = conn.execute(text("SELECT VERSION()")).scalar()
        # `12.3.3-MariaDB-ubu2404` for a pin of 12.3.3; `12.3.5-...` is also fine for a series pin of 12.3
        self.assertTrue(re.match(rf"{re.escape(pinned)}[.-]", version), f"pinned {pinned}, the server reports {version}")
