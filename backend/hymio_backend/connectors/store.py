import hashlib
import json
import os
import secrets
import time
import uuid
from pathlib import Path

from cryptography.fernet import Fernet

from .catalog import PROVIDERS, ConnectorError


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class ConnectorStore:
    def __init__(self, sessions):
        self.transaction = sessions.transaction
        path = Path(sessions.settings.database).with_suffix(".connectors.key")
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(fd, "wb") as file:
                file.write(Fernet.generate_key())
                file.flush()
                os.fsync(file.fileno())
        self.cipher = Fernet(path.read_bytes().strip())
        with self.transaction() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS connections (
              id TEXT PRIMARY KEY, user_id TEXT NOT NULL, provider TEXT NOT NULL,
              device_id TEXT NOT NULL DEFAULT '', name TEXT NOT NULL, state TEXT NOT NULL,
              enabled INTEGER NOT NULL DEFAULT 1, generation INTEGER NOT NULL DEFAULT 1,
              credentials TEXT NOT NULL DEFAULT '', checkpoint TEXT NOT NULL DEFAULT '{}',
              last_success REAL, next_sync REAL, lease TEXT, lease_until REAL,
              failures INTEGER NOT NULL DEFAULT 0, error TEXT NOT NULL DEFAULT '',
              created_at REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS connections_owner ON connections(user_id,created_at);
            CREATE INDEX IF NOT EXISTS connections_due ON connections(enabled,next_sync);
            CREATE TABLE IF NOT EXISTS connector_flows (
              state_hash TEXT PRIMARY KEY, connection_id TEXT NOT NULL, user_id TEXT NOT NULL,
              verifier TEXT NOT NULL, expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS connector_runs (
              id TEXT PRIMARY KEY, connection_id TEXT NOT NULL, user_id TEXT NOT NULL,
              started_at REAL NOT NULL, finished_at REAL, status TEXT NOT NULL,
              received INTEGER NOT NULL DEFAULT 0, error TEXT NOT NULL DEFAULT '');
            CREATE INDEX IF NOT EXISTS connector_runs_owner ON
                connector_runs(user_id,connection_id,started_at);
            CREATE TABLE IF NOT EXISTS connector_items (
              connection_id TEXT NOT NULL, user_id TEXT NOT NULL, external_id TEXT NOT NULL,
              version TEXT NOT NULL, body TEXT NOT NULL, deleted INTEGER NOT NULL DEFAULT 0,
              updated_at REAL NOT NULL, PRIMARY KEY(connection_id,external_id));
            CREATE TABLE IF NOT EXISTS connector_changes (
              id INTEGER PRIMARY KEY AUTOINCREMENT, connection_id TEXT NOT NULL,
              user_id TEXT NOT NULL, external_id TEXT NOT NULL, version TEXT NOT NULL,
              body TEXT NOT NULL, delivered INTEGER NOT NULL DEFAULT 0, record_id TEXT,
              error TEXT NOT NULL DEFAULT '', retry_at REAL NOT NULL DEFAULT 0,
              UNIQUE(connection_id,external_id,version));
            CREATE INDEX IF NOT EXISTS connector_changes_source ON
                connector_changes(connection_id,external_id,id,delivered);
            CREATE INDEX IF NOT EXISTS connector_changes_pending ON
                connector_changes(delivered,retry_at,id);
            """)

    def owned(self, db, uid, cid):
        row = db.execute(
            "SELECT * FROM connections WHERE user_id=? AND id=?", (uid, cid)
        ).fetchone()
        if not row:
            raise ConnectorError("connection_not_found", 404)
        return dict(row)

    def view(self, db, row):
        allowed = (
            "id",
            "provider",
            "device_id",
            "name",
            "state",
            "enabled",
            "last_success",
            "next_sync",
            "error",
            "created_at",
        )
        value = {key: row[key] for key in allowed}
        value["item_count"] = db.execute(
            "SELECT count(*) FROM connector_items WHERE connection_id=? AND deleted=0", (row["id"],)
        ).fetchone()[0]
        value["pending_count"] = db.execute(
            "SELECT count(*) FROM connector_changes WHERE connection_id=? AND delivered=0",
            (row["id"],),
        ).fetchone()[0]
        value["runs"] = [
            dict(r)
            for r in db.execute(
                "SELECT id,started_at,finished_at,status,received,error FROM "
                "connector_runs WHERE user_id=? AND connection_id=? ORDER BY started_at "
                "DESC LIMIT 5",
                (row["user_id"], row["id"]),
            )
        ]
        return value

    def list(self, uid):
        with self.transaction() as db:
            return [
                self.view(db, dict(r))
                for r in db.execute(
                    "SELECT * FROM connections WHERE user_id=? ORDER BY created_at", (uid,)
                )
            ]

    def create(self, uid, provider, device_id="", name=""):
        if provider not in PROVIDERS:
            raise ConnectorError("unknown_provider")
        if not isinstance(device_id, str) or len(device_id) > 128:
            raise ConnectorError("invalid_device")
        with self.transaction() as db:
            if (
                db.execute("SELECT count(*) FROM connections WHERE user_id=?", (uid,)).fetchone()[0]
                >= 20
            ):
                raise ConnectorError("connection_limit", 409)
            cid = uuid.uuid4().hex
            state = (
                "authorization_required"
                if PROVIDERS[provider]["transport"] == "oauth"
                else "waiting_device"
            )
            db.execute(
                "INSERT INTO "
                "connections(id,user_id,provider,device_id,name,state,created_at) "
                "VALUES(?,?,?,?,?,?,?)",
                (
                    cid,
                    uid,
                    provider,
                    device_id,
                    name[:100] if isinstance(name, str) and name else PROVIDERS[provider]["name"],
                    state,
                    time.time(),
                ),
            )
            return self.view(db, self.owned(db, uid, cid))

    def action(self, uid, cid, action):
        with self.transaction() as db:
            row = self.owned(db, uid, cid)
            if action == "disconnect":
                db.execute(
                    "UPDATE connections SET "
                    "enabled=0,state='disconnected',credentials='',generation=generation+1,lease=NULL,lease_until=NULL,next_sync=NULL"
                    " WHERE id=?",
                    (cid,),
                )
                db.execute("DELETE FROM connector_flows WHERE connection_id=?", (cid,))
            elif action in {"pause", "resume", "sync"}:
                if row["state"] == "disconnected":
                    raise ConnectorError("reconnect_required", 409)
                enabled = action != "pause"
                cloud = PROVIDERS[row["provider"]]["transport"] == "oauth"
                if enabled and cloud and not row["credentials"]:
                    raise ConnectorError("reconnect_required", 409)
                state = "queued" if cloud else "waiting_device"
                db.execute(
                    "UPDATE connections SET "
                    "enabled=?,state=?,generation=generation+1,lease=NULL,lease_until=NULL,next_sync=?,error=''"
                    " WHERE id=?",
                    (
                        enabled,
                        state if enabled else "paused",
                        time.time() if enabled and cloud else None,
                        cid,
                    ),
                )
            else:
                raise ConnectorError("unknown_action")
            return self.view(db, self.owned(db, uid, cid))

    def claim(self):
        now = time.time()
        with self.transaction() as db:
            row = db.execute(
                "SELECT * FROM connections WHERE enabled=1 AND next_sync<=? AND "
                "(lease_until IS NULL OR lease_until<?) ORDER BY next_sync LIMIT 1",
                (now, now),
            ).fetchone()
            if not row:
                return None
            row = dict(row)
            row["lease"] = secrets.token_hex(16)
            db.execute(
                "UPDATE connections SET lease=?,lease_until=?,state='syncing' WHERE id=?",
                (row["lease"], now + 300, row["id"]),
            )
            db.execute(
                "UPDATE connector_runs SET status='interrupted',finished_at=? WHERE "
                "connection_id=? AND status='running'",
                (now, row["id"]),
            )
            run = uuid.uuid4().hex
            db.execute(
                "INSERT INTO connector_runs(id,connection_id,user_id,started_at,status) "
                "VALUES(?,?,?,?,'running')",
                (run, row["id"], row["user_id"], now),
            )
            row["run_id"] = run
            return row

    def apply(
        self,
        uid,
        cid,
        items,
        checkpoint=None,
        *,
        lease=None,
        generation=None,
        credentials=None,
        reconcile=None,
    ):
        now = time.time()
        with self.transaction() as db:
            row = self.owned(db, uid, cid)
            if not row["enabled"] or row["state"] == "disconnected":
                raise ConnectorError("connection_paused", 409)
            if lease is not None and (
                row["lease"] != lease
                or row["generation"] != generation
                or (row["lease_until"] or 0) <= now
            ):
                raise ConnectorError("sync_superseded", 409)
            if checkpoint and "captured_at" in checkpoint:
                previous = json.loads(row["checkpoint"])
                if checkpoint["captured_at"] < previous.get("captured_at", 0):
                    raise ConnectorError("stale_device_snapshot", 409)
                if checkpoint["captured_at"] == previous.get("captured_at"):
                    if checkpoint != previous:
                        raise ConnectorError("device_snapshot_conflict", 409)
                    return self.view(db, row)
            if reconcile:
                seen = {x["external_id"] for x in items}
                for old in db.execute(
                    "SELECT external_id,body FROM connector_items WHERE connection_id=? AND "
                    "deleted=0",
                    (cid,),
                ):
                    body = json.loads(old["body"])
                    if (
                        old["external_id"] not in seen
                        and body.get("calendar_id") in reconcile["calendars"]
                        and reconcile["start"] <= body.get("start", "") < reconcile["end"]
                    ):
                        items.append(
                            {
                                "external_id": old["external_id"],
                                "title": body.get("title", ""),
                                "deleted": True,
                            }
                        )
            for item in items:
                raw = encode(item)
                version = hashlib.sha256(raw.encode()).hexdigest()
                old = db.execute(
                    "SELECT version,body FROM connector_items WHERE connection_id=? AND "
                    "external_id=?",
                    (cid, item["external_id"]),
                ).fetchone()
                if not old and item.get("deleted"):
                    continue
                if old and old["body"] == raw:
                    continue
                revision = int(old["version"].split(":", 1)[0]) + 1 if old else 1
                version = f"{revision}:{version}"
                db.execute(
                    "INSERT INTO "
                    "connector_changes(connection_id,user_id,external_id,version,body) "
                    "VALUES(?,?,?,?,?) ON CONFLICT DO NOTHING",
                    (cid, uid, item["external_id"], version, raw),
                )
                db.execute(
                    "INSERT INTO connector_items VALUES(?,?,?,?,?,?,?) ON "
                    "CONFLICT(connection_id,external_id) DO UPDATE SET "
                    "version=excluded.version,body=excluded.body,deleted=excluded.deleted,updated_at=excluded.updated_at",
                    (cid, uid, item["external_id"], version, raw, bool(item.get("deleted")), now),
                )
            more = bool((checkpoint or {}).get("page") or (checkpoint or {}).get("project_offset"))
            next_sync = (
                now + (5 if more else 900)
                if PROVIDERS[row["provider"]]["transport"] == "oauth"
                else None
            )
            db.execute(
                "UPDATE connections SET "
                "checkpoint=?,last_success=?,next_sync=?,state='ready',lease=NULL,lease_until=NULL,failures=0,error='',credentials=?"
                " WHERE id=?",
                (
                    encode(checkpoint if checkpoint is not None else json.loads(row["checkpoint"])),
                    now,
                    next_sync,
                    self.cipher.encrypt(encode(credentials).encode()).decode()
                    if credentials
                    else row["credentials"],
                    cid,
                ),
            )
            if lease:
                db.execute(
                    "UPDATE connector_runs SET finished_at=?,status='succeeded',received=? "
                    "WHERE connection_id=? AND status='running'",
                    (now, len(items), cid),
                )
            else:
                db.execute(
                    "INSERT INTO connector_runs VALUES(?,?,?,?,?,'succeeded',?,'')",
                    (uuid.uuid4().hex, cid, uid, now, now, len(items)),
                )
            db.execute(
                "DELETE FROM connector_runs WHERE connection_id=? AND id NOT IN (SELECT "
                "id FROM connector_runs WHERE connection_id=? ORDER BY started_at DESC "
                "LIMIT 30)",
                (cid, cid),
            )
            return self.view(db, self.owned(db, uid, cid))

    def failed(self, row, code):
        with self.transaction() as db:
            current = self.owned(db, row["user_id"], row["id"])
            if current["lease"] != row["lease"] or current["generation"] != row["generation"]:
                return
            auth = code == "reconnect_required"
            wait = min(21600, 60 * 2 ** min(current["failures"], 8))
            db.execute(
                "UPDATE connections SET "
                "state=?,error=?,next_sync=?,failures=failures+1,lease=NULL,lease_until=NULL"
                " WHERE id=?",
                (
                    "authorization_required" if auth else "retrying",
                    code,
                    None if auth else time.time() + wait,
                    row["id"],
                ),
            )
            db.execute(
                "UPDATE connector_runs SET status='failed',finished_at=?,error=? WHERE id=?",
                (time.time(), code, row["run_id"]),
            )
