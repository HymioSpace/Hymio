"""Generate and manage the single-host cloud stack without shell interpolation."""
import argparse
import ipaddress
import json
import re
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = Path(__file__).resolve().parent / "generated"


def generate(path):
    settings = tomllib.loads(path.read_text())
    domains = [settings[key] for key in ("web_domain", "api_domain", "agent_domain")]
    for domain in domains:
        if not re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?", domain):
            raise ValueError("Domain must be a hostname without scheme, path or port")
    if len(set(domains)) != 3:
        raise ValueError("Use distinct web, API and agent domains")
    config = Path(settings["backend_config_dir"]).expanduser()
    config = (path.parent / config).resolve() if not config.is_absolute() else config.resolve()
    backend = tomllib.loads((config / "hymio.toml").read_text())
    if backend.get("computer_provider") != "e2b":
        raise ValueError("Cloud deployment requires E2B; Docker socket is not mounted")
    if backend.get("host") != "0.0.0.0" or backend.get("port", 8080) != 8080:
        raise ValueError("Backend must listen on 0.0.0.0:8080 inside the container")
    if backend.get("database") != "/data/hymio.sqlite":
        raise ValueError("Set database = /data/hymio.sqlite for the persistent volume")
    web, api, agent = domains
    if backend.get("public_url") != f"https://{api}":
        raise ValueError("Backend public_url must match api_domain with HTTPS")
    if backend.get("oath_ws") != f"wss://{agent}":
        raise ValueError("Backend oath_ws must match agent_domain with WSS")
    bind = str(ipaddress.ip_address(settings.get("backend_internal_bind", "172.17.0.1")))
    if ":" in bind:
        raise ValueError("backend_internal_bind currently requires IPv4")
    ports = [settings.get("oath_ws_port", 8765), settings.get("backend_internal_port", 8080)]
    if any(type(port) is not int or not 1 <= port <= 65535 for port in ports):
        raise ValueError("Ports must be integers between 1 and 65535")
    OUTPUT.mkdir(exist_ok=True, mode=0o700)
    (OUTPUT / "client.toml").write_text(f'backend_url = "https://{api}"\n')
    (OUTPUT / "Caddyfile").write_text(
        f"{web} {{\n root * /srv\n try_files {{path}} /index.html\n file_server\n}}\n"
        f"{api} {{\n reverse_proxy backend:8080\n}}\n"
        f"{agent} {{\n reverse_proxy host.docker.internal:{ports[0]}\n}}\n"
    )
    compose = {
        "name": "hymio-cloud",
        "services": {
            "backend": {
                "build": {"context": str(ROOT), "dockerfile": "deploy/cloud/Backend.Dockerfile"},
                "restart": "unless-stopped",
                "volumes": [f"{config}:/config:ro", "backend-data:/data"],
                "ports": [f"{bind}:{ports[1]}:8080"],
                "extra_hosts": ["host.docker.internal:host-gateway"],
                "security_opt": ["no-new-privileges:true"],
                "cap_drop": ["ALL"],
            },
            "edge": {
                "build": {"context": str(ROOT), "dockerfile": "deploy/cloud/Web.Dockerfile"},
                "restart": "unless-stopped",
                "depends_on": {"backend": {"condition": "service_healthy"}},
                "ports": ["80:80", "443:443", "443:443/udp"],
                "extra_hosts": ["host.docker.internal:host-gateway"],
                "volumes": [
                    f"{OUTPUT / 'Caddyfile'}:/etc/caddy/Caddyfile:ro",
                    "caddy-data:/data", "caddy-config:/config",
                ],
            },
        },
        "volumes": {name: {} for name in ("backend-data", "caddy-data", "caddy-config")},
    }
    target = OUTPUT / "compose.json"
    target.write_text(json.dumps(compose, indent=2) + "\n")
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "start", "stop", "status", "logs"))
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("cloud.local.toml"))
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
        "stop": ["down"], "status": ["ps"], "logs": ["logs", "--tail", "100", "-f"],
    }
    subprocess.run(["docker", "compose", "-f", str(target), *commands[args.command]], check=True)


if __name__ == "__main__":
    main()
