"""Boots the real application and asks it what it serves. Run by tests/test_mariadb_app_boot.py in a
subprocess, against a migrated database: importing src.main seeds the admin user, the settings and the
achievements, exactly as `uvicorn src.main:app` does when the API container starts.

Prints one line, `PROBE:` followed by JSON: the status every declared route answers to a request with
no credentials, the status of the places the interactive docs would be, and the paths of the schema.
"""
import json

from fastapi.testclient import TestClient

import src.main as main
from tests.app_routes import BASE, declared_routes, requestable

client = TestClient(main.app, raise_server_exceptions=False)
status = {f"{method} {path}": client.request(method, requestable(path)).status_code for method, path in declared_routes()}
docs = {path: client.get(path).status_code for path in (f"{BASE}/docs", f"{BASE}/redoc", f"{BASE}/openapi.json", "/docs", "/redoc", "/openapi.json")}
schema = sorted(f"{method.upper()} {path}" for path, item in main.app.openapi()["paths"].items() for method in item)
print("PROBE:" + json.dumps({"status": status, "docs": docs, "schema": schema}))
