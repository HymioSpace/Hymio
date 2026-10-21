"""One portable private input; generated service credentials stay on this machine."""

import hashlib
import json
import os
import secrets
import tempfile
import tomllib
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
FIELDS = {
    "minimax_api_key",
    "e2b_api_key",
    "daytona_api_key",
    "daytona_api_url",
    "daytona_snapshot",
    "admin_user_ids",
    "computer_provider",
    "device_api_targets",
    "minimax_api_base",
    "models",
    "vision_model",
    "e2b_template",
    "casdoor_port",
    "lan_host",
    "invitation_codes",
}


def private_write(path, text):
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "w") as output:
            output.write(text)
        Path(name).replace(path)
    finally:
        Path(name).unlink(missing_ok=True)


def toml(data):
    """Serialize service tables, including TOML inline tables where needed."""

    def value(item):
        if isinstance(item, dict):
            return (
                "{ "
                + ", ".join(json.dumps(k) + " = " + value(v) for k, v in item.items())
                + " }"
            )
        if isinstance(item, (list, tuple)):
            return "[" + ", ".join(value(v) for v in item) + "]"
        return json.dumps(item, ensure_ascii=False)

    return "\n".join(f"{key} = {value(item)}" for key, item in data.items()) + "\n"


def load(path):
    try:
        source = tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError:
        raise ValueError(
            f"Invalid TOML in {path}; check syntax without publishing its contents"
        ) from None
    path.chmod(0o600)
    if set(source) - FIELDS:
        raise ValueError(
            "Unknown unified configuration fields; compare deploy/config.example.toml"
        )
    for field in FIELDS - {
        "models",
        "casdoor_port",
        "invitation_codes",
        "device_api_targets",
        "admin_user_ids",
    }:
        if field in source and not isinstance(source[field], str):
            raise ValueError(f"{field} must be text")
    source.setdefault(
        "computer_provider", "e2b" if source.get("e2b_api_key") else "daytona"
    )
    if source["computer_provider"] not in ("daytona", "device_api", "e2b"):
        raise ValueError("computer_provider must be daytona, device_api or e2b")
    source.setdefault("admin_user_ids", [])
    if not isinstance(source["admin_user_ids"], list) or any(
        not isinstance(x, str) or not x for x in source["admin_user_ids"]
    ):
        raise ValueError("admin_user_ids must be a list of product user IDs")
    source["daytona_api_key"] = os.environ.get(
        "DAYTONA_API_KEY", source.get("daytona_api_key", "")
    ).strip()
    source.setdefault("daytona_api_url", "https://app.daytona.io/api")
    source.setdefault("daytona_snapshot", "")
    source.setdefault("device_api_targets", [])
    if not isinstance(source["device_api_targets"], list):
        raise TypeError("device_api_targets must be an array of target tables")
    # Resolve paths here so generated service files preserve the original input base.
    sys_path = str(ROOT / "backend")
    import sys

    if sys_path not in sys.path:
        sys.path.insert(0, sys_path)
    from hymio_backend.devices.target_config import targets_from_config

    source["device_api_targets"] = [
        vars(t) for t in targets_from_config(source["device_api_targets"], path.parent)
    ]
    for field, env in (
        ("minimax_api_key", "MINIMAX_API_KEY"),
        ("e2b_api_key", "E2B_API_KEY"),
    ):
        source[field] = os.environ.get(env, source.get(field, "")).strip()
        required = field != "e2b_api_key" or source["computer_provider"] == "e2b"
        if (required and not source[field]) or any(c in source[field] for c in "\r\n"):
            raise ValueError(f"Set {field} in {path} or export {env}")
    source.setdefault("minimax_api_base", "https://api.minimax.cn/v1")
    endpoint = urlsplit(source["minimax_api_base"])
    if (
        endpoint.scheme != "https"
        or not endpoint.hostname
        or endpoint.username
        or endpoint.password
        or endpoint.query
        or endpoint.fragment
    ):
        raise ValueError("minimax_api_base must be an HTTPS API base URL")
    source.setdefault("models", ["MiniMax-M2.7", "MiniMax-M3"])
    source.setdefault("vision_model", "MiniMax-M3")
    source.setdefault("e2b_template", "hymio-desktop")
    source.setdefault("casdoor_port", 8000)
    source.setdefault("lan_host", "off")
    source.setdefault("invitation_codes", [])
    for key in ("models", "invitation_codes"):
        if not isinstance(source[key], list) or any(
            not isinstance(v, str)
            or not v.strip()
            or len(v) > 128
            or "\n" in v
            or "\r" in v
            for v in source[key]
        ):
            raise ValueError(f"{key} must be a list of nonempty short strings")
    if (
        not source["models"]
        or not source["vision_model"].strip()
        or not source["e2b_template"].strip()
    ):
        raise ValueError("models, vision_model and e2b_template must not be empty")
    port = source["casdoor_port"]
    if (
        type(port) is not int
        or not 1024 <= port <= 65535
        or port in (8080, 1420, 8200, 8765, 8766, 8770, 8771, 8772, 8773)
    ):
        raise ValueError(
            "casdoor_port must be a free port from 1024 to 65535, distinct from Hymio/Oath ports"
        )
    # Reject invalid network input before any service or generated state is changed.
    from local_network import lan_address

    lan_address(source["lan_host"])
    return source


