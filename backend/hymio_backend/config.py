import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Settings:
    database: Path
    issuer: str
    client_id: str
    client_secret_file: Path
    public_url: str
    callback_url: str
    service_token_file: Path
    origins: tuple[str, ...]
    oath_ws: str
    oath_biz: str
    kits_url: str = "http://127.0.0.1:8090"
    oath_admin_token_file: Path | None = None
    access_seconds: int = 900
    refresh_seconds: int = 2592000
    login_method: str = "account"
    signup_enabled: bool = True
    invitation_codes_file: Path | None = None
    host: str = "127.0.0.1"
    port: int = 8080
    task_parallelism: int = 2
    computer_provider: str = "daytona"
    daytona_key_file: Path | None = None
    daytona_api_url: str = "https://app.daytona.io/api"
    daytona_snapshot: str = ""
    admin_user_ids: tuple[str, ...] = ()
    device_api_targets: tuple[dict, ...] = ()
    e2b_key_file: Path | None = None
    e2b_template: str = "hymio-desktop"
    model_options: tuple[str, ...] = ("MiniMax-M2.7", "MiniMax-M3")
    model_context_windows: dict[str, int] = field(default_factory=dict)
    vision_model: str = "MiniMax-M3"
    native_image_models: tuple[str, ...] = (
        "MiniMax-M3",
        "deepseek-flash",
        "Qwen/Qwen3.8-27B",
        "Qwen/Qwen3-VL-32B-Instruct",
    )
    media_api_base: str = "https://api.minimax.cn/v1"
    media_credential: str = ""
    vault_url: str = "http://127.0.0.1:8200"
    prometheus_url: str = "http://127.0.0.1:19090"
    grafana_url: str = ""
    observability_retention_days: int = 7
    observability_max_events: int = 20000
    vault_role_id_file: Path | None = None
    vault_secret_id_file: Path | None = None
    nostalgia_connections_file: Path | None = None
    connectors_config_file: Path | None = None
    apns_key_file: Path | None = None
    apns_key_id: str = ""
    apns_team_id: str = ""
    apns_bundle_id: str = ""
    apns_environment: str = "production"

    @classmethod
    def load(cls, path):
        path = Path(path).expanduser().resolve()
        data = tomllib.loads(path.read_text())
        if os.environ.get("HYMIO_CONNECTORS_CONFIG_FILE"):
            data["connectors_config_file"] = os.environ["HYMIO_CONNECTORS_CONFIG_FILE"]
        if os.environ.get("HYMIO_PROMETHEUS_URL"):
            data.setdefault("prometheus_url", os.environ["HYMIO_PROMETHEUS_URL"])
        if os.environ.get("HYMIO_KITS_URL"):
            data["kits_url"] = os.environ["HYMIO_KITS_URL"]
        if os.environ.get("HYMIO_APNS_KEY_FILE"):
            data["apns_key_file"] = os.environ["HYMIO_APNS_KEY_FILE"]
        for key, env in (
            ("apns_key_id", "HYMIO_APNS_KEY_ID"),
            ("apns_team_id", "HYMIO_APNS_TEAM_ID"),
            ("apns_bundle_id", "HYMIO_APNS_BUNDLE_ID"),
            ("apns_environment", "HYMIO_APNS_ENVIRONMENT"),
        ):
            if os.environ.get(env):
                data[key] = os.environ[env]
        for key in ("database", "client_secret_file", "service_token_file"):
            file = Path(data[key]).expanduser()
            data[key] = file if file.is_absolute() else path.parent / file
        data["origins"] = tuple(data["origins"])
        if data.get("e2b_key_file"):
            key = Path(data["e2b_key_file"]).expanduser()
            data["e2b_key_file"] = key if key.is_absolute() else path.parent / key
        if data.get("invitation_codes_file"):
            file = Path(data["invitation_codes_file"]).expanduser()
            data["invitation_codes_file"] = file if file.is_absolute() else path.parent / file
        for key in (
            "vault_role_id_file",
            "vault_secret_id_file",
            "daytona_key_file",
            "oath_admin_token_file",
            "connectors_config_file",
            "apns_key_file",
        ):
            if data.get(key):
                file = Path(data[key]).expanduser()
                data[key] = file if file.is_absolute() else path.parent / file
        data["model_options"] = tuple(data.get("model_options", ("MiniMax-M2.7", "MiniMax-M3")))
        from .devices.api_provider import targets_from_config

        if data.get("device_api_targets"):
            data["device_api_targets"] = tuple(
                vars(target)
                for target in targets_from_config(data["device_api_targets"], path.parent)
            )
        if not isinstance(data.get("admin_user_ids", ()), (list, tuple)):
            raise ValueError("admin_user_ids must be a list of product user IDs")
        data["admin_user_ids"] = tuple(data.get("admin_user_ids", ()))
        if data.get("nostalgia_connections_file"):
            file = Path(data["nostalgia_connections_file"]).expanduser()
            data["nostalgia_connections_file"] = file if file.is_absolute() else path.parent / file
        result = cls(**data)
        if not isinstance(result.model_context_windows, dict) or any(
            not isinstance(k, str) or not k or type(v) is not int or v < 4096
            for k, v in result.model_context_windows.items()
        ):
            raise ValueError("model_context_windows requires model IDs and token capacities")
        if not result.model_options or any(
            not isinstance(m, str) or not m.strip() or len(m) > 128 for m in result.model_options
        ):
            raise ValueError("model_options must contain model identifiers")
        if result.computer_provider not in ("daytona", "device_api", "e2b"):
            raise ValueError("computer_provider must be daytona, device_api or e2b")
        if result.computer_provider == "e2b" and not result.e2b_key_file:
            raise ValueError("e2b requires e2b_key_file")
        if (
            result.computer_provider == "e2b"
            and result.e2b_key_file
            and not result.e2b_key_file.read_text().strip()
        ):
            raise ValueError("Missing E2B credential")
        if any(not isinstance(v, str) or not v for v in result.admin_user_ids):
            raise ValueError("admin_user_ids must contain product user IDs")
        endpoint = urlsplit(result.daytona_api_url)
        if (
            endpoint.scheme != "https"
            or not endpoint.hostname
            or endpoint.username
            or endpoint.password
            or endpoint.query
            or endpoint.fragment
        ):
            raise ValueError("daytona_api_url must be HTTPS")
        if result.invitation_codes_file and result.login_method != "account":
            raise ValueError("Invitation registration requires account login")
        if result.login_method not in ("account", "google"):
            raise ValueError("login_method must be account or google")
        if result.access_seconds < 1 or result.refresh_seconds < result.access_seconds:
            raise ValueError("Invalid token lifetimes")
        for url in (
            result.issuer,
            result.public_url,
            result.callback_url,
            result.oath_biz,
            result.kits_url,
            result.media_api_base,
            result.vault_url,
            result.prometheus_url,
        ):
            parsed = urlsplit(url)
            if (
                parsed.scheme not in ("http", "https")
                or not parsed.hostname
                or parsed.username
                or parsed.password
            ):
                raise ValueError("Invalid service URL")
        if result.grafana_url:
            parsed = urlsplit(result.grafana_url)
            if (
                parsed.scheme not in ("http", "https")
                or not parsed.hostname
                or parsed.username
                or parsed.password
            ):
                raise ValueError("Invalid Grafana URL")
        agent = urlsplit(result.oath_ws)
        if (
            agent.scheme not in ("ws", "wss")
            or not agent.hostname
            or agent.username
            or agent.password
        ):
            raise ValueError("oath_ws must be an internal WS(S) service URL")
        public = urlsplit(result.public_url)
        if agent.netloc == public.netloc and agent.path == public.path.rstrip("/") + "/agent/ws":
            raise ValueError("oath_ws must not point back to the Hymio WebSocket proxy")
        if (
            result.login_method != "account"
            and result.callback_url != result.public_url.rstrip("/") + "/auth/callback"
        ):
            raise ValueError("callback_url must be public_url + /auth/callback")
        if not result.client_secret_file.read_text().strip():
            raise ValueError("Missing OIDC client secret")
        if len(result.service_token_file.read_text().strip()) < 32:
            raise ValueError("Service credential must be at least 32 characters")
        if result.oath_admin_token_file and not result.oath_admin_token_file.read_text().strip():
            raise ValueError("Missing Oath administrator credential")
        if result.apns_key_file and not result.apns_key_file.read_text().strip():
            raise ValueError("Missing APNs signing key")
        if result.apns_key_file and not all(
            (result.apns_key_id, result.apns_team_id, result.apns_bundle_id)
        ):
            raise ValueError("APNs requires key ID, team ID and bundle ID")
        if result.apns_environment not in {"sandbox", "production"}:
            raise ValueError("apns_environment must be sandbox or production")
        if type(result.task_parallelism) is not int or not 1 <= result.task_parallelism <= 8:
            raise ValueError("task_parallelism must be between 1 and 8")
        return result
