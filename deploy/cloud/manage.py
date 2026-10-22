"""Generate and manage the single-host cloud stack without shell interpolation."""

import argparse
import ipaddress
import json
import re
import subprocess
import tomllib
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = Path(__file__).resolve().parent / "generated"


def generate(path):
    settings = tomllib.loads(path.read_text())
    domains = [settings[key] for key in ("web_domain", "api_domain")]
    if settings.get("agent_domain"):
        domains.append(settings["agent_domain"])
    for domain in domains:
        if not re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?", domain):
            raise ValueError("Domain must be a hostname without scheme, path or port")
    if settings.get("agent_domain") in domains[:2]:
        raise ValueError("Legacy agent domain must be separate from Web and API")
    config = Path(settings["backend_config_dir"]).expanduser()
    config = (
        (path.parent / config).resolve()
        if not config.is_absolute()
        else config.resolve()
    )
    backend = tomllib.loads((config / "hymio.toml").read_text())
    if backend.get("computer_provider") not in ("daytona", "e2b", "device_api"):
        raise ValueError("Cloud computer_provider must be daytona, device_api or e2b")
    if backend.get("host") != "0.0.0.0" or backend.get("port", 8080) != 8080:
        raise ValueError("Backend must listen on 0.0.0.0:8080 inside the container")
    if backend.get("database") != "/data/hymio.sqlite":
        raise ValueError("Set database = /data/hymio.sqlite for the persistent volume")
    if backend.get("admin_user_ids"):
        admin_token = backend.get("oath_admin_token_file")
        if not isinstance(admin_token, str) or not admin_token:
            raise ValueError(
                "Set oath_admin_token_file to the Oath internal token for admin trace reads"
            )
        admin_token_path = Path(admin_token).expanduser()
        if not admin_token_path.is_absolute():
            admin_token_path = config / admin_token_path
        if not admin_token_path.is_file() or not admin_token_path.read_text().strip():
            raise ValueError(
                "oath_admin_token_file must contain the Oath internal token"
            )
    web, api = domains[:2]
    agent = settings.get("agent_domain")
    if backend.get("public_url") != f"https://{api}":
        raise ValueError("Backend public_url must match api_domain with HTTPS")
    upstream = urlsplit(backend.get("oath_ws", ""))
    if (
        upstream.scheme not in ("ws", "wss")
        or not upstream.hostname
        or upstream.username
        or upstream.password
    ):
        raise ValueError("Backend oath_ws must be a reachable private WS(S) upstream")
    if upstream.netloc == api and upstream.path == "/agent/ws":
        raise ValueError("Oath upstream must not point back to Backend")
    bind = str(
        ipaddress.ip_address(settings.get("backend_internal_bind", "172.17.0.1"))
    )
    if ":" in bind:
        raise ValueError("backend_internal_bind currently requires IPv4")
    ports = [
        settings.get("oath_ws_port", 8765),
        settings.get("backend_internal_port", 8080),
    ]
    if any(type(port) is not int or not 1 <= port <= 65535 for port in ports):
        raise ValueError("Ports must be integers between 1 and 65535")
    OUTPUT.mkdir(exist_ok=True, mode=0o700)
    (OUTPUT / "client.toml").write_text(f'backend_url = "https://{api}"\n')
    web_routes = " root * /srv\n try_files {path} /index.html\n file_server\n"
    private_routes = (
        " @private path /internal/*\n handle @private {\n  respond 404\n }\n"
    )
    if web == api:
        routes = (
            f"{web} {{\n{private_routes}"
            " handle /admin/api/* {\n  reverse_proxy backend:8080\n }\n"
            " handle_path /admin/* {\n  root * /srv/admin\n"
            "  try_files {path} /index.html\n  file_server\n }\n"
            " @backend path /health /auth/* /agent/* /oath-biz/* /devices /devices/* "
            "/tasks /attachments /attachments/* /settings/* /telemetry/*\n"
            " handle @backend {\n  reverse_proxy backend:8080\n }\n"
            f" handle {{\n{web_routes} }}\n}}\n"
        )
    else:
        routes = (
            f"{web} {{\n handle /admin/api/* {{\n  reverse_proxy backend:8080\n }}\n"
            " handle_path /admin/* {\n  root * /srv/admin\n"
            "  try_files {path} /index.html\n  file_server\n }\n"
            f" handle {{\n{web_routes} }}\n}}\n"
            f"{api} {{\n{private_routes} reverse_proxy backend:8080\n}}\n"
        )
    if agent:
        routes += f"{agent} {{\n reverse_proxy host.docker.internal:{ports[0]}\n}}\n"
    (OUTPUT / "Caddyfile").write_text(routes)
    compose = {
        "name": "hymio-cloud",
        "services": {
            "backend": {
                "build": {
                    "context": str(ROOT),
                    "dockerfile": "deploy/cloud/Backend.Dockerfile",
                },
                "restart": "unless-stopped",
                "volumes": [f"{config}:/config:ro", "backend-data:/data"],
                "ports": [f"{bind}:{ports[1]}:8080"],
                "extra_hosts": ["host.docker.internal:host-gateway"],
                "security_opt": ["no-new-privileges:true"],
                "cap_drop": ["ALL"],
            },
            "edge": {
                "build": {
                    "context": str(ROOT),
                    "dockerfile": "deploy/cloud/Web.Dockerfile",
                },
                "restart": "unless-stopped",
                "depends_on": {"backend": {"condition": "service_healthy"}},
                "ports": ["80:80", "443:443", "443:443/udp"],
                "extra_hosts": ["host.docker.internal:host-gateway"],
                "volumes": [
                    f"{OUTPUT / 'Caddyfile'}:/etc/caddy/Caddyfile:ro",
                    "caddy-data:/data",
                    "caddy-config:/config",
                ],
            },
        },
        "volumes": {
            name: {} for name in ("backend-data", "caddy-data", "caddy-config")
        },
    }
    runtime_network = settings.get("runtime_network")
    (OUTPUT / "hymio-metrics-targets.json").write_text(
        json.dumps(
            [
                {
                    "targets": [
                        "backend:8080"
                        if runtime_network
                        else "host.docker.internal:8080"
                    ]
                }
            ]
        )
        + "\n"
    )
    compose["services"]["backend"]["environment"] = {
        "HYMIO_PROMETHEUS_URL": settings.get("prometheus_url")
        or (
            "http://prometheus:9090"
            if runtime_network
            else "http://host.docker.internal:19090"
        )
    }
    if runtime_network:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", runtime_network):
            raise ValueError("Invalid runtime network name")
        compose["networks"] = {"runtime": {"external": True, "name": runtime_network}}
        compose["services"]["backend"]["networks"] = ["default", "runtime"]
        compose["services"]["backend"].pop("ports")
    if settings.get("managed_identity", False):
        compose["services"]["identity-permissions"] = {
            "image": "busybox:1.37.0",
            "command": ["chown", "1000:1000", "/data"],
            "volumes": ["identity-data:/data"],
        }
        compose["services"]["identity"] = {
            "image": "casbin/casdoor:4.20.0",
            "restart": "unless-stopped",
            "depends_on": {
                "identity-permissions": {"condition": "service_completed_successfully"}
            },
            "ports": ["127.0.0.1:8000:8000"],
            "environment": {
                "driverName": "sqlite",
                "dataSourceName": "file:/data/casdoor.db?cache=shared",
                "dbName": "casdoor",
                "origin": "http://identity:8000",
            },
            "volumes": ["identity-data:/data"],
        }
        compose["volumes"]["identity-data"] = {}
    target = OUTPUT / "compose.json"
    target.write_text(json.dumps(compose, indent=2) + "\n")
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=("prepare", "start", "stop", "status", "logs")
    )
    parser.add_argument(
        "--config", type=Path, default=Path(__file__).with_name("cloud.local.toml")
    )
    args = parser.parse_args()
    target = OUTPUT / "compose.json"
    if args.command in ("prepare", "start"):
        target = generate(args.config.expanduser().resolve())
    elif not target.exists():
        parser.error("Run prepare or start first")
    if args.command == "prepare":
        print(f"Generated {target}")
        return
    commands = {
        "start": ["up", "--build", "-d", "--wait", "--wait-timeout", "180"],
        "stop": ["down"],
        "status": ["ps"],
        "logs": ["logs", "--tail", "100", "-f"],
    }
    subprocess.run(
        ["docker", "compose", "-f", str(target), *commands[args.command]], check=True
    )


if __name__ == "__main__":
    main()
