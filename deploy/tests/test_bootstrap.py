"""Portable input and interruption/compatibility boundaries for local initialization."""

import json
import os
import sys
import tempfile
import tomllib
import unittest
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli"))
from bootstrap_config import container_readable, load, prepare, runtime_for
from bootstrap_identity import compose
from hymio_cli.command import options


class BootstrapTests(unittest.TestCase):
    def source(self, root, extra=""):
        path = Path(root) / "config.toml"
        path.write_text(
            'minimax_api_key = "synthetic-minimax"\ne2b_api_key = "synthetic-e2b"\n'
            + extra
        )
        return path

    def test_restart_reuses_internal_identity_and_omits_external_keys_from_service_configs(
        self,
    ):
        with (
            tempfile.TemporaryDirectory() as root,
            patch.dict(os.environ, {}, clear=True),
        ):
            path = self.source(
                root, 'casdoor_port = 8001\ninvitation_codes = ["synthetic-invite"]\n'
            )
            settings, runtime, identity = prepare(path)
            # Simulate an interrupted start by deleting only generated output, not identity.
            (runtime / "backend/hymio.toml").unlink()
            again, runtime2, identity2 = prepare(path)
            self.assertEqual((runtime, identity), (runtime2, identity2))
            backend = tomllib.loads((runtime / "backend/hymio.toml").read_text())
            self.assertEqual(backend["issuer"], "http://localhost:8001")
            self.assertEqual(backend["model_options"], settings["models"])
            self.assertTrue(backend["invitation_codes_file"])
            generated = compose(runtime, again, identity2)
            for file in (
                generated,
                runtime / "oath/oath.toml",
                runtime / "backend/hymio.toml",
            ):
                self.assertEqual(file.stat().st_mode & 0o777, 0o600)
                self.assertNotIn("synthetic-minimax", file.read_text())
                self.assertNotIn("synthetic-e2b", file.read_text())
            spec = json.loads(generated.read_text())
            self.assertEqual(
                spec["services"]["casdoor"]["environment"]["initDataNewOnly"], "true"
            )
            self.assertEqual(
                spec["services"]["casdoor"]["ports"], ["127.0.0.1:8001:8000"]
            )

    def test_new_location_gets_new_identity_not_copied_service_credentials(self):
        with (
            tempfile.TemporaryDirectory() as a,
            tempfile.TemporaryDirectory() as b,
            patch.dict(os.environ, {}, clear=True),
        ):
            original = self.source(a)
            copied = Path(b) / "config.toml"
            copied.write_text(original.read_text())
            self.assertNotEqual(runtime_for(original), runtime_for(copied))
            self.assertNotEqual(prepare(original)[2], prepare(copied)[2])

    def test_environment_overrides_and_invalid_inputs_fail_without_runtime(self):
        with (
            tempfile.TemporaryDirectory() as root,
            patch.dict(
                os.environ,
                {"MINIMAX_API_KEY": "env-model", "E2B_API_KEY": "env-e2b"},
                clear=True,
            ),
        ):
            path = self.source(root)
            self.assertEqual(load(path)["minimax_api_key"], "env-model")
            for extra in (
                "unknown = true",
                "models = []",
                "casdoor_port = 8080",
                "casdoor_port = true",
                'minimax_api_base = "http://example.com/v1"',
                'models = "model"',
            ):
                path = self.source(root, extra)
                with self.subTest(extra=extra), self.assertRaises(ValueError):
                    prepare(path)
                self.assertFalse(runtime_for(path).exists())

    def test_missing_key_has_actionable_error_without_disclosing_other_key(self):
        with (
            tempfile.TemporaryDirectory() as root,
            patch.dict(os.environ, {}, clear=True),
        ):
            path = Path(root) / "config.toml"
            path.write_text(
                'computer_provider = "e2b"\nminimax_api_key = "synthetic-private"\n'
            )
            with self.assertRaisesRegex(ValueError, "E2B_API_KEY") as error:
                load(path)
            self.assertNotIn("synthetic-private", str(error.exception))

    def test_cli_detects_one_file_and_explicit_legacy_override(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            (home / "config.toml").write_text("")
            args = Namespace(
                home=home, config=None, backend_config=None, oath_config=None
            )
            self.assertEqual(
                options(args, home, {})["config"], str((home / "config.toml").resolve())
            )
            args.backend_config = str(home / "existing.toml")
            self.assertIsNone(
                options(args, home, {"config": str(home / "config.toml")})["config"]
            )

    def test_changed_model_key_rotates_alias_without_resetting_identity(self):
        with (
            tempfile.TemporaryDirectory() as folder,
            patch.dict(os.environ, {}, clear=True),
        ):
            path = self.source(folder)
            _, runtime, identity = prepare(path)
            before = tomllib.loads((runtime / "oath/oath.toml").read_text())
            path.write_text(
                path.read_text().replace("synthetic-minimax", "synthetic-replacement")
            )
            _, _, after_identity = prepare(path)
            after = tomllib.loads((runtime / "oath/oath.toml").read_text())
            self.assertEqual(identity, after_identity)
            self.assertNotEqual(
                before["agent"]["provider"]["credential"],
                after["agent"]["provider"]["credential"],
            )

    def test_launcher_uses_named_oath_and_scoped_model_import(self):
        import start as launcher

        with (
            tempfile.TemporaryDirectory() as folder,
            patch.dict(os.environ, {}, clear=True),
        ):
            path = self.source(folder, "casdoor_port = 8001\n")
            child = SimpleNamespace(pid=12345, poll=lambda: None, wait=lambda **_: 0)
            with (
                patch.object(
                    sys, "argv", ["start.py", "--config", str(path), "--client", "none"]
                ),
                patch.object(launcher.shutil, "which", return_value="available"),
                patch.object(
                    launcher.subprocess,
                    "run",
                    return_value=SimpleNamespace(
                        stdout=(
                            "--system-prompt --name --context-provider "
                            "--context-provider-token-file"
                        )
                    ),
                ),
                patch.object(launcher.subprocess, "Popen", return_value=child) as popen,
                patch.object(launcher, "run") as run,
                patch.object(launcher, "wait_http") as wait,
                patch.object(launcher, "free_port"),
                patch.object(
                    launcher,
                    "prepare_devices",
                    side_effect=lambda config, config_path, oath, tools_dir: oath,
                ),
                patch.object(launcher, "write_ios_network"),
                patch("bootstrap_identity.verify"),
                patch("bootstrap_config.container_readable"),
                patch.object(launcher.os, "killpg"),
                patch.object(launcher.time, "sleep", side_effect=KeyboardInterrupt),
                self.assertRaises(KeyboardInterrupt),
            ):
                launcher.main()
            oath = next(c for c in run.call_args_list if c.args[0][0] == "oath")
            self.assertIn("--name", oath.args[0])
            self.assertEqual(oath.kwargs["env"]["MINIMAX_API_KEY"], "synthetic-minimax")
            self.assertNotIn("synthetic-minimax", " ".join(map(str, oath.args[0])))
            self.assertNotIn("env", popen.call_args.kwargs)
            self.assertIn(
                "http://localhost:8001/.well-known/openid-configuration",
                [c.args[0] for c in wait.call_args_list],
            )

    def test_container_files_are_readable_under_private_host_ancestors(self):
        with (
            tempfile.TemporaryDirectory() as folder,
            patch.dict(os.environ, {}, clear=True),
        ):
            path = self.source(folder)
            _, runtime, _ = prepare(path)
            tools = runtime / "tools"
            tools.mkdir()
            (tools / "_connection.local").write_text("synthetic-service-connection")
            config = runtime / "oath/oath.toml"
            container_readable(runtime, config, tools)
            self.assertEqual(runtime.stat().st_mode & 0o777, 0o700)
            self.assertEqual(config.stat().st_mode & 0o777, 0o644)
            self.assertEqual(
                (runtime / "oath/data/private").stat().st_mode & 0o777, 0o700
            )
            role = runtime / "oath/data/private/vault-role-id"
            role.write_text("synthetic-existing-role")
            container_readable(runtime, config, tools)
            self.assertEqual(role.read_text(), "synthetic-existing-role")
            self.assertEqual((runtime / "identity.json").stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
