#!/usr/bin/env python3
"""Start the local Hymio development stack."""

import argparse
import fcntl
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    raise SystemExit(
        "Use: uv run --python 3.12 --no-project python deploy/start.py"
    ) from None
from urllib.request import urlopen

from local_network import lan_address, load_network, prepare_lan, write_ios_network

ROOT = Path(__file__).resolve().parents[1]


def run(args, cwd=ROOT, env=None):
    subprocess.run(
        [str(arg) for arg in args], cwd=cwd, env=env, check=True, timeout=900
    )


def wait_http(url, child=None, timeout=90):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if child is not None and child.poll() is not None:
            raise RuntimeError("Backend exited before becoming ready")
        try:
            with urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except OSError:
            pass
        time.sleep(0.5)
    raise RuntimeError(f"Timed out waiting for {url}")


def free_port(port):
    with socket.socket() as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
        except OSError as error:
            raise RuntimeError(
                f"Port {port} is occupied; stop its service first"
            ) from error


def prepare_devices(config, config_path, oath_config, tools_dir=None):
    """Mount product tools without exposing the Oath host shell."""
    service_key = (
        config_path.parent / Path(config["service_token_file"]).expanduser()
    ).resolve()
    target = (tools_dir or ROOT / "extensions/tools") / "_connection.local"
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as file:
        json.dump(
            {
                "url": "http://host.docker.internal:8080",
                "token": service_key.read_text().strip(),
            },
            file,
        )
    source = oath_config.read_text()
    choices = config.get("model_options", ["MiniMax-M2.7", "MiniMax-M3"])
    source = re.sub(r"^selectable_models\s*=.*$", "", source, flags=re.MULTILINE)
    source = source.replace(
        "[agent]", "[agent]\nselectable_models = " + json.dumps(choices), 1
    )
    source = re.sub(r"^tool_timeout_seconds\s*=.*$", "", source, flags=re.MULTILINE)
    source = source.replace("[agent]", "[agent]\ntool_timeout_seconds = 150", 1)
    if not re.search(r"^\[agent\]\s*$", source, re.MULTILINE):
        raise RuntimeError("Oath config must contain [agent]")
    if re.search(r"^builtin_bash\s*=", source, re.MULTILINE):
        source = re.sub(
            r"^builtin_bash\s*=.*$", "builtin_bash = false", source, flags=re.MULTILINE
        )
    else:
        source = re.sub(
            r"^\[agent\]\s*$",
            "[agent]\nbuiltin_bash = false",
            source,
            count=1,
            flags=re.MULTILINE,
        )
    generated = oath_config.with_name("hymio-runtime.local.toml")
    fd = os.open(generated, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as file:
        file.write(source)
    return generated


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", choices=("web", "desk", "none"), default="web")
    parser.add_argument("--backend-config", type=Path)
    parser.add_argument("--oath-config", type=Path)
    parser.add_argument(
        "--config", type=Path, help="Single portable private deployment configuration"
    )
    parser.add_argument("--auth-project", default="hymio-auth")
    parser.add_argument(
        "--deploy-config", type=Path, default=ROOT / "deploy/local.toml"
    )
    parser.add_argument("--instance", help=argparse.SUPPRESS)
    parser.add_argument("--ready-file", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    children = []
    bootstrap_lock = None
    try:
        for command in (
            "docker",
            "uv",
            "oath",
            *(("pnpm",) if args.client != "none" else ()),
        ):
            if not shutil.which(command):
                raise RuntimeError(
                    f"Missing {command}; see deploy/README.md prerequisites"
                )
        if os.name != "posix":
            raise RuntimeError("This launcher currently supports macOS and Linux")
        help_text = subprocess.run(
            ["oath", "start", "--help"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        ).stdout
        if "--system-prompt" not in help_text:
            raise RuntimeError(
                "Update Oath: this launcher requires --system-prompt support"
            )
        unified = args.config
        default_input = Path.home() / ".hymio/config.toml"
        if (
            not unified
            and not args.backend_config
            and not args.oath_config
            and default_input.exists()
        ):
            unified = default_input
        if unified and (args.backend_config or args.oath_config):
            raise ValueError("Use --config or legacy service configs, not both")
        managed = None
        identity_compose = ROOT / "deploy/auth/compose.yaml"
        credentials = None
        tools_dir = ROOT / "extensions/tools"
        oath_name = None
        if unified:
            from bootstrap_config import prepare, runtime_for
            from bootstrap_identity import compose

            unified = unified.expanduser().resolve()
            runtime = runtime_for(unified)
            runtime.mkdir(parents=True, mode=0o700, exist_ok=True)
            bootstrap_lock = (runtime / "launch.lock").open("a")
            try:
                fcntl.flock(bootstrap_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError(
                    "This configuration already has a running launcher"
                ) from None
            managed, runtime, credentials = prepare(unified)
            # External keys are consumed here; only the Oath CLI gets the model import.
            for key in ("MINIMAX_API_KEY", "E2B_API_KEY"):
                os.environ.pop(key, None)
            args.backend_config = runtime / "backend/hymio.toml"
            args.oath_config = runtime / "oath/oath.toml"
            args.deploy_config = runtime / "network.toml"
            suffix = runtime.name.removeprefix("local-")
            args.auth_project = "hymio-local-" + suffix
            oath_name = "hymio-oath-" + suffix
            tools_dir = runtime / "tools"
            shutil.copytree(
                ROOT / "extensions/tools",
                tools_dir,
                dirs_exist_ok=True,
                ignore=shutil.ignore_patterns(
                    "_connection.local", "__pycache__", "*.pyc"
                ),
            )
            identity_compose = compose(runtime, managed, credentials)
            print(
                f"Unified configuration: {unified}. Generated runtime: {runtime}",
                flush=True,
            )
        args.backend_config = args.backend_config or ROOT / "backend/hymio.toml"
        args.oath_config = args.oath_config or Path.home() / ".oath/oath.toml"
        config_path = args.backend_config.expanduser().resolve()
        if not config_path.is_file():
            raise RuntimeError(
                "Run hymio init first; legacy manual setup is documented in deploy/README.md"
            )
        config = tomllib.loads(config_path.read_text())
        provider = config.get("computer_provider", "e2b")
        if provider not in ("daytona", "e2b", "device_api"):
            raise RuntimeError("computer_provider must be daytona, device_api or e2b")
        key_path = None
        if provider == "e2b":
            key_file = config.get("e2b_key_file")
            if not key_file:
                raise RuntimeError("Set e2b_key_file for the legacy E2B provider")
            key_path = (config_path.parent / Path(key_file).expanduser()).resolve()
            if not key_path.is_file() or not key_path.read_text().strip():
                raise RuntimeError("E2B key file is missing or empty")
        extras = ["--extra", "e2b"] if provider == "e2b" else []
        if config.get("host") != "0.0.0.0" or config.get("port", 8080) != 8080:
            raise RuntimeError(
                'Set Backend host = "0.0.0.0" and port = 8080 for Docker access'
            )
        if not managed and config.get("issuer") != "http://localhost:8000":
            raise RuntimeError(
                "This launcher requires local Casdoor at http://localhost:8000"
            )
        for field in ("service_token_file", "client_secret_file"):
            path = (config_path.parent / Path(config[field]).expanduser()).resolve()
            if not path.is_file():
                raise RuntimeError(f"Missing credential file referenced by {field}")
        oath_config = args.oath_config.expanduser().resolve()
        if not oath_config.is_file():
            raise RuntimeError(
                "Configure ~/.oath/oath.toml and its model credential first"
            )
        runtime = tomllib.loads(oath_config.read_text()).get("services", {})
        ws = f"ws://127.0.0.1:{runtime.get('gateway_port', 8765)}"
        biz = f"http://127.0.0.1:{runtime.get('biz_port', 8766)}"
        if config.get("oath_ws") != ws or config.get("oath_biz") != biz:
            raise RuntimeError(
                "Backend oath_ws/oath_biz must match the local Oath configured ports"
            )
        address = lan_address(load_network(args.deploy_config.expanduser().resolve()))
        if address:
            config, config_path = prepare_lan(ROOT, config, config_path, address)
        model_config = tomllib.loads(oath_config.read_text())
        provider = model_config.get("agent", {}).get("provider", {})
        secrets = model_config.get("secrets", {})
        overlay = dict(config)
        overlay.setdefault(
            "media_api_base",
            provider.get("api_base", "https://api.minimax.cn/v1").removesuffix(
                "/chat/completions"
            ),
        )
        overlay.setdefault("media_credential", provider.get("credential", ""))
        overlay.setdefault(
            "vault_url", secrets.get("vault_url", "http://127.0.0.1:8200")
        )
        for key, default in (
            ("role_id_file", "./data/private/vault-role-id"),
            ("secret_id_file", "./data/private/vault-secret-id"),
        ):
            overlay.setdefault(
                "vault_" + key,
                str(
                    (
                        oath_config.parent
                        / Path(secrets.get(key, default)).expanduser()
                    ).resolve()
                ),
            )
        # Resolve existing private paths before writing an overlay in the same directory.
        for key in (
            "database",
            "client_secret_file",
            "service_token_file",
            "e2b_key_file",
            "daytona_key_file",
            "invitation_codes_file",
        ):
            if overlay.get(key):
                overlay[key] = str(
                    (config_path.parent / Path(overlay[key]).expanduser()).resolve()
                )
        config_path = config_path.with_name("hymio-media.local.toml")
        from local_network import private_write
        from bootstrap_config import toml

        private_write(
            config_path,
            toml(overlay),
        )
        config = overlay
        write_ios_network(ROOT, config["public_url"])
        free_port(8080)
        if args.client != "none":
            free_port(1420)
        run(["docker", "info"], cwd=ROOT)
        if managed:
            owned = subprocess.run(
                [
                    "docker",
                    "compose",
                    "-f",
                    str(identity_compose),
                    "-p",
                    args.auth_project,
                    "ps",
                    "-q",
                    "casdoor",
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=20,
            )
            if not owned.stdout.strip():
                free_port(managed["casdoor_port"])
        run(
            [
                "uv",
                "sync",
                "--frozen",
                *extras,
            ],
            cwd=ROOT / "backend",
        )
        if managed and provider == "e2b":
            run(
                [
                    "uv",
                    "run",
                    "--frozen",
                    "--extra",
                    "e2b",
                    "python",
                    ROOT / "deploy/computer/build_e2b.py",
                    "--key-file",
                    key_path,
                    "--name",
                    managed["e2b_template"],
                    "--ensure",
                ],
                cwd=ROOT / "backend",
            )
        oath_config = prepare_devices(config, config_path, oath_config, tools_dir)
        if managed:
            from bootstrap_config import container_readable

            container_readable(runtime, oath_config, tools_dir)
        if args.client != "none":
            run(["pnpm", "install", "--frozen-lockfile"], cwd=ROOT / "apps/client")
        run(
            [
                "docker",
                "compose",
                "-f",
                identity_compose,
                "-p",
                args.auth_project,
                "up",
                "-d",
            ]
        )
        wait_http(config["issuer"] + "/.well-known/openid-configuration")
        if managed:
            from bootstrap_identity import verify

            verify(config["issuer"], credentials)
        backend = subprocess.Popen(
            [
                "uv",
                "run",
                "--frozen",
                *extras,
                "python",
                "-m",
                "hymio_backend",
                "--config",
                str(config_path),
            ],
            cwd=ROOT / "backend",
            start_new_session=True,
        )
        children.append(backend)
        wait_http("http://127.0.0.1:8080/health", backend)
        oath_env = (
            {**os.environ, "MINIMAX_API_KEY": managed["minimax_api_key"]}
            if managed
            else None
        )
        run(
            [
                "oath",
                "start",
                *(["--name", oath_name] if managed else []),
                "--config",
                oath_config,
                "--system-prompt",
                ROOT / "extensions/prompts/hymio.md",
                "--auth-mode",
                "remote",
                "--auth-url",
                "http://host.docker.internal:8080/internal/auth/verify",
                "--auth-token-file",
                (
                    config_path.parent / Path(config["service_token_file"]).expanduser()
                ).resolve(),
                "--tool",
                tools_dir,
                "--skill",
                ROOT / "extensions/skills",
            ],
            env=oath_env,
        )
        if args.client != "none":
            children.append(
                subprocess.Popen(
                    ["pnpm", "dev" if args.client == "web" else "desktop"],
                    env={
                        **os.environ,
                        "HYMIO_BACKEND_URL": config["public_url"],
                        "HYMIO_LAN": "1" if address else "0",
                    },
                    cwd=ROOT / "apps/client",
                    start_new_session=True,
                )
            )
        print(
            "Hymio running. Backend: http://localhost:8080 | Web: http://127.0.0.1:1420"
            if args.client != "none"
            else "Hymio Backend running: http://localhost:8080",
            flush=True,
        )
        if address:
            print(
                f"iPhone Backend: {config['public_url']} | Web: http://{address}:1420 | iOS Debug network configuration generated",
                flush=True,
            )
        print(
            "Ctrl+C stops Backend/client. Docker services remain running.", flush=True
        )
        if args.ready_file and args.instance:
            temporary = args.ready_file.with_suffix(".tmp")
            temporary.write_text(
                json.dumps(
                    {
                        "instance": args.instance,
                        "backend_url": config["public_url"],
                        "web_url": f"http://{address or '127.0.0.1'}:1420",
                    }
                )
            )
            temporary.chmod(0o600)
            temporary.replace(args.ready_file)
        while all(child.poll() is None for child in children):
            time.sleep(0.5)
        if any(child.returncode not in (None, 0) for child in children):
            raise RuntimeError("A foreground service failed; see its output above")
    finally:
        for child in children:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
        deadline = time.monotonic() + 8
        for child in children:
            try:
                child.wait(timeout=max(0.1, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
        if bootstrap_lock is not None:
            bootstrap_lock.close()


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    try:
        main()
    except KeyboardInterrupt:
        pass
    except (
        RuntimeError,
        OSError,
        ValueError,
        TypeError,
        KeyError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
    ) as error:
        print(f"Startup failed: {error}", file=sys.stderr)
        sys.exit(1)
