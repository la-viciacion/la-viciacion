import datetime
import types
import unittest
from unittest import mock

import bcrypt
from fastapi import BackgroundTasks, HTTPException

from src import auth
from src.database import models
from src.routers import basic
from src.utils import email, messages as msg, password_reset
from src.utils.rate_limit import AttemptLimiter
from tests.sqlite_db import make_session

OLD = "OldPassw0rd!xyz"
NEW = "NewPassw0rd!xyz"


def hashed(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=4)).decode()


def add_user(db, id=1, username="ana", email_address="ana@x.es", active=1, name="Ana"):
    user = models.User(id=id, name=name, username=username, email=email_address, is_active=active, password=hashed(OLD))
    db.add(user)
    db.commit()
    return user


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


class TokenLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        self.user = add_user(self.db)
        patcher = mock.patch.object(password_reset.users, "hash_password", lambda p: hashed(p))
        patcher.start()
        self.addCleanup(patcher.stop)

    def reset(self, token, password=NEW):
        return password_reset.reset_password(self.db, token, password)

    def test_only_the_hash_of_the_token_is_stored(self):
        token = password_reset.create_token(self.db, self.user)
        row = self.db.query(models.PasswordReset).one()
        self.assertNotIn(token, row.token_hash)
        self.assertEqual(row.token_hash, password_reset.hash_token(token))
        self.assertGreaterEqual(len(token), 40)  # 256 random bits

    def test_a_valid_token_changes_the_password_once(self):
        token = password_reset.create_token(self.db, self.user)
        self.assertTrue(self.reset(token))
        self.db.refresh(self.user)
        self.assertTrue(bcrypt.checkpw(NEW.encode(), self.user.password.encode()))
        self.assertFalse(self.reset(token, "AnotherPassw0rd!x"))  # spent
        self.assertTrue(bcrypt.checkpw(NEW.encode(), self.user.password.encode()))

    def test_changing_the_password_signs_out_the_old_sessions(self):
        before = auth.password_fingerprint(self.user)
        self.reset(password_reset.create_token(self.db, self.user))
        self.db.refresh(self.user)
        self.assertNotEqual(auth.password_fingerprint(self.user), before)

    def test_an_unknown_token_is_refused(self):
        password_reset.create_token(self.db, self.user)
        self.assertFalse(self.reset("not-a-token"))

    def test_an_expired_token_is_refused_and_changes_nothing(self):
        token = password_reset.create_token(self.db, self.user)
        self.db.query(models.PasswordReset).update({"expires_at": utc_now() - datetime.timedelta(seconds=1)})
        self.db.commit()
        old = self.user.password
        self.assertFalse(self.reset(token))
        self.db.refresh(self.user)
        self.assertEqual(self.user.password, old)

    def test_a_new_link_cancels_the_previous_one(self):
        first = password_reset.create_token(self.db, self.user)
        second = password_reset.create_token(self.db, self.user)
        self.assertFalse(self.reset(first))
        self.assertTrue(self.reset(second))

    def test_using_a_link_removes_the_other_unused_ones_of_that_user(self):
        token = password_reset.create_token(self.db, self.user)
        now = utc_now()
        self.db.add(models.PasswordReset(user_id=1, token_hash="x" * 64, created_at=now, expires_at=now + datetime.timedelta(hours=1)))
        self.db.commit()
        self.reset(token)
        self.assertEqual(self.db.query(models.PasswordReset).count(), 1)

    def test_a_disabled_account_cannot_reset(self):
        token = password_reset.create_token(self.db, self.user)
        self.user.is_active = 0
        self.db.commit()
        self.assertFalse(self.reset(token))

    def test_links_of_other_users_are_untouched(self):
        other = add_user(self.db, id=2, username="bob", email_address="bob@x.es")
        bob_token = password_reset.create_token(self.db, other)
        password_reset.create_token(self.db, self.user)
        self.assertTrue(self.reset(bob_token))
        self.db.refresh(self.user)
        self.assertTrue(bcrypt.checkpw(OLD.encode(), self.user.password.encode()))

    def test_old_spent_rows_are_tidied_up(self):
        self.db.add(models.PasswordReset(user_id=1, token_hash="o" * 64, created_at=datetime.datetime(2020, 1, 1), expires_at=datetime.datetime(2020, 1, 1, 1)))
        self.db.commit()
        password_reset.create_token(self.db, self.user)
        self.assertEqual(self.db.query(models.PasswordReset).filter_by(token_hash="o" * 64).count(), 0)


class MessageTests(unittest.TestCase):
    def test_the_email_carries_the_link_and_escapes_the_name(self):
        with mock.patch.object(password_reset.config, "PUBLIC_URL", "https://lavi.example"):
            link = password_reset.recovery_link("TOK")
        self.assertEqual(link, "https://lavi.example/#/reset-password?token=TOK")
        subject, text, body = password_reset.recovery_message("<b>Ana</b>", link)
        self.assertIn(link, text)
        self.assertIn(f'href="{link}"', body)
        self.assertNotIn("<b>Ana</b>", body)
        self.assertIn("60 minutos", text)
        self.assertIn("ignora este correo", text)


