"""Waits for the MariaDB service of the job (GitLab only waits for the port) and prints the server under test."""
import os
import sys
import time

from sqlalchemy import create_engine, text

url = os.environ["TEST_MARIADB_URL"]
print("image: ", os.environ.get("MARIADB_IMAGE", "?"))

for _ in range(40):
    try:
        with create_engine(url).connect() as conn:
            print("server:", conn.execute(text("SELECT VERSION()")).scalar())
            sys.exit(0)
    except Exception:
        time.sleep(3)

print("the MariaDB service did not answer in two minutes")
sys.exit(1)
