"""How the bot talks to the API and picks up its Telegram settings: the superadmin login, the retry with a fresh
token, and the Telegram token and chats, which come from the environment only."""
import os
import unittest
from unittest import mock

from tests import support  # noqa: F401  (sets the environment and the path before the bot is imported)

import requests

from utils import config as config_module
from utils.config import Config


def new_config(**attributes):
    """A Config that skips the singleton, the blocking start-up and the watcher thread."""
    instance = object.__new__(Config)
    instance.API_URL = "http://api/api/v1"
    instance.API_USER = "admin"
    instance.API_PASSWORD = "the-god-password"
    instance.__dict__.update(attributes)
    return instance


def response(status=200, payload=None):
    result = mock.Mock(status_code=status)
    result.json.return_value = payload or {}
    result.raise_for_status.side_effect = None if status < 400 else requests.HTTPError(f"{status}")
    return result


class LoginAndRequestTests(unittest.TestCase):
    def test_login_sends_the_superadmin_credentials_and_keeps_the_token(self):
        config = new_config()
        with mock.patch.object(config_module.requests, "post", return_value=response(payload={"access_token": "tok-1"})) as post:
            config.login()
        self.assertEqual(config._token, "tok-1")
        self.assertEqual(post.call_args.args[0], "http://api/api/v1/token")
        self.assertEqual(post.call_args.kwargs["data"], {"username": "admin", "password": "the-god-password"})

    def test_a_refused_login_raises(self):
        with mock.patch.object(config_module.requests, "post", return_value=response(status=401)):
            with self.assertRaises(requests.HTTPError):
                new_config().login()

    def test_the_first_request_logs_in_and_every_request_carries_the_token(self):
        config = new_config()
        with mock.patch.object(config_module.requests, "post", return_value=response(payload={"access_token": "tok-1"})) as post, \
             mock.patch.object(config_module.requests, "request", return_value=response(payload={"ok": 1})) as request:
            first = config.request("GET", "http://api/api/v1/users/")
            config.request("GET", "http://api/api/v1/users/")
        self.assertEqual(post.call_count, 1)  # the token is reused
        self.assertEqual(first.json(), {"ok": 1})
        self.assertEqual(request.call_args.kwargs["headers"], {"Authorization": "Bearer tok-1"})
        self.assertEqual(request.call_args.kwargs["timeout"], 10)

    def test_an_expired_token_is_replaced_once_and_the_request_repeated(self):
        config = new_config(_token="expired")
        tokens = iter(["fresh"])
        answers = iter([response(status=401), response(payload={"ok": 1})])
        with mock.patch.object(config_module.requests, "post", side_effect=lambda *a, **k: response(payload={"access_token": next(tokens)})) as post, \
             mock.patch.object(config_module.requests, "request", side_effect=lambda *a, **k: next(answers)) as request:
            result = config.request("GET", "http://api/x")
        self.assertEqual(result.json(), {"ok": 1})
        self.assertEqual(post.call_count, 1)
        self.assertEqual([c.kwargs["headers"]["Authorization"] for c in request.call_args_list], ["Bearer expired", "Bearer fresh"])

    def test_a_second_401_is_returned_to_the_caller_not_retried_forever(self):
        config = new_config(_token="x")
        with mock.patch.object(config_module.requests, "post", return_value=response(payload={"access_token": "y"})), \
             mock.patch.object(config_module.requests, "request", return_value=response(status=401)) as request:
            result = config.request("GET", "http://api/x")
        self.assertEqual(result.status_code, 401)
        self.assertEqual(request.call_count, 2)

    def test_other_errors_are_not_retried(self):
        config = new_config(_token="x")
        with mock.patch.object(config_module.requests, "request", return_value=response(status=500)) as request:
            self.assertEqual(config.request("GET", "http://api/x").status_code, 500)
        self.assertEqual(request.call_count, 1)

    def test_a_timeout_given_by_the_caller_is_kept(self):
        config = new_config(_token="x")
        with mock.patch.object(config_module.requests, "request", return_value=response()) as request:
            config.request("POST", "http://api/x", json={"a": 1}, timeout=3)
        self.assertEqual((request.call_args.kwargs["timeout"], request.call_args.kwargs["json"]), (3, {"a": 1}))


class TelegramSettingsTests(unittest.TestCase):
    """The token and the chats come from the environment and nowhere else: the API does not keep them."""

    def start(self, env):
        instance = object.__new__(Config)
        instance._ready = False
        keys = ("TELEGRAM_TOKEN", "TELEGRAM_GROUP_ID", "TELEGRAM_ADMIN_CHAT_ID")
        with mock.patch.dict(os.environ, env), mock.patch.object(config_module, "load_dotenv"),              mock.patch.object(config_module.requests, "request") as request:
            for key in keys:
                if key not in env:
                    os.environ.pop(key, None)
            instance.__init__()
        request.assert_not_called()  # nothing is asked of the API
        return instance

    def test_the_token_and_the_chats_are_the_ones_of_the_environment(self):
        config = self.start({"TELEGRAM_TOKEN": "env-token", "TELEGRAM_GROUP_ID": "-100222", "TELEGRAM_ADMIN_CHAT_ID": "42"})
        self.assertEqual((config.TELEGRAM_TOKEN, config.TELEGRAM_GROUP_ID, config.TELEGRAM_ADMIN_CHAT_ID), ("env-token", "-100222", "42"))

    def test_the_admin_chat_is_optional(self):
        config = self.start({"TELEGRAM_TOKEN": "env-token", "TELEGRAM_GROUP_ID": "-100222"})
        self.assertIsNone(config.TELEGRAM_ADMIN_CHAT_ID)

    def test_without_a_token_or_a_group_it_does_not_start(self):
        for env, name in (({"TELEGRAM_GROUP_ID": "-100222"}, "TELEGRAM_TOKEN"), ({"TELEGRAM_TOKEN": "env-token"}, "TELEGRAM_GROUP_ID"),
                          ({"TELEGRAM_TOKEN": "", "TELEGRAM_GROUP_ID": "-100222"}, "TELEGRAM_TOKEN")):
            with self.assertRaises(SystemExit) as stopped:
                self.start(env)
            self.assertIn(name, str(stopped.exception))


class SingletonTests(unittest.TestCase):
    def test_every_module_gets_the_same_configuration(self):
        self.assertIs(Config(), Config())
        self.assertEqual(Config().API_USER, "admin")  # the bot always acts as the superadmin
