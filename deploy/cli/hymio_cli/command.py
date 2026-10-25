"""Install and operate the source-based Hymio local stack."""

import argparse
import fcntl
import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

from .process import alive, health, save, stop


def read(path):
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def options(args, root, previous):
    defaults = {
        "client": "web",
        "backend_config": str(root / "backend/hymio.toml"),
        "oath_config": str(Path.home() / ".oath/oath.toml"),
        "auth_project": "hymio-auth",
        "deploy_config": str(root / "deploy/local.toml"),
        "config": None,
    }
    legacy = any(
        getattr(args, k, None)
        for k in ("backend_config", "oath_config", "auth_project", "deploy_config")
    )
    default_config = (
        args.home.expanduser() / "config.toml"
        if getattr(args, "home", None)
        else Path.home() / ".hymio/config.toml"
    )
    if default_config.exists() and not legacy:
        defaults["config"] = str(default_config.resolve())
    if legacy:
        previous = {**previous, "config": None}
    settings = {}
    for key, default in defaults.items():
        explicit = getattr(args, key, None)
        settings[key] = (
            str(explicit) if explicit is not None else previous.get(key, default)
        )
        if key == "config" and not settings[key] and not legacy:
            settings[key] = default
    return settings


def start(home, root, args, state, restarting=False):
    settings = options(
        args, root, state.get("settings", read(home / "preferences.json"))
    )
    if alive(state):
        if settings != state["settings"]:
            raise RuntimeError(
                "A managed instance uses different settings. Use hymio restart with your options."
            )
        backend, web = health(settings["client"])
        print(
            "Hymio already running."
            if backend
            and web
            and read(home / "ready.json").get("instance") == state["instance"]
            else "Hymio is running but not ready; use status or logs."
        )
        return
    backend, web = health(settings["client"])
    if backend or (settings["client"] != "none" and web):
        if backend and web and not restarting:
            print(
                "Existing Hymio services are available: http://127.0.0.1:1420"
                if settings["client"] != "none"
                else "Existing Backend: http://127.0.0.1:8080"
            )
            print(
                "Not managed by this command; no processes were changed. Stop their original launchers before CLI management."
            )
            save(home / "preferences.json", settings)
            return
        raise RuntimeError(
            "A service is already responding on 8080/1420. No process was stopped; close its original launcher first."
        )
    instance = uuid.uuid4().hex
    command = [
        sys.executable,
        str(root / "deploy/start.py"),
        "--instance",
        instance,
        "--ready-file",
        str(home / "ready.json"),
    ]
    for key, value in settings.items():
        if value is None or (
            settings.get("config")
            and key
            in ("backend_config", "oath_config", "auth_project", "deploy_config")
        ):
            continue
        command.extend(["--" + key.replace("_", "-"), value])
    log = home / "hymio.log"
    with log.open("ab") as output:
        log.chmod(0o600)
        output.write(f"\n--- Starting Hymio {time.ctime()} ---\n".encode())
        output.flush()
        child = subprocess.Popen(
            command,
            cwd=root,
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    state = {
        "pid": child.pid,
        "instance": instance,
        "root": str(root),
        "settings": settings,
    }
    save(home / "state.json", state)
    save(home / "preferences.json", settings)
    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        if child.poll() is not None:
            raise RuntimeError(f"Startup failed. Run hymio logs or inspect {log}")
        if read(home / "ready.json").get("instance") == instance and all(
            health(settings["client"])
        ):
            ready = read(home / "ready.json")
            print(
                "Hymio ready: "
                + ready.get(
                    "web_url" if settings["client"] != "none" else "backend_url",
                    "http://127.0.0.1:8080",
                )
            )
            print(
                "iPhone Backend: " + ready.get("backend_url", "http://127.0.0.1:8080")
            )
            return
        time.sleep(0.5)
    raise RuntimeError(
        "Startup is still in progress. Use hymio status / logs; do not launch a second copy."
    )


def doctor(home):
    state = read(home / "state.json")
    settings = state.get("settings", {})
    unified = bool(settings.get("config"))
    print(f"Configuration mode: {'unified' if unified else 'legacy'}")
    if unified:
        path = Path(settings["config"]).expanduser()
        print(f"Editable input: {path}")
        runtime = path.parent / "local-" + hashlib.sha256(
            str(path.resolve()).encode()
        ).hexdigest()[:10]
        print(f"Generated Backend config: {runtime / 'backend/hymio.toml'} (do not edit)")
        print(f"Generated Oath config: {runtime / 'oath/oath.toml'} (do not edit)")
        print(f"Private credentials: {runtime / 'backend/private'} (do not copy separately)")
    else:
        print(f"Editable Backend config: {settings.get('backend_config', 'not recorded')}")
        print(f"Editable Oath config: {settings.get('oath_config', 'not recorded')}")
        print(
            "Editable network overlay: "
            + str(settings.get("deploy_config", "not recorded"))
        )
        print("Generated Backend overlay: backend/hymio-media.local.toml (do not edit)")
        print("Migration: create ~/.hymio/config.toml for future unified installs;")
        print("existing accounts, history and identity data require a separate migration.")
    print(f"Manager state: {home / 'state.json'}")
    print(f"Launch log: {home / 'hymio.log'}")
    backend, web = health(settings.get("client", "web"))
    print(f"Backend health: {'ready' if backend else 'unavailable'}")
    print(f"Client health: {'ready' if web else 'unavailable'}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("init", "start", "stop", "restart", "status", "logs", "doctor"),
    )
    parser.add_argument("--home", type=Path, default=Path.home() / ".hymio")
    parser.add_argument("--client", choices=("web", "desk", "none"))
    parser.add_argument(
        "--backend-config", type=lambda p: str(Path(p).expanduser().resolve())
    )
    parser.add_argument(
        "--oath-config", type=lambda p: str(Path(p).expanduser().resolve())
    )
    parser.add_argument(
        "--config",
        type=lambda p: str(Path(p).expanduser().resolve()),
        help="Single portable deployment configuration",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Initialize from environment variables",
    )
    parser.add_argument("--auth-project")
    parser.add_argument(
        "--deploy-config", type=lambda p: str(Path(p).expanduser().resolve())
    )
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--follow", "-f", action="store_true")
    args = parser.parse_args()
    try:
        if os.name != "posix":
            raise RuntimeError("The local manager supports macOS/Linux only")
        if args.timeout <= 0:
            raise ValueError("--timeout must be positive")
        home = args.home.expanduser().resolve()
        home.mkdir(mode=0o700, parents=True, exist_ok=True)
        if args.config and any(
            (
                args.backend_config,
                args.oath_config,
                args.auth_project,
                args.deploy_config,
            )
        ):
            raise ValueError(
                "Use --config or legacy service/deployment overrides, not both"
            )
        if args.command == "logs":
            log = home / "hymio.log"
            if not log.exists():
                print("No managed launch log yet.")
                return
            subprocess.run(
                ["tail", *(["-f"] if args.follow else []), "-n", "100", str(log)],
                check=True,
            )
            return
        if args.command == "doctor":
            doctor(home)
            return
        if args.command == "status":
            state = read(home / "state.json")
            settings = state.get("settings", {"client": "web"})
            backend, web = health(settings["client"])
            print(
                "Manager: "
                + (
                    "running"
                    if alive(state)
                    else "stopped (existing services may be unmanaged)"
                )
            )
            print("Backend: " + ("ready" if backend else "unavailable"))
            if settings["client"] != "none":
                print(
                    "Client: "
                    + (
                        "ready — "
                        + read(home / "ready.json").get(
                            "web_url", "http://127.0.0.1:1420"
                        )
                        if web
                        else "unavailable"
                    )
                )
            if read(home / "ready.json").get("backend_url"):
                print(
                    "iPhone Backend: "
                    + read(home / "ready.json").get("backend_url", "see hymio logs")
                )
            print(f"Log: {home / 'hymio.log'}")
            return
        with (home / "command.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError(
                    "Another Hymio lifecycle command is in progress"
                ) from None
            state = read(home / "state.json")
            if args.command in ("stop", "restart"):
                was_running = alive(state)
                stop(state)
                if args.command == "stop" and not was_running:
                    print(
                        "No managed instance. Existing unmanaged services were left untouched."
                    )
                    return
                if args.command == "stop":
                    print(
                        "Managed Backend/Kit Host/client stopped. Oath, Casdoor and E2B remain running."
                    )
                    return
            installation = read(home / "installation.json")
            root = (
                Path(installation.get("root", state.get("root", "")))
                .expanduser()
                .resolve()
            )
            if (
                not installation
                and not state.get("root")
                or not (root / "deploy/start.py").is_file()
            ):
                raise RuntimeError(
                    "Run bash scripts/hymio-install from the source checkout first"
                )
            if args.command == "init":
                if alive(state):
                    raise RuntimeError(
                        "Stop the managed launcher before initializing a different configuration"
                    )
                subprocess.run(
                    [
                        sys.executable,
                        str(root / "deploy/init.py"),
                        "--config",
                        args.config or str(home / "config.toml"),
                        *(["--non-interactive"] if args.non_interactive else []),
                    ],
                    check=True,
                )
                settings = options(args, root, read(home / "preferences.json"))
                settings["config"] = args.config or str(home / "config.toml")
                save(home / "preferences.json", settings)
                return
            start(home, root, args, state, restarting=args.command == "restart")
    except KeyboardInterrupt:
        print("\nUse hymio status to check background services.")
    except (RuntimeError, ValueError, OSError, subprocess.SubprocessError) as error:
        print(f"Hymio: {error}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
