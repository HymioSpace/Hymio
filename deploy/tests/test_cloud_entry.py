import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "cloud_manage", Path(__file__).resolve().parents[1] / "cloud/manage.py"
)
cloud = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cloud)


class CloudEntryTests(unittest.TestCase):
    def test_admin_console_requires_oath_internal_token_file(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            backend = root / "hymio.toml"
            backend.write_text(
                'computer_provider="e2b"\nhost="0.0.0.0"\nport=8080\n'
                'database="/data/hymio.sqlite"\npublic_url="https://app.example.com"\n'
                'oath_ws="ws://host.docker.internal:8765"\n'
                'admin_user_ids=["user-1"]\n'
            )
            config = root / "cloud.toml"
            config.write_text(
                'web_domain="app.example.com"\napi_domain="app.example.com"\n'
                'backend_config_dir="."\n'
            )
            previous = cloud.OUTPUT
            cloud.OUTPUT = root / "generated"
            try:
                with self.assertRaisesRegex(ValueError, "oath_admin_token_file"):
                    cloud.generate(config)
                token = root / "oath-admin-token"
                token.write_text("x" * 43)
                backend.write_text(
                    backend.read_text() + 'oath_admin_token_file="./oath-admin-token"\n'
                )
                cloud.generate(config)
            finally:
                cloud.OUTPUT = previous

    def test_single_domain_routes_api_before_static_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "hymio.toml").write_text(
                'computer_provider="e2b"\nhost="0.0.0.0"\nport=8080\ndatabase="/data/hymio.sqlite"\npublic_url="https://app.example.com"\noath_ws="ws://host.docker.internal:8765"\n'
            )
            config = root / "cloud.toml"
            config.write_text(
                'web_domain="app.example.com"\napi_domain="app.example.com"\nbackend_config_dir="."\nmanaged_identity=true\nruntime_network="oath_oath"\n'
            )
            previous = cloud.OUTPUT
            cloud.OUTPUT = root / "generated"
            try:
                compose = json.loads(cloud.generate(config).read_text())
                self.assertEqual(
                    compose["services"]["identity"]["ports"], ["127.0.0.1:8000:8000"]
                )
                self.assertIn("identity-data", compose["volumes"])
                self.assertNotIn("ports", compose["services"]["backend"])
                self.assertEqual(compose["networks"]["runtime"]["name"], "oath_oath")
                caddy = (cloud.OUTPUT / "Caddyfile").read_text()
                self.assertEqual(caddy.count("app.example.com"), 1)
                self.assertIn("/agent/*", caddy)
                self.assertIn("/telemetry/*", caddy.split("handle @backend")[0])
                self.assertEqual(
                    json.loads(
                        (cloud.OUTPUT / "hymio-metrics-targets.json").read_text()
                    ),
                    [{"targets": ["backend:8080"]}],
                )
                self.assertEqual(
                    (cloud.OUTPUT / "hymio-metrics-targets.json").stat().st_mode
                    & 0o777,
                    0o644,
                )
                self.assertEqual(
                    compose["services"]["backend"]["environment"][
                        "HYMIO_PROMETHEUS_URL"
                    ],
                    "http://prometheus:9090",
                )
                self.assertIn("/devices/*", caddy)
                self.assertIn("/tasks", caddy.split("handle @backend")[0])
                self.assertIn("handle /admin/api/*", caddy)
                self.assertIn("handle_path /admin/*", caddy)
                self.assertIn("root * /srv/admin", caddy)
                self.assertLess(
                    caddy.index("handle /admin/api/*"),
                    caddy.index("handle_path /admin/*"),
                )
                self.assertLess(
                    caddy.index("handle @backend"),
                    caddy.index("try_files", caddy.index("handle @backend")),
                )
                self.assertIn("handle @private {\n  respond 404", caddy)
            finally:
                cloud.OUTPUT = previous

    def test_two_domains_and_optional_legacy_agent_entry(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "hymio.toml").write_text(
                'computer_provider="e2b"\nhost="0.0.0.0"\nport=8080\ndatabase="/data/hymio.sqlite"\npublic_url="https://api.example.com"\noath_ws="ws://host.docker.internal:8765"\n'
            )
            config = root / "cloud.toml"
            source = 'web_domain="app.example.com"\napi_domain="api.example.com"\nbackend_config_dir="."\n'
            config.write_text(source)
            previous = cloud.OUTPUT
            cloud.OUTPUT = root / "generated"
            try:
                compose = json.loads(cloud.generate(config).read_text())
                self.assertEqual(set(compose["services"]), {"backend", "edge"})
                caddy = (cloud.OUTPUT / "Caddyfile").read_text()
                self.assertIn("api.example.com", caddy)
                self.assertNotIn("agent.example.com", caddy)
                config.write_text(source + 'agent_domain="agent.example.com"\n')
                cloud.generate(config)
                self.assertIn(
                    "agent.example.com", (cloud.OUTPUT / "Caddyfile").read_text()
                )
            finally:
                cloud.OUTPUT = previous
