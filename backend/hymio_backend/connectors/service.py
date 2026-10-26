import asyncio
import base64
import hashlib
import json
import logging
import math
import secrets
import time
from pathlib import Path
from urllib.parse import urlencode

import httpx

from ..context.client import ContextError, NostalgiaClient
from .catalog import PROVIDERS, ConnectorError
from .providers import normalize_native, pull_dida, pull_gmail, request
from .store import ConnectorStore, encode

_log = logging.getLogger(__name__)


class ConnectorService:
    def __init__(self, settings, sessions, *, client=None, context=None):
        self.settings = settings
        self.store = ConnectorStore(sessions)
        self.http = client or httpx.AsyncClient(timeout=20, follow_redirects=False, trust_env=False)
        self.context = context or NostalgiaClient(settings)

    def registration(self, provider):
        path = getattr(self.settings, "connectors_config_file", None)
        if not path:
            return None
        try:
            value = json.loads(Path(path).read_text()).get(provider, {})
            if not all(
                isinstance(value.get(k), str) and value[k].strip()
                for k in ("client_id", "client_secret")
            ):
                return None
            return value
        except (OSError, ValueError, AttributeError):
            return None

    def catalog(self):
        return [
            {k: p[k] for k in ("id", "name", "summary", "transport", "platforms", "permissions")}
            | {"configured": p["transport"] == "device" or self.registration(p["id"]) is not None}
            for p in PROVIDERS.values()
        ]

    def callback_url(self, provider):
        return self.settings.public_url.rstrip("/") + "/connectors/oauth/" + provider + "/callback"

    def authorize(self, uid, cid):
        with self.store.transaction() as db:
            row = self.store.owned(db, uid, cid)
            provider = row["provider"]
            if PROVIDERS[provider]["transport"] != "oauth":
                raise ConnectorError("use_ios_permissions")
            registration = self.registration(provider)
            if not registration:
                raise ConnectorError("provider_not_configured", 503)
            state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
            db.execute(
                "DELETE FROM connector_flows WHERE expires<? OR connection_id=?", (time.time(), cid)
            )
            db.execute(
                "INSERT INTO connector_flows VALUES(?,?,?,?,?)",
                (hashlib.sha256(state.encode()).hexdigest(), cid, uid, verifier, time.time() + 600),
            )
            params = {
                "response_type": "code",
                "client_id": registration["client_id"],
                "redirect_uri": self.callback_url(provider),
                "scope": PROVIDERS[provider]["scope"],
                "state": state,
            }
            if provider == "gmail":
                challenge = (
                    base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
                    .decode()
                    .rstrip("=")
                )
                params.update(
                    access_type="offline",
                    prompt="consent",
                    code_challenge=challenge,
                    code_challenge_method="S256",
                )
            return {"url": PROVIDERS[provider]["authorize"] + "?" + urlencode(params)}

    async def callback(self, provider, state, code, denied=False):
        if provider not in PROVIDERS or not isinstance(state, str) or not 16 <= len(state) <= 256:
            raise ConnectorError("authorization_expired")
        with self.store.transaction() as db:
            key = hashlib.sha256(state.encode()).hexdigest()
            row = db.execute(
                "SELECT * FROM connector_flows WHERE state_hash=? AND expires>?", (key, time.time())
            ).fetchone()
            if not row:
                raise ConnectorError("authorization_expired")
            row = dict(row)
            connection = self.store.owned(db, row["user_id"], row["connection_id"])
            if connection["provider"] != provider or not connection["enabled"]:
                raise ConnectorError("authorization_expired")
            generation = connection["generation"]
            db.execute("DELETE FROM connector_flows WHERE state_hash=?", (key,))
        if denied or not code:
            raise ConnectorError("authorization_cancelled")
        registration = self.registration(provider)
        if not registration:
            raise ConnectorError("provider_not_configured", 503)
        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.callback_url(provider),
        }
        options = {}
        if provider == "gmail":
            payload.update(
                client_id=registration["client_id"],
                client_secret=registration["client_secret"],
                code_verifier=row["verifier"],
            )
        else:
            options["auth"] = httpx.BasicAuth(
                registration["client_id"], registration["client_secret"]
            )
        value = await request(
            self.http, "POST", PROVIDERS[provider]["token"], data=payload, **options
        )
        if not isinstance(value.get("access_token"), str):
            raise ConnectorError("token_exchange_failed", 503)
        if value.get("scope") and PROVIDERS[provider]["scope"] not in value["scope"].split():
            raise ConnectorError("required_scope_not_granted", 409)
        value["expires_at"] = time.time() + float(value.get("expires_in", 180 * 86400))
        with self.store.transaction() as db:
            current = self.store.owned(db, row["user_id"], row["connection_id"])
            if current["generation"] != generation or not current["enabled"]:
                raise ConnectorError("authorization_expired", 409)
            db.execute(
                "UPDATE connections SET credentials=?,state='queued',next_sync=?,error=''"
                " WHERE id=?",
                (
                    self.store.cipher.encrypt(encode(value).encode()).decode(),
                    time.time(),
                    row["connection_id"],
                ),
            )

    async def access(self, row):
        value = json.loads(self.store.cipher.decrypt(row["credentials"].encode()))
        if value.get("expires_at", 0) > time.time() + 60:
            return value
        if row["provider"] != "gmail" or not value.get("refresh_token"):
            raise ConnectorError("reconnect_required", 409)
        registration = self.registration("gmail")
        if not registration:
            raise ConnectorError("provider_not_configured", 503)
        refreshed = await request(
            self.http,
            "POST",
            PROVIDERS["gmail"]["token"],
            data={
                "grant_type": "refresh_token",
                "refresh_token": value["refresh_token"],
                "client_id": registration["client_id"],
                "client_secret": registration["client_secret"],
            },
        )
        value.update(refreshed)
        value["expires_at"] = time.time() + float(refreshed.get("expires_in", 3600))
        return value

    def ingest(self, uid, cid, data):
        with self.store.transaction() as db:
            row = self.store.owned(db, uid, cid)
        if (
            PROVIDERS[row["provider"]]["transport"] != "device"
            or data.get("device_id") != row["device_id"]
        ):
            raise ConnectorError("device_mismatch", 403)
        if data.get("consent") is not True:
            raise ConnectorError("upload_consent_required")
        captured = data.get("captured_at")
        if (
            type(captured) not in (int, float)
            or not math.isfinite(captured)
            or not 0 < captured <= time.time() + 60
        ):
            raise ConnectorError("invalid_capture_time")
        items, reconciliation = normalize_native(row["provider"], data)
        checkpoint = {
            "captured_at": captured,
            "fingerprint": hashlib.sha256(encode(data).encode()).hexdigest(),
        }
        return self.store.apply(uid, cid, items, checkpoint, reconcile=reconciliation)

    async def collect(self):
        row = await asyncio.to_thread(self.store.claim)
        if not row:
            return False
        try:
            async with asyncio.timeout(240):
                credentials = await self.access(row)
                adapter = pull_gmail if row["provider"] == "gmail" else pull_dida
                items, checkpoint = await adapter(
                    self.http, credentials["access_token"], json.loads(row["checkpoint"])
                )
                await asyncio.to_thread(
                    self.store.apply,
                    row["user_id"],
                    row["id"],
                    items,
                    checkpoint,
                    lease=row["lease"],
                    generation=row["generation"],
                    credentials=credentials,
                )
        except ConnectorError as exc:
            await asyncio.to_thread(self.store.failed, row, exc.code)
        except Exception as exc:
            _log.warning("Connector collection failed: %s", type(exc).__name__)
            await asyncio.to_thread(self.store.failed, row, "upstream_unavailable")
        return True

    def project(self):
        # One worker owns projection. Never send a later revision while its predecessor is pending.
        with self.store.transaction() as db:
            rows = [
                dict(x)
                for x in db.execute(
                    "SELECT c.*,n.provider FROM connector_changes c JOIN connections n ON "
                    "n.id=c.connection_id WHERE c.delivered=0 AND c.retry_at<=? AND NOT "
                    "EXISTS (SELECT 1 FROM connector_changes p WHERE "
                    "p.connection_id=c.connection_id AND p.external_id=c.external_id AND "
                    "p.id<c.id AND p.delivered=0) ORDER BY c.id LIMIT 10",
                    (time.time(),),
                )
            ]
        for row in rows:
            try:
                with self.store.transaction() as db:
                    previous = db.execute(
                        "SELECT record_id FROM connector_changes WHERE connection_id=? AND "
                        "external_id=? AND id<? AND record_id IS NOT NULL ORDER BY id DESC LIMIT "
                        "1",
                        (row["connection_id"], row["external_id"], row["id"]),
                    ).fetchone()
                item = json.loads(row["body"])
                data = {
                    "item_type": "context",
                    "context_type": "connector",
                    "context": {
                        **item,
                        "provider": row["provider"],
                        "text": ("来源已移除：" if item.get("deleted") else "")
                        + item.get("title", "")
                        + "\n"
                        + item.get("text", ""),
                        "untrusted_source": True,
                    },
                    "source": {
                        "kind": "connector",
                        "namespace": row["provider"] + "." + row["connection_id"],
                        "external_id": hashlib.sha256(row["external_id"].encode()).hexdigest(),
                        "version": row["version"],
                        "parser": "hymio.connectors.v1",
                    },
                }
                if previous:
                    data["expected_record_id"] = previous[0]
                result = self.context.call(
                    row["user_id"],
                    "records.append",
                    data=data,
                    operation_id="connector:" + str(row["id"]),
                )
                with self.store.transaction() as db:
                    db.execute(
                        "UPDATE connector_changes SET delivered=1,record_id=?,error='' WHERE id=?",
                        (result["data"]["id"], row["id"]),
                    )
            except Exception as exc:
                code = (
                    "context_conflict"
                    if isinstance(exc, ContextError) and exc.status == 412
                    else "context_pending"
                )
                with self.store.transaction() as db:
                    db.execute(
                        "UPDATE connector_changes SET error=?,retry_at=? WHERE id=?",
                        (code, time.time() + 300, row["id"]),
                    )
        return bool(rows)

    def read(self, uid, cid=None, query="", limit=20):
        if (
            not isinstance(query, str)
            or len(query) > 100
            or type(limit) is not int
            or not 1 <= limit <= 50
        ):
            raise ConnectorError("invalid_query")
        with self.store.transaction() as db:
            if cid:
                self.store.owned(db, uid, cid)
            rows = db.execute(
                "SELECT "
                "i.body,i.connection_id,i.updated_at,n.last_success,n.state,n.provider "
                "FROM connector_items i JOIN connections n ON n.id=i.connection_id WHERE "
                "i.user_id=? AND i.deleted=0 AND (? IS NULL OR i.connection_id=?) AND "
                "i.body LIKE ? ESCAPE '\\' ORDER BY i.updated_at DESC LIMIT ?",
                (
                    uid,
                    cid,
                    cid,
                    "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%",
                    limit,
                ),
            ).fetchall()
            return [
                {
                    "connection_id": r["connection_id"],
                    "provider": r["provider"],
                    "data": {
                        **json.loads(r["body"]),
                        "text": json.loads(r["body"]).get("text", "")[:2000],
                    },
                    "untrusted_source": True,
                    "synced_at": r["updated_at"],
                    "last_success": r["last_success"],
                    "connection_state": r["state"],
                }
                for r in rows
            ]

    async def disconnect(self, uid, cid):
        with self.store.transaction() as db:
            row = self.store.owned(db, uid, cid)
        value = await asyncio.to_thread(self.store.action, uid, cid, "disconnect")
        if row["credentials"]:
            try:
                token = json.loads(self.store.cipher.decrypt(row["credentials"].encode()))[
                    "access_token"
                ]
                url = (
                    "https://oauth2.googleapis.com/revoke"
                    if row["provider"] == "gmail"
                    else "https://api.dida365.com/oauth/revoke"
                )
                await request(self.http, "POST", url, data={"token": token})
                value["revocation"] = "confirmed"
            except Exception:
                value["revocation"] = "not_confirmed"
        return value

    async def run(self):
        async def loop(operation, interval):
            while True:
                try:
                    await operation()
                except Exception as exc:
                    _log.warning("Connector worker retry: %s", type(exc).__name__)
                await asyncio.sleep(interval)

        async def project():
            await asyncio.to_thread(self.project)

        try:
            await asyncio.gather(loop(self.collect, 5), loop(self.collect, 5), loop(project, 5))
        finally:
            await self.http.aclose()
