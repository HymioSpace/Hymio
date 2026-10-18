import tempfile
import time
import unittest
from pathlib import Path

from hymio_backend.config import Settings
from hymio_backend.session_store import SessionStore, Unauthorized


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        root = Path(self.folder.name)
        self.settings = Settings(
            root / "state.sqlite",
            "https://identity.example",
            "hymio",
            root / "oidc-secret",
            "https://hymio.example",
            "https://hymio.example/auth/callback",
            root / "service-secret",
            ("https://client.example",),
            "wss://agent.example",
            "http://biz",
        )
        self.store = SessionStore(self.settings)

    def tearDown(self):
        self.folder.cleanup()

    def login(self, subject="person-a"):
        handle, state, _, _ = self.store.start("https://client.example")
        self.store.claim_callback(state)
        code, _ = self.store.finish(state, {"iss": self.settings.issuer, "sub": subject})
        return self.store.exchange(handle, code)

    def test_identity_is_stable_and_callback_and_grant_are_single_use(self):
        handle, state, _, _ = self.store.start("https://client.example")
        self.store.claim_callback(state)
        with self.assertRaises(Unauthorized):
            self.store.claim_callback(state)
        code, _ = self.store.finish(state, {"iss": self.settings.issuer, "sub": "person-a"})
        with self.assertRaises(Unauthorized):
            self.store.exchange(handle, "wrong")
        first = self.store.exchange(handle, code)
        with self.assertRaises(Unauthorized):
            self.store.exchange(handle, code)
        self.assertEqual(first["user_id"], self.login()["user_id"])
        self.assertNotEqual(first["user_id"], self.login("person-b")["user_id"])

    def test_refresh_reuse_revokes_only_its_login(self):
        first, other = self.login(), self.login()
        new = self.store.refresh(first["refresh_token"])
        with self.assertRaises(Unauthorized):
            self.store.verify(first["access_token"])
        self.store.verify(new["access_token"])
        with self.assertRaises(Unauthorized):
            self.store.refresh(first["refresh_token"])
        with self.assertRaises(Unauthorized):
            self.store.verify(new["access_token"])
        self.store.verify(other["access_token"])

    def test_account_and_browser_login_share_identity_but_isolate_sessions(self):
        account = self.store.create_session({"iss": self.settings.issuer, "sub": "person-a"})
        browser = self.login("person-a")
        other = self.store.create_session({"iss": self.settings.issuer, "sub": "person-b"})
        self.assertEqual(account["user_id"], browser["user_id"])
        self.assertNotEqual(account["user_id"], other["user_id"])
        self.store.logout(account["access_token"])
        with self.assertRaises(Unauthorized):
            self.store.verify(account["access_token"])
        self.assertEqual(self.store.verify(browser["access_token"])["user_id"], browser["user_id"])
        self.assertEqual(self.store.verify(other["access_token"])["user_id"], other["user_id"])

    def test_logout_and_expiry_deny_access(self):
        first = self.login()
        self.store.logout(first["access_token"])
        with self.assertRaises(Unauthorized):
            self.store.verify(first["access_token"])
        with self.assertRaises(Unauthorized):
            self.store.refresh(first["refresh_token"])
        second = self.login()
        with self.store.transaction() as db:
            db.execute("UPDATE credentials SET expires=?", (time.time() - 1,))
        with self.assertRaises(Unauthorized):
            self.store.verify(second["access_token"])


if __name__ == "__main__":
    unittest.main()