def configure(test, **overrides):
    values = {
        "SMTP_HOST": "smtp.x", "SMTP_PORT": 587, "SMTP_EMAIL": "no-reply@x.es", "SMTP_USER": "user",
        "SMTP_PASS": "pw", "SMTP_SECURITY": "starttls", "PUBLIC_URL": "https://x.es", **overrides,
    }
    for key, value in values.items():
        patcher = mock.patch.object(email.config, key, value)
        patcher.start()
        test.addCleanup(patcher.stop)


class SendEmailTests(unittest.TestCase):
    def test_starttls_then_login_then_send(self):
        configure(self)
        with mock.patch.object(email.smtplib, "SMTP") as smtp:
            email.send_email("ana@x.es", "Hola", "texto", "<p>html</p>")
        server = smtp.return_value
        smtp.assert_called_once_with("smtp.x", 587, timeout=email.SMTP_TIMEOUT_SECONDS)
        self.assertEqual([c[0] for c in server.method_calls], ["starttls", "login", "send_message"])
        server.login.assert_called_once_with("user", "pw")
        sent = server.send_message.call_args.args[0]
        self.assertEqual((sent["To"], sent["Subject"]), ("ana@x.es", "Hola"))
        self.assertTrue(sent.is_multipart())

    def test_ssl_mode_does_not_use_starttls(self):
        configure(self, SMTP_SECURITY="ssl", SMTP_PORT=465)
        with mock.patch.object(email.smtplib, "SMTP_SSL") as smtp_ssl:
            email.send_email("ana@x.es", "Hola", "texto")
        server = smtp_ssl.return_value
        self.assertNotIn("starttls", [c[0] for c in server.method_calls])
        self.assertEqual(smtp_ssl.call_args.args, ("smtp.x", 465))

    def test_none_sends_without_encryption_for_a_local_mail_catcher(self):
        configure(self, SMTP_SECURITY="none", SMTP_PORT=1025, SMTP_PASS="")
        with mock.patch.object(email.smtplib, "SMTP") as smtp:
            email.send_email("ana@x.es", "Hola", "texto")
        self.assertEqual([c[0] for c in smtp.return_value.method_calls], ["send_message"])

    def test_no_password_means_no_login(self):
        configure(self, SMTP_PASS="")
        with mock.patch.object(email.smtplib, "SMTP") as smtp:
            email.send_email("ana@x.es", "Hola", "texto")
        smtp.return_value.login.assert_not_called()

    def test_a_plain_text_message_has_no_html_part(self):
        configure(self)
        self.assertFalse(email.build_message("ana@x.es", "s", "texto").is_multipart())

    def test_failures_are_raised_not_swallowed(self):
        configure(self)
        with mock.patch.object(email.smtplib, "SMTP", side_effect=OSError("down")):
            with self.assertRaises(OSError):
                email.send_email("ana@x.es", "Hola", "texto")

    def test_without_configuration_nothing_is_attempted(self):
        configure(self, SMTP_HOST="")
        with mock.patch.object(email.smtplib, "SMTP") as smtp:
            with self.assertRaises(email.EmailNotConfigured):
                email.send_email("ana@x.es", "Hola", "texto")
        smtp.assert_not_called()

    def test_the_background_task_never_raises_and_never_logs_the_token(self):
        with mock.patch.object(password_reset.email, "send_email", side_effect=RuntimeError("smtp down")), \
                mock.patch.object(password_reset.logger, "error") as error:
            password_reset.send_recovery_email("ana@x.es", "Ana", "SECRET-TOKEN")
        self.assertNotIn("SECRET-TOKEN", error.call_args.args[0])


class EndpointTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        add_user(self.db)
        add_user(self.db, id=2, username="nomail", email_address=None)
        add_user(self.db, id=3, username="off", email_address="off@x.es", active=0)
        for name in ("RECOVERY_BY_ACCOUNT", "RECOVERY_BY_CLIENT", "RESET_LINK_FAILS"):
            old = getattr(basic, name)
            patcher = mock.patch.object(basic, name, AttemptLimiter(old.max_failures, old.window))
            patcher.start()
            self.addCleanup(patcher.stop)
        self.enable_mail(True)
        self.sent = []
        sender = mock.patch.object(password_reset, "send_recovery_email", lambda *a: self.sent.append(a))
        sender.start()
        self.addCleanup(sender.stop)
        hasher = mock.patch.object(password_reset.users, "hash_password", lambda p: hashed(p))
        hasher.start()
        self.addCleanup(hasher.stop)

    def enable_mail(self, value):
        patcher = mock.patch.object(type(basic.config), "MAIL_ENABLED", new_callable=mock.PropertyMock, return_value=value)
        patcher.start()
        self.addCleanup(patcher.stop)

    def forgot(self, login, host="83.1.1.1"):
        tasks = BackgroundTasks()
        request = types.SimpleNamespace(client=types.SimpleNamespace(host=host))
        result = basic.forgot_password(request, basic.ForgotPasswordBody(login=login), tasks, self.db)
        for task in tasks.tasks:
            task.func(*task.args, **task.kwargs)
        return result

    def reset(self, token, password=NEW, host="83.1.1.1"):
        request = types.SimpleNamespace(client=types.SimpleNamespace(host=host))
        return basic.reset_password(request, basic.ResetPasswordBody(token=token, new_password=password), self.db)

    def test_without_mail_configured_it_says_so(self):
        self.enable_mail(False)
        with self.assertRaises(HTTPException) as ctx:
            self.forgot("ana")
        self.assertEqual(ctx.exception.status_code, 503)
        self.assertEqual(self.sent, [])

    def test_a_known_user_gets_the_email_at_the_stored_address(self):
        self.assertEqual(self.forgot("ana")["message"], msg.RECOVERY_REQUESTED)
        self.assertEqual(len(self.sent), 1)
        to, name, token = self.sent[0]
        self.assertEqual((to, name), ("ana@x.es", "Ana"))
        self.assertEqual(self.db.query(models.PasswordReset).filter_by(token_hash=password_reset.hash_token(token)).count(), 1)

    def test_the_login_can_be_the_email(self):
        self.forgot("ANA@x.es")
        self.assertEqual(self.sent[0][0], "ana@x.es")

    def test_every_other_case_looks_exactly_the_same_and_sends_nothing(self):
        answers = [self.forgot(login) for login in ("ana", "nobody", "nomail", "off", "nobody@x.es")]
        self.assertEqual(len({a["message"] for a in answers}), 1)
        self.assertEqual(len(self.sent), 1)  # only ana

    def test_an_account_gets_three_links_an_hour(self):
        for _ in range(5):
            self.forgot("ana")
        self.assertEqual(len(self.sent), 3)

    def test_a_client_is_limited_with_a_429_but_not_an_unknown_one(self):
        for _ in range(20):
            self.forgot("nobody")
        with self.assertRaises(HTTPException) as ctx:
            self.forgot("nobody")
        self.assertEqual(ctx.exception.status_code, 429)
        for _ in range(25):  # behind the proxy the address is private: there is no per-client bucket to share
            self.forgot("nobody", host="172.18.0.3")

    def test_the_whole_flow_changes_the_password(self):
        self.forgot("ana")
        token = self.sent[0][2]
        self.assertEqual(self.reset(token)["message"], msg.PASSWORD_RESET_DONE)
        user = self.db.get(models.User, 1)
        self.assertTrue(bcrypt.checkpw(NEW.encode(), user.password.encode()))
        with self.assertRaises(HTTPException) as ctx:
            self.reset(token, "OtherPassw0rd!xy")
        self.assertEqual((ctx.exception.status_code, ctx.exception.detail), (400, msg.RECOVERY_LINK_INVALID))

    def test_a_weak_password_is_refused_without_using_up_the_link(self):
        self.forgot("ana")
        token = self.sent[0][2]
        with self.assertRaises(HTTPException) as ctx:
            self.reset(token, "weak")
        self.assertEqual((ctx.exception.status_code, ctx.exception.detail), (400, msg.PASSWORD_RULES))
        self.assertEqual(self.reset(token)["message"], msg.PASSWORD_RESET_DONE)

    def test_wrong_links_are_limited_per_client(self):
        for _ in range(20):
            with self.assertRaises(HTTPException):
                self.reset("wrong")
        with self.assertRaises(HTTPException) as ctx:
            self.reset("wrong")
        self.assertEqual(ctx.exception.status_code, 429)


class PushContactTests(unittest.TestCase):
    def contact(self, setting=None, smtp="", public=""):
        from src.utils import push

        with mock.patch.object(push.settings, "get", return_value=setting),                 mock.patch.object(push.config, "SMTP_EMAIL", smtp),                 mock.patch.object(push.config, "PUBLIC_URL", public):
            return push.contact()

    def test_the_setting_wins_then_the_sender_address_then_an_https_public_url(self):
        self.assertEqual(self.contact(setting="mailto:a@x.es", smtp="b@x.es"), "mailto:a@x.es")
        self.assertEqual(self.contact(smtp="b@x.es", public="https://x.es"), "mailto:b@x.es")
        self.assertEqual(self.contact(public="https://x.es"), "https://x.es")

    def test_without_any_of_them_it_is_still_a_well_formed_contact(self):
        self.assertTrue(self.contact(public="http://localhost:3000").startswith("mailto:"))


if __name__ == "__main__":
    unittest.main()
