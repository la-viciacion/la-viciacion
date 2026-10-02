"""How the bot talks to the API and picks up its Telegram settings: the superadmin login, the retry with a fresh
token, the settings served by the API with the environment as a fallback, and the restart when they change."""
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
    def load(self, api_values=None, api_error=None, env=None):
        config = new_config()
        fetch = mock.patch.object(Config, "_fetch", side_effect=api_error, return_value=api_values)
        environment = mock.patch.dict(os.environ, env or {}, clear=False)
        with fetch, environment:
            config._load_telegram()
        return config

    def test_what_the_api_serves_wins_over_the_environment(self):
        config = self.load({"token": "api-token", "group_id": "-100111", "admin_chat_id": "42", "version": "v1"},
                           env={"TELEGRAM_TOKEN": "env-token", "TELEGRAM_GROUP_ID": "-100222"})
        self.assertEqual((config.TELEGRAM_TOKEN, config.TELEGRAM_GROUP_ID, config.TELEGRAM_ADMIN_CHAT_ID, config._version), ("api-token", "-100111", "42", "v1"))

    def test_without_the_api_the_environment_is_the_fallback(self):
        config = self.load(api_error=requests.ConnectionError("api down"), env={"TELEGRAM_TOKEN": "env-token", "TELEGRAM_GROUP_ID": "-100222"})
        self.assertEqual((config.TELEGRAM_TOKEN, config.TELEGRAM_GROUP_ID), ("env-token", "-100222"))

    def test_it_waits_and_asks_again_until_there_is_a_token_and_a_group(self):
        config = new_config()
        answers = iter([{"token": None, "group_id": None}, {"token": "t", "group_id": "-1", "version": "v2"}])
        with mock.patch.object(Config, "_fetch", side_effect=lambda: next(answers)), mock.patch.object(config_module.time, "sleep") as sleep, \
             mock.patch.dict(os.environ, {"TELEGRAM_TOKEN": "", "TELEGRAM_GROUP_ID": ""}):
            config._load_telegram()
        sleep.assert_called_once_with(15)
        self.assertEqual((config.TELEGRAM_TOKEN, config._version), ("t", "v2"))

    def test_the_settings_are_fetched_from_the_admin_endpoint_and_a_failure_raises(self):
        config = new_config(_token="x")
        with mock.patch.object(config_module.requests, "request", return_value=response(payload={"token": "t"})) as request:
            self.assertEqual(config._fetch(), {"token": "t"})
        self.assertEqual(request.call_args.args[:2], ("GET", "http://api/api/v1/manage/settings/telegram"))
        with mock.patch.object(config_module.requests, "request", return_value=response(status=403)):
            with self.assertRaises(requests.HTTPError):
                config._fetch()


class WatcherTests(unittest.TestCase):
    class Stop(Exception):
        pass

    def watch(self, versions, current="v1"):
        config = new_config(_version=current)
        answers = iter(versions)

        def fetch():
            answer = next(answers)
            if isinstance(answer, Exception):
                raise answer
            return {"version": answer}

        sleeps = []

        def sleep(seconds):
            sleeps.append(seconds)
            if len(sleeps) > len(versions):
                raise self.Stop()  # the loop never ends by itself

        with mock.patch.object(Config, "_fetch", side_effect=fetch), mock.patch.object(config_module.time, "sleep", side_effect=sleep), \
             mock.patch.object(config_module.os, "_exit", side_effect=self.Stop) as exit_:
            with self.assertRaises(self.Stop):
                config._watch()
        return exit_, sleeps

    def test_it_checks_every_minute_and_leaves_things_alone_while_nothing_changes(self):
        exit_, sleeps = self.watch(["v1", "v1", "v1"])
        exit_.assert_not_called()
        self.assertEqual(set(sleeps), {config_module.WATCH_SECONDS})

    def test_a_change_of_the_telegram_settings_restarts_the_process_so_it_picks_them_up(self):
        exit_, _ = self.watch(["v1", "v2"])
        exit_.assert_called_once_with(0)

    def test_an_api_that_is_restarting_does_not_restart_the_bot(self):
        exit_, _ = self.watch([requests.ConnectionError("api restarting"), "v1"])
        exit_.assert_not_called()


class SingletonTests(unittest.TestCase):
    def test_every_module_gets_the_same_configuration(self):
        self.assertIs(Config(), Config())
        self.assertEqual(Config().API_USER, "admin")  # the bot always acts as the superadmin