def runtime_for(path):
    return path.parent / (
        "local-" + hashlib.sha256(str(path.resolve()).encode()).hexdigest()[:10]
    )


def prepare(path):
    settings = load(path)
    runtime = runtime_for(path)
    runtime.mkdir(parents=True, mode=0o700, exist_ok=True)
    runtime.chmod(0o700)
    identity = runtime / "identity.json"
    if not identity.exists():
        if (runtime / "casdoor-compose.json").exists() or (
            runtime / "backend/hymio.toml"
        ).exists():
            raise ValueError(
                "Generated identity is missing from an existing runtime; restore its backup instead of regenerating credentials"
            )
        private_write(
            identity,
            json.dumps(
                {
                    key: secrets.token_urlsafe(36)
                    for key in (
                        "client_id",
                        "client_secret",
                        "service_token",
                        "admin_password",
                        "oath_token",
                        "rabbit_password",
                    )
                }
            ),
        )
    credentials = json.loads(identity.read_text())
    backend_dir = runtime / "backend"
    oath_dir = runtime / "oath"
    backend_dir.mkdir(mode=0o700, exist_ok=True)
    oath_dir.mkdir(mode=0o700, exist_ok=True)
    for name, data in (
        ("casdoor-client-secret", credentials["client_secret"]),
        ("oath-auth-token", credentials["service_token"]),
        ("e2b-api-key", settings["e2b_api_key"]),
        ("daytona-api-key", settings["daytona_api_key"]),
        ("invitation-codes", "\n".join(settings["invitation_codes"])),
    ):
        private_write(backend_dir / "private" / name, data + "\n")
    issuer = f"http://localhost:{settings['casdoor_port']}"
    backend = tomllib.loads((ROOT / "backend/hymio.example.toml").read_text())
    backend.update(
        host="0.0.0.0",
        issuer=issuer,
        client_id=credentials["client_id"],
        model_options=settings["models"],
        vision_model=settings["vision_model"],
        e2b_template=settings["e2b_template"],
        computer_provider=settings["computer_provider"],
        daytona_key_file="./private/daytona-api-key",
        daytona_api_url=settings["daytona_api_url"],
        daytona_snapshot=settings["daytona_snapshot"],
        admin_user_ids=settings["admin_user_ids"],
        device_api_targets=settings["device_api_targets"],
    )
    if settings["invitation_codes"]:
        backend["invitation_codes_file"] = "./private/invitation-codes"
    private_write(backend_dir / "hymio.toml", toml(backend))
    # Only Oath's public configuration contract is used, without importing its implementation.
    oath = {
        "data_root": "./data",
        "services": {
            "internal_token": credentials["oath_token"],
            "rabbitmq_user": "oath",
            "rabbitmq_password": credentials["rabbit_password"],
            "broker_url": f"amqp://oath:{credentials['rabbit_password']}@127.0.0.1:5672/%2F",
        },
        "agent": {
            "provider": {
                "model": settings["models"][0],
                "api_base": settings["minimax_api_base"],
                "credential": "model/minimax-"
                + hashlib.sha256(settings["minimax_api_key"].encode()).hexdigest()[:16],
                "import_env": "MINIMAX_API_KEY",
                "timeout_seconds": 120,
            }
        },
    }
    # start.py extends an explicit [agent] table; model parameters remain in a child table.
    private_write(
        oath_dir / "oath.toml",
        toml({"data_root": oath["data_root"]})
        + "\n[services]\n"
        + toml(oath["services"])
        + "\n[agent]\nmax_output_tokens = 8192\n\n[agent.provider]\n"
        + toml(oath["agent"]["provider"]),
    )
    private_write(runtime / "network.toml", toml({"lan_host": settings["lan_host"]}))
    return settings, runtime, credentials


def container_readable(runtime, oath_config, tools_dir):
    """Non-root Linux containers can read only their explicitly mounted bootstrap files.

    A 0700 ancestor protects these files from other host users; the input file and Vault
    administrator material remain 0600. AppRole placeholders preserve this mode when Oath
    writes them before starting workers. No chown/sudo or writable Docker socket is needed.
    """
    private = runtime / "oath/data/private"
    private.mkdir(parents=True, mode=0o700, exist_ok=True)
    private.chmod(0o700)
    for name in ("vault-role-id", "vault-secret-id"):
        path = private / name
        if not path.exists():
            private_write(path, "")
        path.chmod(0o644)
    for path in (
        oath_config,
        tools_dir / "_connection.local",
        runtime / "backend/private/oath-auth-token",
    ):
        path.chmod(0o644)
    # Only the tools directory is mounted, not its private 0700 runtime ancestor.
    tools_dir.chmod(0o755)
