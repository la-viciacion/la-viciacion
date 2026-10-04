"""Export / import of a player's data, the audit log and the `.sql` backup through real requests
(MariaDB required, see api_support.py). The merge rules themselves are in test_data_export.py."""
import datetime
import re
from datetime import timedelta
from unittest import mock

from sqlalchemy import text

from src.routers import users as users_router
from tests.api_support import ApiTestCase


def ago(**delta) -> datetime.datetime:
    return datetime.datetime.now().replace(microsecond=0) - timedelta(**delta)


class DataTestCase(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.ana = self.user("ana")
        self.bea = self.user("bea")
        self.root = self.user("root", admin=True)
        self.game("celeste", "Celeste")
        self.game("hades", "Hades")
        self.session(self.ana, "celeste", ago(hours=5), 60)
        self.session(self.ana, "hades", ago(hours=3), 30)
        self.library_entry(self.ana, "celeste", datetime.date.today(), completed=0)
        self.library_entry(self.ana, "hades", datetime.date.today(), completed=0)

    def export(self, username="ana", as_user="ana"):
        return self.api("GET", f"/users/{username}/export", as_user=as_user)

    def import_file(self, data, username="ana", as_user="ana", **params):
        return self.api("POST", f"/users/{username}/import", as_user=as_user, json=data, params=params)

    def wipe(self, user_id):
        with self.engine.begin() as conn:
            for table in ("game_timers", "users_games", "game_scores", "users_wishlist"):
                conn.execute(text(f"DELETE FROM {table} WHERE user_id = :u"), {"u": user_id})


class ExportTests(DataTestCase):
    def test_it_needs_a_login_and_is_only_for_the_owner_or_an_admin(self):
        self.assertEqual(self.api("GET", "/users/ana/export").status_code, 401)
        self.assertEqual(self.export(as_user="bea").status_code, 403)
        self.assertEqual(self.export(as_user="root").status_code, 200)

    def test_it_is_a_download_with_the_players_data(self):
        response = self.export()
        self.assertEqual(response.status_code, 200)
        self.assertRegex(response.headers["content-disposition"], r'attachment; filename="laviciacion-ana-\d{4}-\d\d-\d\d\.json"')
        body = response.json()
        self.assertEqual(body["format"], "laviciacion-export")
        self.assertEqual(sorted(s["game_id"] for s in body["sessions"]), ["celeste", "hades"])
        self.assertEqual({g["id"] for g in body["games"]}, {"celeste", "hades"})
        self.assertEqual(len(body["library"]), 2)

    def test_it_holds_nothing_of_the_others(self):
        self.session(self.bea, "celeste", ago(hours=9), 20)
        self.assertEqual(len(self.export().json()["sessions"]), 2)


class ImportDisabledTests(DataTestCase):
    def test_while_it_is_switched_off_the_route_answers_404_and_writes_nothing(self):
        data = self.export().json()
        self.wipe(self.ana)
        response = self.import_file(data)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM game_timers"), 0)

    def test_it_still_needs_the_owner_or_an_admin_first(self):
        self.assertEqual(self.import_file(self.export().json(), as_user="bea").status_code, 403)


class ImportTests(DataTestCase):
    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(users_router, "IMPORT_ENABLED", True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_it_needs_a_login_and_is_only_for_the_owner_or_an_admin(self):
        self.assertEqual(self.api("POST", "/users/ana/import", json={}).status_code, 401)
        data = self.export().json()
        self.assertEqual(self.import_file(data, as_user="bea").status_code, 403)

    def test_what_was_exported_comes_back_after_losing_it(self):
        data = self.export().json()
        self.wipe(self.ana)
        report = self.import_file(data).json()
        self.assertEqual(report["sessions"], {"imported": 2, "existing": 0, "skipped": 0})
        self.assertEqual(report["library"]["imported"], 2)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM game_timers WHERE user_id = :u", u=self.ana), 2)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM users_games WHERE user_id = :u", u=self.ana), 2)
        self.assertEqual(self.export().json()["sessions"], data["sessions"])
        # earned, not imported: the check of the achievements is asked for, silently
        self.background["after_session_change"].assert_called_with(self.ana, True)

    def test_importing_again_changes_nothing(self):
        data = self.export().json()
        report = self.import_file(data).json()
        self.assertEqual(report["sessions"], {"imported": 0, "existing": 2, "skipped": 0})
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM game_timers"), 2)
        self.background["after_session_change"].assert_not_called()

    def test_a_dry_run_writes_nothing_and_asks_for_no_follow_up(self):
        data = self.export().json()
        self.wipe(self.ana)
        report = self.import_file(data, dry_run="true").json()
        self.assertTrue(report["dry_run"])
        self.assertEqual(report["sessions"]["imported"], 2)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM game_timers"), 0)
        self.background["after_session_change"].assert_not_called()

    def test_it_can_be_brought_to_another_account(self):
        data = self.export().json()
        report = self.import_file(data, username="bea", as_user="bea").json()
        self.assertEqual(report["sessions"]["imported"], 2)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM game_timers WHERE user_id = :u", u=self.bea), 2)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM game_timers WHERE user_id = :u", u=self.ana), 2)

    def test_a_file_that_is_not_an_export_is_refused(self):
        self.assertEqual(self.import_file({"format": "other", "version": 1}).status_code, 400)
        self.assertEqual(self.import_file({"format": "laviciacion-export", "version": 99}).status_code, 400)
        self.assertEqual(self.import_file({"hello": "world"}).status_code, 422)

    def test_a_malformed_row_is_refused_before_anything_is_written(self):
        data = self.export().json()
        data["scores"] = [{"game_id": "celeste", "score": 1000}]
        self.wipe(self.ana)
        self.assertEqual(self.import_file(data).status_code, 422)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM game_timers"), 0)

    def test_a_closed_season_is_for_admins(self):
        old = datetime.datetime(datetime.date.today().year - 1, 5, 1, 10)
        self.session(self.ana, "celeste", old, 60)
        data = self.export().json()
        self.wipe(self.ana)
        player = self.import_file(data).json()
        self.assertEqual((player["sessions"]["imported"], player["sessions"]["skipped"]), (2, 1))
        self.wipe(self.ana)
        admin = self.import_file(data, as_user="root").json()
        self.assertEqual((admin["sessions"]["imported"], admin["sessions"]["skipped"]), (3, 0))


class AuditTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.ana = self.user("ana")
        self.root = self.user("root", admin=True)
        self.game("celeste", "Celeste")
        self.game("hades", "Hades")
        self.timer = self.session(self.ana, "celeste", ago(hours=5), 60)

    def admin(self, method, path, **kwargs):
        return self.api(method, f"/manage{path}", as_user="root", **kwargs)

    def log(self, **params):
        return self.admin("GET", "/audit", params=params).json()

    def test_a_change_is_recorded_with_who_what_and_how_it_was(self):
        self.assertEqual(self.admin("PATCH", f"/timers/{self.timer}", json={"game_id": "hades", "notes": "wrong game"}).status_code, 200)
        (entry,) = self.log()["items"]
        self.assertEqual((entry["username"], entry["method"], entry["entity"], entry["entity_id"], entry["status"]), ("root", "PATCH", "timers", str(self.timer), 200))
        self.assertEqual(entry["detail"]["body"], {"game_id": "hades", "notes": "wrong game"})
        self.assertEqual((entry["detail"]["before"]["game_id"], entry["detail"]["before"]["notes"]), ("celeste", None))

    def test_the_game_of_the_session_and_its_library_entry_moved(self):
        self.library_entry(self.ana, "celeste", datetime.date.today(), completed=0)
        self.admin("PATCH", f"/timers/{self.timer}", json={"game_id": "hades"})
        self.assertEqual([r[0] for r in self.rows("SELECT game_id FROM users_games WHERE user_id = :u", u=self.ana)], ["hades"])
        self.assertEqual(self.scalar("SELECT game_id FROM game_timers WHERE id = :i", i=self.timer), "hades")

    def test_reads_and_refused_requests_leave_nothing(self):
        self.admin("GET", "/overview")
        self.assertEqual(self.admin("PATCH", "/timers/99999", json={"notes": "x"}).status_code, 404)
        self.assertEqual(self.log()["total"], 0)

    def test_a_creation_notes_its_id_and_a_delete_what_went(self):
        created = self.admin("POST", "/platforms", json={"name": "Plataforma de prueba"}).json()
        self.admin("DELETE", f"/platforms/{created['id']}")
        entries = self.log()["items"]  # newest first
        self.assertEqual([(e["method"], e["entity"], e["entity_id"]) for e in entries], [("DELETE", "platforms", created["id"]), ("POST", "platforms", created["id"])])
        self.assertEqual(entries[0]["detail"]["before"]["name"], "Plataforma de prueba")

    def test_passwords_and_secrets_never_reach_the_log(self):
        self.admin("POST", f"/users/{self.ana}/password", json={"password": "N3w-secret!password"})
        self.admin("PUT", "/settings", json={"values": {"ai.api_key": "sk-very-secret"}})
        everything = str(self.rows("SELECT path, detail FROM audit_log"))
        self.assertNotIn("N3w-secret!password", everything)
        self.assertNotIn("sk-very-secret", everything)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM audit_log"), 2)

    def test_a_user_and_their_hash_are_not_copied_when_they_are_deleted(self):
        self.admin("DELETE", f"/users/{self.ana}", params={"force": "true"})
        (entry,) = self.log(entity="users")["items"]
        self.assertNotIn("password", entry["detail"]["before"])
        self.assertEqual(entry["detail"]["query"], "force=true")

    def test_the_trace_of_an_admin_survives_deleting_their_account(self):
        other = self.user("other", admin=True)
        self.api("PATCH", f"/manage/timers/{self.timer}", as_user="other", json={"notes": "hi"})
        self.admin("DELETE", f"/users/{other}", params={"force": "true"})
        entries = self.log(method="PATCH")["items"]
        self.assertEqual([(e["username"], e["user_id"]) for e in entries], [("other", None)])

    def test_the_log_filters_by_admin_entity_and_method_and_pages(self):
        self.admin("PATCH", f"/timers/{self.timer}", json={"notes": "a"})
        self.admin("POST", "/platforms", json={"name": "Plataforma de prueba"})
        self.assertEqual(self.log(entity="timers")["total"], 1)
        self.assertEqual(self.log(method="POST")["total"], 1)
        self.assertEqual(self.log(user_id=self.root)["total"], 2)
        self.assertEqual(self.log(user_id=self.ana)["total"], 0)
        self.assertEqual(len(self.log(limit=1)["items"]), 1)
        self.assertEqual(self.admin("GET", "/audit", params={"method": "GET"}).status_code, 422)

    def test_a_player_cannot_read_the_log(self):
        self.assertEqual(self.api("GET", "/manage/audit", as_user="ana").status_code, 403)


class BackupTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.ana = self.user("ana")
        self.root = self.user("root", admin=True)
        self.game("celeste", "Celeste O'Brien")
        self.session(self.ana, "celeste", ago(hours=5), 60)

    def backup(self, as_user="root"):
        return self.api("POST", "/manage/backup", as_user=as_user)

    def test_only_an_admin_gets_it(self):
        self.assertEqual(self.api("POST", "/manage/backup").status_code, 401)
        self.assertEqual(self.backup(as_user="ana").status_code, 403)

    def test_it_is_an_sql_download(self):
        response = self.backup()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "application/sql")
        self.assertRegex(response.headers["content-disposition"], r'attachment; filename="laviciacion-backup-\d{4}-\d\d-\d\d\.sql"')
        self.assertTrue(response.text.startswith("-- La Viciación: database backup"))

    def test_it_has_every_table_with_its_schema_and_rows(self):
        sql = self.backup().text
        tables = [r[0] for r in self.rows("SELECT table_name FROM information_schema.tables WHERE table_schema = DATABASE() AND table_type = 'BASE TABLE'")]
        for table in tables:
            with self.subTest(table=table):
                self.assertIn(f"DROP TABLE IF EXISTS `{table}`;", sql)
                self.assertIn(f"CREATE TABLE `{table}`", sql)
        self.assertIn("INSERT INTO `users`", sql)
        self.assertIn("'Celeste O\\'Brien'", sql)  # escaped
        self.assertIn("INSERT INTO `alembic_version`", sql)  # the revision travels with the data

    def test_generated_columns_are_left_out_of_the_inserts(self):
        sql = self.backup().text
        columns = re.search(r"INSERT INTO `game_timers` \(([^)]*)\)", sql).group(1)
        self.assertNotIn("`season`", columns)
        self.assertIn("`start_time`", columns)
        self.assertRegex(sql, r"CREATE TABLE `game_timers`[^;]*`season`[^;]*GENERATED ALWAYS")

    def test_who_took_a_copy_is_in_the_audit_log(self):
        self.backup()
        self.assertEqual(self.rows("SELECT username, method, entity FROM audit_log"), [("root", "POST", "backup")])
