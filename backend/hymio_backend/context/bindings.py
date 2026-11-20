import hashlib
import hmac
import json
import os
import sqlite3
import threading
from pathlib import Path
from urllib.parse import quote, urlsplit

import httpx
from cryptography.fernet import Fernet


class ContextBindingError(RuntimeError):
    pass


class ContextBindings:
    """Per-user Nostalgia credentials provisioned with the Hymio account."""

    def __init__(self, settings):
        self.settings = settings
        self.path = Path(settings.database)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        key_path = self.path.with_suffix(".context.key")
        try:
            fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(fd, "wb") as file:
                file.write(Fernet.generate_key())
        self.cipher = Fernet(key_path.read_bytes().strip())
        self._lock = threading.Lock()
        with self._connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS context_bindings("
                "user_id TEXT PRIMARY KEY,url TEXT NOT NULL,token TEXT NOT NULL,"
                "created_at REAL NOT NULL)"
            )

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        return db

    def get(self, user_id):
        with self._connect() as db:
            row = db.execute(
                "SELECT url,token FROM context_bindings WHERE user_id=?", (user_id,)
            ).fetchone()
        if not row:
            return None
        try:
            token = self.cipher.decrypt(row["token"].encode()).decode()
        except Exception as exc:
            raise ContextBindingError("Stored context credential is invalid") from exc
        return row["url"], token

    def ensure(self, user_id):
        with self._lock:
            existing = self.get(user_id)
            if existing:
                return True
            static = self._static_credentials(user_id)
            url = static[0] if static else self._provisioning_url()
            service_file = Path(self.settings.service_token_file)
            try:
                service_token = service_file.read_text().strip()
            except OSError as exc:
                raise ContextBindingError("Provisioning credential unavailable") from exc
            if not service_token:
                raise ContextBindingError("Provisioning credential is empty")
            if static:
                # Migrate the legacy token in place so removing the JSON fallback later cannot
                # break an existing account.
                token = static[1]
            else:
                # Deterministic provisioning makes retries and multi-worker startup converge on
                # the same credential instead of racing with different random tokens.
                token = hmac.new(
                    service_token.encode(),
                    b"hymio-nostalgia-context:" + user_id.encode(),
                    hashlib.sha256,
                ).hexdigest()
            try:
                response = httpx.put(
                    url + "/v1/admin/tokens/" + quote(user_id, safe=""),
                    headers={"Authorization": "Bearer " + service_token},
                    json={"token": token},
                    timeout=5,
                    trust_env=False,
                )
                response.raise_for_status()
            except httpx.HTTPError as exc:
                raise ContextBindingError("Context provisioning failed") from exc
            encrypted = self.cipher.encrypt(token.encode()).decode()
            with self._connect() as db:
                db.execute(
                    "INSERT INTO context_bindings(user_id,url,token,created_at) "
                    "VALUES(?,?,?,strftime('%s','now')) "
                    "ON CONFLICT(user_id) DO UPDATE SET url=excluded.url,token=excluded.token",
                    (user_id, url, encrypted),
                )
            return True

    def _static_credentials(self, user_id):
        path = getattr(self.settings, "nostalgia_connections_file", None)
        if not path:
            return None
        try:
            path = Path(path)
            entry = json.loads(path.read_text())["users"][user_id]
            url = str(entry["url"]).rstrip("/")
            parsed = urlsplit(url)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("Invalid static context URL")
            token_file = Path(entry["token_file"])
            if not token_file.is_absolute():
                token_file = path.parent / token_file
            token = token_file.read_text().strip()
            if len(token) < 16:
                raise ValueError("Invalid static context credential")
            return url, token
        except (OSError, KeyError, TypeError, ValueError):
            return None

    def _provisioning_url(self):
        configured = getattr(self.settings, "nostalgia_url", "")
        if configured:
            parsed = urlsplit(configured)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
            ):
                raise ContextBindingError("Context provisioning URL is invalid")
            return configured.rstrip("/")
        path = getattr(self.settings, "nostalgia_connections_file", None)
        if path:
            try:
                users = json.loads(Path(path).read_text()).get("users", {})
                first = next(iter(users.values()))
                return str(first["url"]).rstrip("/")
            except (OSError, KeyError, StopIteration, TypeError, ValueError):
                pass
        raise ContextBindingError("Context provisioning URL is not configured")
