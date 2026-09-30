import unittest

from src.routers.basic import client_key


class ClientKeyTests(unittest.TestCase):
    def test_a_public_address_is_counted(self):
        self.assertEqual(client_key("83.45.10.7"), "83.45.10.7")
        self.assertEqual(client_key("2a02:9130::1"), "2a02:9130::1")

    def test_private_and_loopback_peers_are_not_a_client(self):
        for host in ("172.18.0.3", "10.0.0.5", "192.168.1.20", "127.0.0.1", "::1"):
            self.assertIsNone(client_key(host), host)

    def test_missing_or_odd_hosts_are_not_a_client(self):
        for host in (None, "", "unknown", "testclient"):
            self.assertIsNone(client_key(host), repr(host))


if __name__ == "__main__":
    unittest.main()


class NoSignupTests(unittest.TestCase):
    def test_there_is_no_public_registration_route(self):
        from src.routers import basic

        paths = {route.path for route in basic.router.routes}
        self.assertNotIn("/signup", paths)
        self.assertEqual(paths, {"/", "/keepalive", "/token", "/auth/active_user", "/auth/forgot-password", "/auth/reset-password"})
