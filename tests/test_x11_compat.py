import unittest

from Xlib import error, xauth

from gesto.x11_compat import enable_empty_display_auth


class AuthCompatibilityTests(unittest.TestCase):
    def setUp(self):
        enable_empty_display_auth()
        self.authority = xauth.Xauthority.__new__(xauth.Xauthority)
        # Solo datos ficticios. No se abren archivos de autorización ni sockets.
        self.authority.entries = [
            (256, b"test-host", b"", b"MIT-MAGIC-COOKIE-1", b"fake-empty-display-cookie"),
        ]

    def test_empty_display_matches_same_host_and_family(self):
        self.assertEqual(
            self.authority.get_best_auth(256, "test-host", 0),
            (b"MIT-MAGIC-COOKIE-1", b"fake-empty-display-cookie"),
        )

    def test_explicit_display_takes_precedence(self):
        self.authority.entries.append(
            (256, b"test-host", b"0", b"MIT-MAGIC-COOKIE-1", b"fake-explicit-cookie")
        )
        self.assertEqual(self.authority.get_best_auth(256, "test-host", 0)[1], b"fake-explicit-cookie")

    def test_different_host_family_or_protocol_is_rejected(self):
        for family, host, protocols in ((256, "other-host", (b"MIT-MAGIC-COOKIE-1",)),
                                        (0, "test-host", (b"MIT-MAGIC-COOKIE-1",)),
                                        (256, "test-host", (b"OTHER-PROTOCOL",))):
            with self.subTest(family=family, host=host), self.assertRaises(error.XNoAuthError):
                self.authority.get_best_auth(family, host, 0, protocols)

    def test_nonempty_wrong_display_does_not_match(self):
        self.authority.entries = [
            (256, b"test-host", b"1", b"MIT-MAGIC-COOKIE-1", b"fake-cookie"),
        ]
        with self.assertRaises(error.XNoAuthError):
            self.authority.get_best_auth(256, "test-host", 0)

    def test_enabling_compatibility_is_idempotent(self):
        method = xauth.Xauthority.get_best_auth
        enable_empty_display_auth()
        self.assertIs(xauth.Xauthority.get_best_auth, method)
