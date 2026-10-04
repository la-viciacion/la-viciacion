import contextlib
import datetime
import json
import unittest
from unittest import mock

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

from src import auth
from src.database import models
from src.routers import manage
from src.utils import audit
from tests.sqlite_db import make_session


class RedactTests(unittest.TestCase):
    def test_secrets_are_hidden_whatever_their_depth(self):
        got = audit.redact({"password": "hunter2", "values": {"telegram.token": "123:abc", "ai.api_key": "k", "ai.model": "x"}})
        self.assertEqual(got, {"password": "***", "values": {"telegram.token": "***", "ai.api_key": "***", "ai.model": "x"}})

    def test_a_private_key_and_a_new_password_are_secrets_too(self):
        self.assertEqual(audit.redact({"push.vapid_private": "p", "new_password": "x"}), {"push.vapid_private": "***", "new_password": "***"})

    def test_ordinary_keys_are_kept(self):
        self.assertEqual(audit.redact({"key": "first", "title": "Hola"}), {"key": "first", "title": "Hola"})

    def test_long_texts_and_lists_are_cut(self):
        got = audit.redact({"text": "x" * 500, "ids": list(range(200))})
        self.assertEqual(len(got["text"]), audit.TEXT_MAX + 1)
        self.assertEqual(len(got["ids"]), audit.LIST_MAX)


class TargetTests(unittest.TestCase):
    def test_the_entity_and_row_come_from_the_path(self):
        self.assertEqual(audit.target_of("/api/v1/manage/timers/12"), ("timers", "12"))
        self.assertEqual(audit.target_of("/api/v1/manage/users/3/password"), ("users", "3"))
        self.assertEqual(audit.target_of("/api/v1/manage/user-achievements/7"), ("user-achievements", "7"))

    def test_an_entity_without_kept_rows_has_no_id(self):
        self.assertEqual(audit.target_of("/api/v1/manage/settings"), ("settings", None))
        self.assertEqual(audit.target_of("/api/v1/manage/push/announce"), ("push", None))

    def test_a_path_outside_the_panel_has_no_target(self):
        self.assertEqual(audit.target_of("/api/v1/users/ana"), (None, None))


class DetailTests(unittest.TestCase):
    def test_nothing_to_say_is_stored_as_nothing(self):
        self.assertIsNone(audit.detail_json(None, None, ""))
        self.assertIsNone(audit.detail_json({}, None, ""))

    def test_it_keeps_what_was_sent_what_there_was_and_the_query(self):
        got = json.loads(audit.detail_json({"password": "x", "name": "Ana"}, {"id": 1}, "force=true"))
        self.assertEqual(got, {"before": {"id": 1}, "body": {"password": "***", "name": "Ana"}, "query": "force=true"})

    def test_an_oversized_detail_is_cut_but_stays_valid_json(self):
        body = {f"k{i}": "y" * 250 for i in range(200)}
        got = json.loads(audit.detail_json(body, None, ""))
        self.assertIn("truncated", got)


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        self.db.add(models.User(id=1, username="ana", name="Ana", email="a@x.es", password="HASH", avatar=b"\x89PNG", is_admin=0, is_active=1))
        self.db.add(models.Game(id="g", name="Doom"))
        self.db.add(models.GameTimer(
            id=3, user_id=1, game_id="g", platform="pc", start_time=datetime.datetime(2026, 3, 1, 10),
            end_time=datetime.datetime(2026, 3, 1, 11), duration_seconds=3600, is_active=False,
        ))
        self.db.commit()

    def test_a_user_is_kept_without_the_hash_or_the_picture(self):
        got = audit.snapshot(self.db, "users", "1")
        self.assertEqual(got["username"], "ana")
        self.assertNotIn("password", got)
        self.assertNotIn("avatar", got)

    def test_dates_are_written_as_text(self):
        got = audit.snapshot(self.db, "timers", "3")
        self.assertEqual((got["game_id"], got["start_time"], got["season"]), ("g", "2026-03-01T10:00:00", 2026))
        json.dumps(got)

    def test_a_text_id_is_looked_up_as_it_is(self):
        self.assertEqual(audit.snapshot(self.db, "games", "g")["name"], "Doom")

    def test_unknown_rows_entities_and_ids_give_nothing(self):
        self.assertIsNone(audit.snapshot(self.db, "timers", "99"))
        self.assertIsNone(audit.snapshot(self.db, "timers", "abc"))
        self.assertIsNone(audit.snapshot(self.db, "settings", None))
        self.assertIsNone(audit.snapshot(self.db, "timers", None))


