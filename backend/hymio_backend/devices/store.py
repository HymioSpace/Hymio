import hashlib
import json
import time
import uuid


class DeviceConflict(ValueError):
    pass


class DeviceStore:
    def __init__(self, sessions):
        self.transaction = sessions.transaction
        with self.transaction() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS devices (
                    id TEXT PRIMARY KEY, user_id TEXT NOT NULL, name TEXT NOT NULL,
                    kind TEXT NOT NULL, provider TEXT NOT NULL, provider_ref TEXT NOT NULL,
                    generation INTEGER NOT NULL DEFAULT 1, revoked_at REAL,
                    created_at REAL NOT NULL, last_seen REAL NOT NULL DEFAULT 0);
                CREATE UNIQUE INDEX IF NOT EXISTS one_cloud_desktop
                    ON devices(user_id,kind) WHERE revoked_at IS NULL AND kind='cloud_desktop';
                CREATE UNIQUE INDEX IF NOT EXISTS one_mac
                    ON devices(user_id,kind) WHERE revoked_at IS NULL AND kind='mac';
                CREATE UNIQUE INDEX IF NOT EXISTS channel_binding
                    ON devices(user_id,provider_ref)
                    WHERE revoked_at IS NULL AND provider='channel';
                CREATE TABLE IF NOT EXISTS device_commands (
                    user_id TEXT NOT NULL, invocation_id TEXT NOT NULL,
                    device_id TEXT NOT NULL, generation INTEGER NOT NULL,
                    fingerprint TEXT NOT NULL, deadline REAL NOT NULL,
                    status TEXT NOT NULL, result TEXT, PRIMARY KEY(user_id,invocation_id));
                CREATE TABLE IF NOT EXISTS device_locks (
                    device_id TEXT PRIMARY KEY, user_id TEXT NOT NULL,
                    invocation_id TEXT NOT NULL, deadline REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS device_ensures (
                    user_id TEXT PRIMARY KEY, owner TEXT NOT NULL, deadline REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS device_recovery (
                    user_id TEXT PRIMARY KEY, failures INTEGER NOT NULL,
                    retry_at REAL NOT NULL, error TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS device_media (
                    id TEXT PRIMARY KEY, user_id TEXT NOT NULL, device_id TEXT NOT NULL,
                    content BLOB NOT NULL, created_at REAL NOT NULL);
            """)
            additions = {
                "devices": {
                    "control_state": "TEXT NOT NULL DEFAULT 'active'",
                    "replaces_device_id": "TEXT",
                },
                "device_commands": {
                    "request_json": "TEXT NOT NULL DEFAULT '{}'",
                    "submitted_at": "REAL NOT NULL DEFAULT 0",
                },
            }
            if not db.in_transaction:
                db.execute("BEGIN IMMEDIATE")
            for table, columns in additions.items():
                existing = {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}
                for name, definition in columns.items():
                    if name not in existing:
                        db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
            self._channel_policy(db)

    def _channel_policy(self, db):
        db.execute(
            """UPDATE devices SET revoked_at=? WHERE id IN (
            SELECT id FROM (SELECT id, row_number() OVER (
                PARTITION BY user_id,kind ORDER BY last_seen DESC,created_at DESC,id DESC
            ) AS rank FROM devices WHERE revoked_at IS NULL AND kind IN ('web','ios'))
            WHERE rank>1)""",
            (time.time(),),
        )
        db.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS one_channel_kind ON devices(user_id,kind) "
            "WHERE revoked_at IS NULL AND kind IN ('web','ios')"
        )
        db.execute("""CREATE TABLE IF NOT EXISTS channel_connections (
            user_id TEXT NOT NULL, kind TEXT NOT NULL, owner TEXT NOT NULL, deadline REAL NOT NULL,
            PRIMARY KEY(user_id,kind))""")

    def connection_claim(self, user_id, kind, owner):
        with self.transaction() as db:
            db.execute(
                "INSERT OR REPLACE INTO channel_connections VALUES(?,?,?,?)",
                (user_id, kind, owner, time.time() + 45),
            )

    def connection_renew(self, user_id, kind, owner):
        with self.transaction() as db:
            return (
                db.execute(
                    "UPDATE channel_connections SET deadline=? "
                    "WHERE user_id=? AND kind=? AND owner=? AND deadline>?",
                    (time.time() + 45, user_id, kind, owner, time.time()),
                ).rowcount
                == 1
            )

    def connection_release(self, user_id, kind, owner):
        with self.transaction() as db:
            db.execute(
                "DELETE FROM channel_connections WHERE user_id=? AND kind=? AND owner=?",
                (user_id, kind, owner),
            )

    def create(self, user_id, provider):
        with self.transaction() as db:
            row = db.execute(
                "SELECT * FROM devices WHERE user_id=? AND kind='cloud_desktop' "
                "AND revoked_at IS NULL",
                (user_id,),
            ).fetchone()
            if row:
                return dict(row)
            device_id = uuid.uuid4().hex
            db.execute(
                "INSERT INTO devices(id,user_id,name,kind,provider,provider_ref,created_at) "
                "VALUES(?,?,?,'cloud_desktop',?,'',?)",
                (device_id, user_id, "Cloud desktop", provider, time.time()),
            )
        return self.get(user_id, device_id)

    def get(self, user_id, device_id):
        with self.transaction() as db:
            row = db.execute(
                "SELECT * FROM devices WHERE user_id=? AND id=? AND revoked_at IS NULL",
                (user_id, device_id),
            ).fetchone()
            if not row:
                raise KeyError("device_not_found")
            return dict(row)

    def list(self, user_id):
        with self.transaction() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM devices WHERE user_id=? AND revoked_at IS NULL "
                    "ORDER BY created_at",
                    (user_id,),
                )
            ]

    def set_ref(self, user_id, device_id, reference):
        with self.transaction() as db:
            changed = db.execute(
                "UPDATE devices SET provider_ref=? WHERE id=? AND user_id=? AND revoked_at IS NULL",
                (reference, device_id, user_id),
            ).rowcount
            if changed != 1:
                raise DeviceConflict("device_revoked_during_provision")

    def begin_ensure(self, user_id):
        owner = uuid.uuid4().hex
        with self.transaction() as db:
            row = db.execute(
                "SELECT deadline FROM device_ensures WHERE user_id=?", (user_id,)
            ).fetchone()
            if row and row[0] > time.time():
                return None
            db.execute(
                "INSERT OR REPLACE INTO device_ensures VALUES(?,?,?)",
                (user_id, owner, time.time() + 180),
            )
        return owner

    def recovery(self, user_id, *, error=None, clear=False):
        with self.transaction() as db:
            row = db.execute("SELECT * FROM device_recovery WHERE user_id=?", (user_id,)).fetchone()
            if clear:
                db.execute("DELETE FROM device_recovery WHERE user_id=?", (user_id,))
                return None
            if error:
                failures = (row["failures"] if row else 0) + 1
                retry_at = time.time() + min(300, 5 * 2 ** min(failures - 1, 6))
                db.execute(
                    "INSERT OR REPLACE INTO device_recovery VALUES(?,?,?,?)",
                    (user_id, failures, retry_at, error),
                )
                return {"retry_at": retry_at, "error": error}
            return dict(row) if row else None

    def provision_record(self, user_id, device_id):
        with self.transaction() as db:
            row = db.execute(
                "SELECT status,result FROM device_commands WHERE user_id=? AND device_id=? "
                "AND invocation_id LIKE ? ORDER BY submitted_at DESC LIMIT 1",
                (user_id, device_id, "provision:" + device_id + "%"),
            ).fetchone()
            return dict(row) if row else None

    def finish_ensure(self, user_id, owner):
        with self.transaction() as db:
            db.execute("DELETE FROM device_ensures WHERE user_id=? AND owner=?", (user_id, owner))

    def replace_missing(self, user_id, device_id):
        with self.transaction() as db:
            row = db.execute(
                "SELECT id FROM devices WHERE user_id=? AND id=? AND revoked_at IS NULL",
                (user_id, device_id),
            ).fetchone()
            if not row:
                raise DeviceConflict("binding_changed")
            db.execute(
                "UPDATE devices SET revoked_at=?,generation=generation+1 WHERE user_id=? AND id=?",
                (time.time(), user_id, device_id),
            )
            new_id = uuid.uuid4().hex
            db.execute(
                "INSERT INTO devices(id,user_id,name,kind,provider,provider_ref,created_at,"
                "replaces_device_id) "
                "VALUES(?,?,'E2B cloud desktop','cloud_desktop','e2b','',?,?)",
                (new_id, user_id, time.time(), device_id),
            )
        return self.get(user_id, new_id)

    def bind(self, user_id, installation_id, kind):
        if (
            kind not in ("web", "ios", "mac")
            or not isinstance(installation_id, str)
            or not 1 <= len(installation_id) <= 128
        ):
            raise ValueError("invalid_device")
        with self.transaction() as db:
            row = db.execute(
                "SELECT * FROM devices WHERE user_id=? AND provider_ref=? AND provider='channel' "
                "AND revoked_at IS NULL",
                (user_id, installation_id),
            ).fetchone()
            if row:
                if row["kind"] != kind:
                    raise DeviceConflict("installation_kind_conflict")
                device_id = row["id"]
            else:
                same_kind = db.execute(
                    "SELECT * FROM devices WHERE user_id=? AND kind=? AND revoked_at IS NULL",
                    (user_id, kind),
                ).fetchone()
                if same_kind:
                    if kind == "mac":
                        raise DeviceConflict("mac_already_bound")
                    db.execute(
                        "UPDATE devices SET provider_ref=?,last_seen=? WHERE id=?",
                        (installation_id, time.time(), same_kind["id"]),
                    )
                    return dict(
                        db.execute(
                            "SELECT * FROM devices WHERE id=?", (same_kind["id"],)
                        ).fetchone()
                    )
                device_id = uuid.uuid4().hex
                db.execute(
                    "INSERT INTO devices(id,user_id,name,kind,provider,provider_ref,created_at) "
                    "VALUES(?,?,?,?,'channel',?,?)",
                    (
                        device_id,
                        user_id,
                        {"web": "Web", "ios": "iPhone", "mac": "Mac"}[kind],
                        kind,
                        installation_id,
                        time.time(),
                    ),
                )
            db.execute(
                "UPDATE devices SET last_seen=? WHERE id=? AND user_id=?",
                (time.time(), device_id, user_id),
            )
        return self.get(user_id, device_id)

    def heartbeat(self, user_id, device_id):
        self.get(user_id, device_id)
        with self.transaction() as db:
            db.execute(
                "UPDATE devices SET last_seen=? WHERE id=? AND user_id=?",
                (time.time(), device_id, user_id),
            )

    def revoke(self, user_id, device_id):
        self.get(user_id, device_id)
        with self.transaction() as db:
            db.execute(
                "UPDATE devices SET revoked_at=?,generation=generation+1 WHERE id=? AND user_id=?",
                (time.time(), device_id, user_id),
            )

    def claim(self, user_id, device_id, invocation_id, request, timeout):
        fingerprint = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()
        deadline = time.time() + timeout
        with self.transaction() as db:
            selected = db.execute(
                "SELECT * FROM devices WHERE user_id=? AND id=? AND revoked_at IS NULL",
                (user_id, device_id),
            ).fetchone()
            if not selected:
                raise KeyError("device_not_found")
            device = dict(selected)
            current = db.execute(
                "SELECT * FROM device_commands WHERE user_id=? AND invocation_id=?",
                (user_id, invocation_id),
            ).fetchone()
            if current:
                if current["fingerprint"] != fingerprint or current["device_id"] != device_id:
                    raise DeviceConflict("invocation_conflict")
                if current["result"]:
                    return device, json.loads(current["result"])
                if current["deadline"] <= time.time():
                    unknown = {"device_id": device_id, "status": "outcome_unknown"}
                    db.execute(
                        "UPDATE device_commands SET status='outcome_unknown',result=? "
                        "WHERE user_id=? AND invocation_id=?",
                        (json.dumps(unknown), user_id, invocation_id),
                    )
                    return device, unknown
                raise DeviceConflict("invocation_running")
            if device["control_state"] != "active":
                raise DeviceConflict("device_" + device["control_state"])
            # All actions share a device lock: shell may also alter the browser or desktop.
            lock = db.execute(
                "SELECT * FROM device_locks WHERE device_id=?", (device_id,)
            ).fetchone()
            if lock:
                raise DeviceConflict("device_busy_or_requires_recovery")
            db.execute(
                "INSERT INTO device_locks VALUES(?,?,?,?)",
                (device_id, user_id, invocation_id, deadline),
            )
            db.execute(
                "INSERT INTO device_commands(user_id,invocation_id,device_id,generation,"
                "fingerprint,deadline,status,result,request_json,submitted_at) "
                "VALUES(?,?,?,?,?,?,'running',NULL,?,?)",
                (
                    user_id,
                    invocation_id,
                    device_id,
                    device["generation"],
                    fingerprint,
                    deadline,
                    json.dumps(request),
                    time.time(),
                ),
            )
        return device, None

    def finish(self, user_id, invocation_id, result, *, release=True):
        with self.transaction() as db:
            updated = db.execute(
                "UPDATE device_commands SET status=?,result=? WHERE user_id=? AND invocation_id=? "
                "AND status='running'",
                (result["status"], json.dumps(result), user_id, invocation_id),
            )
            if not updated.rowcount:
                known = db.execute(
                    "SELECT result FROM device_commands WHERE user_id=? AND invocation_id=?",
                    (user_id, invocation_id),
                ).fetchone()
                return json.loads(known[0]) if known and known[0] else result
            if release:
                db.execute(
                    "DELETE FROM device_locks WHERE user_id=? AND invocation_id=?",
                    (user_id, invocation_id),
                )
            return result

    def media(self, user_id, device_id, content):
        media_id = uuid.uuid4().hex
        with self.transaction() as db:
            db.execute(
                "INSERT INTO device_media VALUES(?,?,?,?,?)",
                (media_id, user_id, device_id, content, time.time()),
            )
        return media_id

    def read_media(self, user_id, media_id):
        with self.transaction() as db:
            row = db.execute(
                "SELECT content FROM device_media WHERE user_id=? AND id=?", (user_id, media_id)
            ).fetchone()
            if not row:
                raise KeyError("media_not_found")
            return row[0]

    def expired_execution(self, user_id, device_id):
        with self.transaction() as db:
            row = db.execute(
                "SELECT * FROM device_locks WHERE user_id=? AND device_id=? "
                "AND deadline<? AND invocation_id NOT LIKE 'control:%'",
                (user_id, device_id, time.time() - 5),
            ).fetchone()
            return dict(row) if row else None

    def release_expired_execution(self, user_id, device_id, lock):
        with self.transaction() as db:
            deleted = db.execute(
                "DELETE FROM device_locks WHERE user_id=? AND device_id=? "
                "AND invocation_id=? AND deadline=? AND deadline<?",
                (user_id, device_id, lock["invocation_id"], lock["deadline"], time.time() - 5),
            )
            if deleted.rowcount:
                db.execute(
                    "UPDATE device_commands SET status='outcome_unknown',result=? "
                    "WHERE user_id=? AND invocation_id=? AND status='running'",
                    (
                        json.dumps(
                            {
                                "status": "outcome_unknown",
                                "error": (
                                    "Expired execution; no remote operation running. "
                                    "Effects were not repeated."
                                ),
                            }
                        ),
                        user_id,
                        lock["invocation_id"],
                    ),
                )
            return deleted.rowcount == 1

    def begin_control(self, user_id, device_id, action):
        recovery_id = "control:" + action + ":" + uuid.uuid4().hex
        with self.transaction() as db:
            device = db.execute(
                "SELECT * FROM devices WHERE user_id=? AND id=? AND revoked_at IS NULL",
                (user_id, device_id),
            ).fetchone()
            if not device:
                raise KeyError("device_not_found")
            lock = db.execute(
                "SELECT * FROM device_locks WHERE device_id=?", (device_id,)
            ).fetchone()
            if lock and (
                lock["deadline"] > time.time() or not lock["invocation_id"].startswith("control:")
            ):
                raise DeviceConflict("device_running_or_requires_recovery")
            db.execute(
                "INSERT OR REPLACE INTO device_locks VALUES(?,?,?,?)",
                (device_id, user_id, recovery_id, time.time() + 120),
            )
            db.execute(
                "UPDATE devices SET control_state='changing' WHERE id=? AND user_id=?",
                (device_id, user_id),
            )
        return recovery_id

    def finish_control(self, user_id, device_id, control_id, state):
        with self.transaction() as db:
            lock = db.execute(
                "SELECT invocation_id FROM device_locks WHERE device_id=? AND user_id=?",
                (device_id, user_id),
            ).fetchone()
            if not lock or lock[0] != control_id:
                raise DeviceConflict("control_replaced")
            db.execute(
                "UPDATE devices SET control_state=? WHERE id=? AND user_id=? "
                "AND revoked_at IS NULL",
                (state, device_id, user_id),
            )
            if state != "recovery_required":
                db.execute(
                    "DELETE FROM device_locks WHERE device_id=? AND invocation_id=?",
                    (device_id, control_id),
                )

    def reconcile_control(self, user_id, device_id, physical):
        with self.transaction() as db:
            lock = db.execute(
                "SELECT * FROM device_locks WHERE user_id=? AND device_id=? AND deadline<?",
                (user_id, device_id, time.time()),
            ).fetchone()
            if not lock:
                return False
            expected = (
                "online"
                if lock["invocation_id"].startswith("control:resume:")
                else "paused"
                if lock["invocation_id"].startswith("control:pause:")
                else None
            )
            if physical != expected:
                return False
            db.execute(
                "UPDATE devices SET control_state=? WHERE user_id=? AND id=? "
                "AND revoked_at IS NULL",
                ("active" if physical == "online" else "paused", user_id, device_id),
            )
            db.execute(
                "DELETE FROM device_locks WHERE user_id=? AND device_id=? AND invocation_id=?",
                (user_id, device_id, lock["invocation_id"]),
            )
            return True

    def commands(self, user_id, device_id, invocation_id=None, limit=20):
        with self.transaction() as db:
            if not db.execute(
                "SELECT 1 FROM devices WHERE user_id=? AND id=?", (user_id, device_id)
            ).fetchone():
                raise KeyError("device_not_found")
            query = "SELECT * FROM device_commands WHERE user_id=? AND device_id=?"
            params = [user_id, device_id]
            if invocation_id:
                query += " AND invocation_id=?"
                params.append(invocation_id)
            rows = db.execute(
                query + " ORDER BY submitted_at DESC LIMIT ?", (*params, min(max(limit, 1), 100))
            ).fetchall()
            result = []
            for row in rows:
                status = row["status"]
                if status == "running" and row["deadline"] < time.time():
                    status = "outcome_unknown"
                result.append(
                    {
                        "invocation_id": row["invocation_id"],
                        "device_id": device_id,
                        "status": status,
                        "request": json.loads(row["request_json"]),
                        "submitted_at": row["submitted_at"],
                        "result": json.loads(row["result"]) if row["result"] else None,
                    }
                )
            if invocation_id and not result:
                raise KeyError("command_not_found")
            return result[0] if invocation_id else result
