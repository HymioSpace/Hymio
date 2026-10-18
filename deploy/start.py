#!/usr/bin/env python3
"""Start the local Hymio development stack."""
import argparse
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time
try:
    import tomllib
except ModuleNotFoundError:
    raise SystemExit("Use: uv run --python 3.12 --no-project python deploy/start.py")
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def run(args, cwd=ROOT):
    subprocess.run([str(arg) for arg in args], cwd=cwd, check=True, timeout=900)


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
        try:
            sock.bind(("127.0.0.1", port))
        except OSError as error:
            raise RuntimeError(f"Port {port} is occupied; stop its service first") from error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", choices=("web", "desk", "none"), default="web")
    parser.add_argument("--backend-config", type=Path, default=ROOT / "backend/hymio.toml")
    parser.add_argument("--oath-config", type=Path, default=Path.home() / ".oath/oath.toml")
    parser.add_argument("--auth-project", default="hymio-auth")
    args = parser.parse_args()
    children = []
    try:
        for command in ("docker", "uv", "oath", *(("pnpm",) if args.client != "none" else ())):
            if not shutil.which(command):
                raise RuntimeError(f"Missing {command}; see deploy/README.md prerequisites")
        if os.name != "posix":
            raise RuntimeError("This launcher currently supports macOS and Linux")
        config_path = args.backend_config.expanduser().resolve()
        if not config_path.is_file():
            raise RuntimeError("Configure Casdoor and run backend/scripts/setup.py first; see deploy/README.md")
        config = tomllib.loads(config_path.read_text())
        if config.get("host") != "0.0.0.0" or config.get("port", 8080) != 8080:
            raise RuntimeError('Set Backend host = "0.0.0.0" and port = 8080 for Docker access')
        if config.get("issuer") != "http://localhost:8000":
            raise RuntimeError("This launcher requires local Casdoor at http://localhost:8000")
        for field in ("service_token_file", "client_secret_file"):
            path = (config_path.parent / Path(config[field]).expanduser()).resolve()
            if not path.is_file():
                raise RuntimeError(f"Missing credential file referenced by {field}")
        oath_config = args.oath_config.expanduser().resolve()
        if not oath_config.is_file():
            raise RuntimeError("Configure ~/.oath/oath.toml and its model credential first")
        runtime = tomllib.loads(oath_config.read_text()).get("services", {})
        ws = f"ws://127.0.0.1:{runtime.get('gateway_port', 8765)}"
        biz = f"http://127.0.0.1:{runtime.get('biz_port', 8766)}"
        if config.get("oath_ws") != ws or config.get("oath_biz") != biz:
            raise RuntimeError("Backend oath_ws/oath_biz must match the local Oath configured ports")
        client_settings = tomllib.loads((ROOT / "apps/client/client.toml").read_text())
        if args.client != "none" and client_settings.get("backend_url", "").rstrip("/") != config["public_url"].rstrip("/"):
            raise RuntimeError("Client client.toml backend_url must match Backend public_url")
        free_port(8080)
        if args.client != "none":
            free_port(1420)
        run(["docker", "info"], cwd=ROOT)
        run(["uv", "sync", "--frozen"], cwd=ROOT / "backend")
        if args.client != "none":
            run(["pnpm", "install", "--frozen-lockfile"], cwd=ROOT / "apps/client")
        run(["docker", "compose", "-f", ROOT / "deploy/auth/compose.yaml", "-p", args.auth_project, "up", "-d"])
        wait_http("http://localhost:8000/.well-known/openid-configuration")
        backend = subprocess.Popen(
            ["uv", "run", "--frozen", "python", "-m", "hymio_backend", "--config", str(config_path)],
            cwd=ROOT / "backend", start_new_session=True,
        )
        children.append(backend)
        wait_http("http://127.0.0.1:8080/health", backend)
        run(["oath", "start", "--config", oath_config, "--auth-mode", "remote",
             "--auth-url", "http://host.docker.internal:8080/internal/auth/verify",
             "--auth-token-file", (config_path.parent / Path(config["service_token_file"]).expanduser()).resolve()])
        if args.client != "none":
            children.append(subprocess.Popen(
                ["pnpm", "dev" if args.client == "web" else "desktop"],
                cwd=ROOT / "apps/client", start_new_session=True,
            ))
        print("Hymio running. Backend: http://localhost:8080 | Web: http://127.0.0.1:1420" if args.client != "none" else "Hymio Backend running: http://localhost:8080", flush=True)
        print("Ctrl+C stops Backend/client. Docker services remain running.", flush=True)
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


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    try:
        main()
    except KeyboardInterrupt:
        pass
    except (RuntimeError, OSError, ValueError, KeyError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        print(f"Startup failed: {error}", file=sys.stderr)
        sys.exit(1)