class RecordingTests(unittest.TestCase):
    """The router class and its dependency, on a small app with the same wiring as /manage."""

    def setUp(self):
        self.db = make_session(threads=True)
        self.db.add(models.GameTimer(
            id=3, user_id=1, game_id="g", start_time=datetime.datetime(2026, 3, 1, 10), end_time=datetime.datetime(2026, 3, 1, 11),
            duration_seconds=3600, is_active=False,
        ))
        self.db.commit()
        self.admin = models.User(id=9, username="root", is_admin=1, is_active=1)

        router = APIRouter(prefix="/manage", dependencies=[Depends(auth.require_admin), Depends(audit.remember)], route_class=audit.AuditedRoute)

        @router.get("/timers/{timer_id}")
        def read(timer_id: int):
            return {"id": timer_id}

        @router.post("/timers", status_code=201)
        def create(body: dict):
            return {"id": 41}

        @router.patch("/timers/{timer_id}")
        def edit(timer_id: int, body: dict):
            if body.get("fail"):
                raise HTTPException(status_code=409, detail="no")
            return {"id": timer_id}

        @router.delete("/timers/{timer_id}")
        def remove(timer_id: int, force: bool = False):
            return {"message": "ok"}

        @router.put("/settings")
        def put_settings(body: dict):
            return {}

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[auth.require_admin] = lambda: self.admin
        self.client = TestClient(app)
        patcher = mock.patch.object(audit, "SessionLocal", lambda: contextlib.nullcontext(self.db))
        patcher.start()
        self.addCleanup(patcher.stop)

    def rows(self):
        return [audit.entry_out(r) for r in self.db.query(models.AuditLog).order_by(models.AuditLog.id)]

    def test_a_read_leaves_no_trace(self):
        self.assertEqual(self.client.get("/manage/timers/3").status_code, 200)
        self.assertEqual(self.rows(), [])

    def test_an_edit_records_who_what_and_how_it_was(self):
        self.assertEqual(self.client.patch("/manage/timers/3", json={"notes": "fixed"}).status_code, 200)
        (row,) = self.rows()
        self.assertEqual((row["user_id"], row["username"], row["method"], row["path"]), (9, "root", "PATCH", "/manage/timers/3"))
        self.assertEqual((row["entity"], row["entity_id"], row["status"]), ("timers", "3", 200))
        self.assertEqual(row["detail"]["body"], {"notes": "fixed"})
        self.assertEqual(row["detail"]["before"]["duration_seconds"], 3600)

    def test_a_creation_records_the_id_it_got(self):
        self.client.post("/manage/timers", json={"game_id": "g"})
        (row,) = self.rows()
        self.assertEqual((row["method"], row["entity"], row["entity_id"], row["status"]), ("POST", "timers", "41", 201))
        self.assertNotIn("before", row["detail"])

    def test_a_delete_keeps_the_row_that_went_and_the_query(self):
        self.client.delete("/manage/timers/3?force=true")
        (row,) = self.rows()
        self.assertEqual(row["detail"]["before"]["game_id"], "g")
        self.assertEqual(row["detail"]["query"], "force=true")

    def test_a_refused_request_changed_nothing_so_it_is_not_recorded(self):
        self.assertEqual(self.client.patch("/manage/timers/3", json={"fail": True}).status_code, 409)
        self.assertEqual(self.client.patch("/manage/timers/3", json="not an object").status_code, 422)
        self.assertEqual(self.rows(), [])

    def test_secrets_never_reach_the_log(self):
        self.client.put("/manage/settings", json={"values": {"telegram.token": "123:secret", "weekly.time": "09:00"}})
        (row,) = self.rows()
        self.assertEqual(row["detail"]["body"], {"values": {"telegram.token": "***", "weekly.time": "09:00"}})
        self.assertNotIn("123:secret", json.dumps(row, default=str))

    def test_a_failure_writing_the_log_does_not_fail_the_request(self):
        with mock.patch.object(audit, "SessionLocal", side_effect=RuntimeError("db down")):
            self.assertEqual(self.client.patch("/manage/timers/3", json={"notes": "x"}).status_code, 200)

    def test_a_caller_who_is_not_an_admin_leaves_nothing_behind(self):
        def refuse():
            raise HTTPException(status_code=403, detail="no")

        self.client.app.dependency_overrides[auth.require_admin] = refuse
        self.assertEqual(self.client.patch("/manage/timers/3", json={"notes": "x"}).status_code, 403)
        self.assertEqual(self.rows(), [])


class EveryWriteOfThePanelIsAuditedTests(unittest.TestCase):
    def test_the_manage_router_uses_the_audited_route_and_its_dependency(self):
        self.assertIs(manage.router.route_class, audit.AuditedRoute)
        self.assertIn(audit.remember, [d.dependency for d in manage.router.dependencies])
        for route in manage.router.routes:
            self.assertIsInstance(route, audit.AuditedRoute, route.path)

    def test_the_log_is_listed_for_admins_only(self):
        paths = {(m, r.path) for r in manage.router.routes for m in r.methods}
        self.assertIn(("GET", "/manage/audit"), paths)


if __name__ == "__main__":
    unittest.main()
