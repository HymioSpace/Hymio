import tomllib
from dataclasses import dataclass
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
    access_seconds: int = 900
    refresh_seconds: int = 2592000
    login_method: str = "account"
    host: str = "127.0.0.1"
    port: int = 8080
    computer_provider: str = "e2b"
    e2b_key_file: Path | None = None
    e2b_template: str = "hymio-desktop"
    nostalgia_connections_file: Path | None = None

    @classmethod
    def load(cls, path):
        path = Path(path).expanduser().resolve()
        data = tomllib.loads(path.read_text())
        for key in ("database", "client_secret_file", "service_token_file"):
            file = Path(data[key]).expanduser()
            data[key] = file if file.is_absolute() else path.parent / file
        data["origins"] = tuple(data["origins"])
        if data.get("e2b_key_file"):
            key = Path(data["e2b_key_file"]).expanduser()
            data["e2b_key_file"] = key if key.is_absolute() else path.parent / key
        if data.get("nostalgia_connections_file"):
            file = Path(data["nostalgia_connections_file"]).expanduser()
            data["nostalgia_connections_file"] = file if file.is_absolute() else path.parent / file
        result = cls(**data)
        if result.computer_provider != "e2b":
            raise ValueError("Only the e2b computer provider is supported")
        if result.computer_provider == "e2b" and not result.e2b_key_file:
            raise ValueError("e2b requires e2b_key_file")
        if result.e2b_key_file and not result.e2b_key_file.read_text().strip():
            raise ValueError("Missing E2B credential")
        if result.login_method not in ("account", "google"):
            raise ValueError("login_method must be account or google")
        if result.access_seconds < 1 or result.refresh_seconds < result.access_seconds:
            raise ValueError("Invalid token lifetimes")
        for url in (result.issuer, result.public_url, result.callback_url, result.oath_biz):
            parsed = urlsplit(url)
            if (
                parsed.scheme not in ("http", "https")
                or not parsed.hostname
                or parsed.username
                or parsed.password
            ):
                raise ValueError("Invalid service URL")
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
        return result
