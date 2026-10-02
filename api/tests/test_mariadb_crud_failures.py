"""When the database refuses a write, the data layer must undo it and say so (MariaDB required, see
api_support.py): a failed commit leaves the stored data as it was, the session is usable afterwards, and the
error reaches the caller instead of being swallowed. Reads that fail propagate too. Duplicate-key races, which the
code deliberately tolerates in two places, are checked separately."""
import datetime
from unittest import mock

from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError

from src.crud import games as games_crud
from src.crud import users as users_crud
from src.database import database, models, schemas
from tests.api_support import ApiTestCase


class FailureTestCase(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.ana = self.user("ana", email="ana@example.com", telegram_id=111)
        self.game("celeste", "Celeste")
        self.entry = self.library_entry(self.ana, "celeste", datetime.date.today(), "pc")

    def session(self):
        return database.SessionLocal()

    def failing_commit(self, db, error=None):
        return mock.patch.object(db, "commit", side_effect=error or OperationalError("UPDATE", {}, Exception("server has gone away")))


class WritesAreUndoneTests(FailureTestCase):
    def assert_undone_and_raised(self, action, check_unchanged):
        with self.session() as db:
            with self.failing_commit(db), self.assertRaises(SQLAlchemyError):
                action(db)
            check_unchanged()
            db.query(models.User).count()  # the session still works: the failed transaction was rolled back

    def test_a_failed_profile_update_changes_nothing(self):
        def action(db):
            user = db.get(models.User, self.ana)
            users_crud.update_profile(db, user, {"name": "Changed", "telegram_id": 999})
        self.assert_undone_and_raised(action, lambda: self.assertEqual(
            tuple(self.rows("SELECT name, telegram_id FROM users WHERE id = :i", i=self.ana)[0]), ("Ana", 111)))

    def test_a_failed_password_change_keeps_the_old_password(self):
        before = self.scalar("SELECT password FROM users WHERE id = :i", i=self.ana)
        self.assert_undone_and_raised(
            lambda db: users_crud.change_password(db, db.get(models.User, self.ana), "An0ther-secret!pw"),
            lambda: self.assertEqual(self.scalar("SELECT password FROM users WHERE id = :i", i=self.ana), before))

    def test_a_failed_avatar_upload_stores_nothing(self):
        self.assert_undone_and_raised(
            lambda db: users_crud.upload_avatar(db, "ana", b"\x89PNG"),
            lambda: self.assertIsNone(self.scalar("SELECT avatar FROM users WHERE id = :i", i=self.ana)))

    def test_a_failed_completion_leaves_the_entry_pending(self):
        self.assert_undone_and_raised(
            lambda db: users_crud.complete_entry(db, db.get(models.UserGame, self.entry), datetime.date.today()),
            lambda: self.assertEqual(self.scalar("SELECT COALESCE(completed, 0) FROM users_games WHERE id = :i", i=self.entry), 0))

    def test_a_failed_undo_and_a_failed_date_change_leave_a_completion_as_it_was(self):
        with self.session() as db:
            users_crud.complete_entry(db, db.get(models.UserGame, self.entry), datetime.date(datetime.date.today().year, 1, 2))
        for action in (lambda db: users_crud.uncomplete_entry(db, db.get(models.UserGame, self.entry)),
                       lambda db: users_crud.set_completed_date(db, db.get(models.UserGame, self.entry), datetime.date.today())):
            with self.subTest(action=action):
                self.assert_undone_and_raised(action, lambda: self.assertEqual(
                    tuple(self.rows("SELECT completed, completed_date FROM users_games WHERE id = :i", i=self.entry)[0]),
                    (1, datetime.date(datetime.date.today().year, 1, 2))))

    def test_a_failed_account_creation_leaves_no_account(self):
        def action(db):
            users_crud.insert_user(db, username="new", email="new@example.com", name="New", password="Sup3r-secret!pw",
                                   is_admin=False, is_active=True, telegram_id=None)
        self.assert_undone_and_raised(action, lambda: self.assertEqual(self.scalar("SELECT COUNT(*) FROM users WHERE username = 'new'"), 0))

    def test_a_duplicate_account_is_reported_as_an_integrity_error_for_the_route_to_turn_into_a_409(self):
        with self.session() as db:
            with self.assertRaises(IntegrityError):
                users_crud.insert_user(db, username="ana", email="other@example.com", name="X", password="Sup3r-secret!pw",
                                       is_admin=False, is_active=True, telegram_id=None)

    def test_a_failed_library_entry_is_undone_and_raised(self):
        with self.session() as db:
            user = db.get(models.User, self.ana)
            with self.failing_commit(db), self.assertRaises(SQLAlchemyError):
                users_crud.add_new_game(db, schemas.NewGameUser(game_id="celeste", platform="switch"), user)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM users_games WHERE user_id = :u", u=self.ana), 1)

    def test_a_duplicate_library_entry_is_tolerated_not_raised(self):
        with self.session() as db:
            user = db.get(models.User, self.ana)
            same_season = datetime.datetime.now()
            duplicate = IntegrityError("INSERT", {}, Exception("Duplicate entry 'x' for key 'uq_users_games_entry'"))
            with self.failing_commit(db, duplicate):
                users_crud.add_new_game(db, schemas.NewGameUser(game_id="celeste", platform="pc"), user, start_date=same_season.strftime("%Y-%m-%d"))
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM users_games WHERE user_id = :u", u=self.ana), 1)

    def test_a_game_for_a_vanished_catalogue_entry_is_ignored(self):
        with self.session() as db:
            self.assertIsNone(users_crud.add_new_game(db, schemas.NewGameUser(game_id="nope"), db.get(models.User, self.ana)))


class GameCatalogueFailureTests(FailureTestCase):
    def new_game(self, name="Hades"):
        return schemas.NewGame(name=name, dev="Supergiant", genres="Roguelike", avg_time=3600, slug="hades", rawg_id=None)

    def test_a_failed_insert_is_undone_and_raised(self):
        with self.session() as db:
            with self.failing_commit(db), self.assertRaises(OperationalError):
                games_crud._store_game(db, self.new_game(), self.new_game())
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM games WHERE name = 'Hades'"), 0)

    def test_a_race_that_inserted_the_same_game_returns_the_existing_one(self):
        duplicate = IntegrityError("INSERT", {}, Exception("Duplicate entry 'Celeste' for key 'name'"))
        with self.session() as db:
            with self.failing_commit(db, duplicate):
                stored = games_crud._store_game(db, self.new_game("Celeste"), self.new_game("Celeste"))
            self.assertEqual(stored.id, "celeste")

    def test_a_failed_average_time_update_is_raised(self):
        with self.session() as db:
            with self.failing_commit(db), self.assertRaises(OperationalError):
                games_crud.update_avg_time_game(db, "celeste", 7200)


class ReadsPropagateTests(FailureTestCase):
    def test_a_failing_read_reaches_the_caller(self):
        reads = {
            "get_users": lambda db: users_crud.get_users(db),
            "get_user_by_username": lambda db: users_crud.get_user_by_username(db, "ana"),
            "get_user_by_id": lambda db: users_crud.get_user_by_id(db, self.ana),
            "get_avatar": lambda db: users_crud.get_avatar(db, "ana"),
            "count_played_games": lambda db: users_crud.count_played_games(db, self.ana),
            "count_completed_games": lambda db: users_crud.count_completed_games(db, self.ana),
        }
        for name, read in reads.items():
            with self.subTest(read=name), self.session() as db:
                with mock.patch.object(db, "query", side_effect=OperationalError("SELECT", {}, Exception("gone"))), self.assertRaises(SQLAlchemyError):
                    read(db)


class EmergencyAccountTests(FailureTestCase):
    def test_an_empty_emergency_password_stops_the_start(self):
        with mock.patch.object(users_crud.config, "GOD_ADMIN_PASS", ""), self.session() as db:
            with self.assertRaisesRegex(ValueError, "GOD_ADMIN_PASS"):
                users_crud.ensure_god_user(db)

    def test_the_emergency_account_is_created_restored_and_kept_out_of_the_player_lists(self):
        with self.session() as db:
            users_crud.ensure_god_user(db)
            god = db.query(models.User).filter_by(username="admin").one()
            self.assertEqual((god.is_admin, god.is_active), (1, 1))
            god.password, god.is_admin, god.is_active = "tampered", 0, 0
            db.commit()
            users_crud.ensure_god_user(db)  # every start restores access
            db.refresh(god)
            self.assertEqual((god.is_admin, god.is_active), (1, 1))
            self.assertNotEqual(god.password, "tampered")
            self.assertNotIn("admin", [u.username for u in users_crud.get_users(db)])
            self.assertEqual(self.scalar("SELECT COUNT(*) FROM users WHERE username = 'admin'"), 1)  # not duplicated
