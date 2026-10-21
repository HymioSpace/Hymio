import argparse
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from hymio_cli.command import start
from hymio_cli.process import alive, save, stop


class LifecycleTests(unittest.TestCase):
    def test_reused_pid_cannot_be_stopped(self):
        state = {"pid": 12345, "instance": "a" * 32}
        other = SimpleNamespace(returncode=0, stdout="python /other/application.py")
        with (
            patch("hymio_cli.process.subprocess.run", return_value=other),
            patch("hymio_cli.process.os.killpg") as kill,
        ):
            self.assertFalse(alive(state))
            stop(state)
            kill.assert_not_called()

    def test_stop_requires_matching_launcher_identity(self):
        with (
            patch("hymio_cli.process.alive", side_effect=[True, False, False]),
            patch("hymio_cli.process.os.killpg") as kill,
        ):
            stop({"pid": 12345})
            self.assertEqual(kill.call_args.args[0], 12345)

    def test_matching_ready_instance_does_not_spawn_again(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            root = home / "repo"
            settings = {
                "client": "web",
                "backend_config": str(root / "backend/hymio.toml"),
                "oath_config": str(Path.home() / ".oath/oath.toml"),
                "auth_project": "existing-auth",
                "deploy_config": str(root / "deploy/local.toml"),
                "config": None,
            }
            save(home / "ready.json", {"instance": "current"})
            args = argparse.Namespace(
                client=None, backend_config=None, oath_config=None, auth_project=None
            )
            with (
                patch("hymio_cli.command.alive", return_value=True),
                patch("hymio_cli.command.health", return_value=(True, True)),
                patch("hymio_cli.command.subprocess.Popen") as spawn,
            ):
                start(home, root, args, {"settings": settings, "instance": "current"})
                spawn.assert_not_called()
                args.client = "none"
                with self.assertRaisesRegex(RuntimeError, "different settings"):
                    start(
                        home, root, args, {"settings": settings, "instance": "current"}
                    )
                spawn.assert_not_called()

    def test_stale_ready_file_does_not_complete_a_new_start(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            save(home / "ready.json", {"instance": "a" * 32})
            args = argparse.Namespace(
                client="none",
                backend_config=None,
                oath_config=None,
                auth_project=None,
                timeout=0.5,
            )
            child = SimpleNamespace(pid=12345, poll=lambda: None)
            with (
                patch("hymio_cli.command.alive", return_value=False),
                patch("hymio_cli.command.health", return_value=(False, True)),
                patch("hymio_cli.command.subprocess.Popen", return_value=child),
                patch("hymio_cli.command.time.monotonic", side_effect=[0, 0, 1]),
                patch("hymio_cli.command.time.sleep"),
                self.assertRaisesRegex(RuntimeError, "still in progress"),
            ):
                start(home, home, args, {})

    def test_state_is_private_and_atomically_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            save(path, {"pid": 1})
            save(path, {"pid": 2})
            self.assertIn("2", path.read_text())
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertFalse(path.with_suffix(".tmp").exists())


if __name__ == "__main__":
    unittest.main()
