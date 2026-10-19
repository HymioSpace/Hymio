import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_network import lan_address, prepare_lan, write_ios_network, load_network


class LocalNetworkTests(unittest.TestCase):
    def test_overlay_preserves_identity_paths_callback_and_signing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ios = root / "apps/ios/Config/Local.xcconfig"
            ios.parent.mkdir(parents=True)
            ios.write_text(
                "DEVELOPMENT_TEAM = TESTTEAM\nPRODUCT_BUNDLE_IDENTIFIER = example.test\n"
            )
            config = {
                "database": "data/state.sqlite",
                "service_token_file": "private/token",
                "client_secret_file": "private/oidc",
                "e2b_key_file": "private/e2b",
                "public_url": "http://localhost:8080",
                "callback_url": "http://localhost:8080/auth/callback",
                "origins": ["http://localhost:1420"],
                "login_method": "account",
            }
            source = root / "hymio.toml"
            source.write_text("# original\n")
            overlay, target = prepare_lan(root, config, source, "192.168.1.20")
            self.assertEqual(tomllib.loads(target.read_text()), overlay)
            self.assertEqual(source.read_text(), "# original\n")
            self.assertEqual(overlay["callback_url"], config["callback_url"])
            self.assertEqual(
                overlay["database"], str((root / "data/state.sqlite").resolve())
            )
            self.assertEqual(overlay["public_url"], "http://192.168.1.20:8080")
            self.assertIn("DEVELOPMENT_TEAM = TESTTEAM", ios.read_text())
            write_ios_network(root, overlay["public_url"])
            self.assertNotIn("HYMIO_BACKEND_URL", ios.read_text())
            self.assertIn(
                "HYMIO_BACKEND_URL = http:/$()/192.168.1.20:8080",
                (ios.parent / "Network.generated.xcconfig").read_text(),
            )
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)

    def test_non_lan_or_unspecified_addresses_are_rejected(self):
        for address in ("0.0.0.0", "127.0.0.1", "8.8.8.8", "http://example.com"):
            with self.subTest(address=address), self.assertRaises(ValueError):
                lan_address(address)
        self.assertIsNone(lan_address("off"))

    def test_single_config_is_reloaded_and_unknown_keys_fail(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "local.toml"
            self.assertEqual(load_network(path), "off")
            path.write_text('lan_host = "auto"\n')
            self.assertEqual(load_network(path), "auto")
            path.write_text('lan_host = "off"\n')
            self.assertEqual(load_network(path), "off")
            path.write_text('typo_host = "auto"\n')
            with self.assertRaises(ValueError):
                load_network(path)
