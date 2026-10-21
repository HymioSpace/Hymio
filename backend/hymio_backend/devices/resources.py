"""Durable operator grants and provider capacity; no provider network calls in transactions."""

import json
import time


class ResourceDenied(ValueError):
    pass


class ResourceCapacity(ValueError):
    pass


LIMITS = {"daytona": 10, "e2b": 20, "device_api": 1}
NAMES = {"daytona": "Daytona", "e2b": "E2B", "device_api": "火山 ECS"}


class ResourceStore:
    def __init__(self, sessions):
        self.transaction = sessions.transaction
        with self.transaction() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS resource_grants (
                    user_id TEXT NOT NULL, kind TEXT NOT NULL, provider TEXT NOT NULL,
                    enabled INTEGER NOT NULL, updated_at REAL NOT NULL,
                    PRIMARY KEY(user_id,kind));
                CREATE TABLE IF NOT EXISTS resource_allocations (
                    device_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, kind TEXT NOT NULL,
                    provider TEXT NOT NULL, state TEXT NOT NULL, updated_at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS resource_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, actor TEXT NOT NULL,
                    target TEXT NOT NULL, action TEXT NOT NULL, detail TEXT NOT NULL,
                    created_at REAL NOT NULL);
            """)
            # Preserve capacity held by pre-existing devices without automatically granting access.
            db.execute(
                """INSERT OR IGNORE INTO resource_allocations
                SELECT id,user_id,kind,provider,'allocated',? FROM devices
                WHERE kind IN ('cloud_desktop','cloud_android') AND revoked_at IS NULL""",
                (time.time(),),
            )

    def provider(self, user_id, kind="cloud_desktop"):
        with self.transaction() as db:
            row = db.execute(
                "SELECT provider FROM resource_grants WHERE user_id=? AND kind=? AND enabled=1",
                (user_id, kind),
            ).fetchone()
            return row["provider"] if row else None

    def require(self, user_id, provider):
        if self.provider(user_id) != provider:
            raise ResourceDenied("resource_access_denied")

    @staticmethod
    def reserve(db, device):
        provider = device["provider"]
        row = db.execute(
            "SELECT state FROM resource_allocations WHERE device_id=?", (device["id"],)
        ).fetchone()
        if row and row["state"] != "released":
            return
        if provider not in LIMITS:
            raise ResourceCapacity("resource_provider_not_supported")
        count = db.execute(
            "SELECT count(*) FROM resource_allocations WHERE provider=? "
            "AND kind='cloud_desktop' AND state!='released'",
            (provider,),
        ).fetchone()[0]
        if count >= LIMITS[provider]:
            raise ResourceCapacity("resource_capacity_exhausted")
        db.execute(
            "INSERT OR REPLACE INTO resource_allocations VALUES(?,?,?,?,?,?)",
            (device["id"], device["user_id"], "cloud_desktop", provider, "reserved", time.time()),
        )

    def mark(self, device_id, state):
        with self.transaction() as db:
            db.execute(
                "UPDATE resource_allocations SET state=?,updated_at=? WHERE device_id=?",
                (state, time.time(), device_id),
            )

    def grant(self, actor, user_id, provider, enabled, kind="cloud_desktop"):
        if kind != "cloud_desktop" or provider not in LIMITS or type(enabled) is not bool:
            raise ValueError("invalid_resource_grant")
        with self.transaction() as db:
            if not db.execute("SELECT 1 FROM users WHERE user_id=?", (user_id,)).fetchone():
                raise KeyError("user_not_found")
            active = db.execute(
                "SELECT provider FROM resource_allocations "
                "WHERE user_id=? AND state!='released' LIMIT 1",
                (user_id,),
            ).fetchone()
            if (
                enabled
                and active
                and active["provider"] != provider
            ):
                raise ResourceCapacity("resource_release_required")
            db.execute(
                "INSERT OR REPLACE INTO resource_grants VALUES(?,?,?,?,?)",
                (user_id, kind, provider, int(enabled), time.time()),
            )
            db.execute(
                "INSERT INTO resource_audit(actor,target,action,detail,created_at) "
                "VALUES(?,?,?,?,?)",
                (
                    actor,
                    user_id,
                    "grant",
                    json.dumps({"kind": kind, "provider": provider, "enabled": enabled}),
                    time.time(),
                ),
            )

    def audit(self, actor, target, action):
        with self.transaction() as db:
            db.execute(
                "INSERT INTO resource_audit(actor,target,action,detail,created_at) "
                "VALUES(?,?,?,?,?)",
                (actor, target, action, "{}", time.time()),
            )

    def overview(self, query="", offset=0):
        with self.transaction() as db:
            users = [
                dict(row)
                for row in db.execute(
                    """SELECT u.user_id,u.name,g.provider,g.enabled
                FROM users u LEFT JOIN resource_grants g ON u.user_id=g.user_id
                AND g.kind='cloud_desktop'
                WHERE instr(lower(u.name),lower(?))>0 OR instr(u.user_id,?)>0
                ORDER BY lower(u.name),u.user_id LIMIT 50 OFFSET ?""",
                    (query, query, offset),
                )
            ]
            devices = [
                dict(row)
                for row in db.execute("""
                SELECT a.device_id,a.user_id,a.provider,a.state,a.updated_at,
                d.name,d.control_state,d.revoked_at,coalesce(u.name,a.user_id) AS user_name
                FROM resource_allocations a JOIN devices d ON d.id=a.device_id
                LEFT JOIN users u ON u.user_id=a.user_id
                WHERE a.state!='released' ORDER BY a.updated_at DESC LIMIT 100""")
            ]
            capacities = []
            for provider, limit in LIMITS.items():
                used = db.execute(
                    "SELECT count(*) FROM resource_allocations "
                    "WHERE provider=? AND state!='released'",
                    (provider,),
                ).fetchone()[0]
                capacities.append(
                    {"provider": provider, "name": NAMES[provider], "limit": limit, "used": used}
                )
            return {
                "providers": capacities,
                "users": users,
                "devices": devices,
                "next_offset": offset + 50 if len(users) == 50 else None,
                "phone": {"limit": 0, "enabled": False},
                "audit": [
                    dict(r)
                    for r in db.execute(
                        "SELECT actor,target,action,created_at FROM resource_audit "
                        "ORDER BY id DESC LIMIT 20"
                    )
                ],
            }
