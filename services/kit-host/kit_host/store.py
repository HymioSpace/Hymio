import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from datetime import date

CATEGORIES = {
    "food": "餐饮",
    "transport": "出行",
    "learning": "学习",
    "life": "生活",
    "other": "其他",
}


class KitStore:
    """Persistent business state owned by the Kit Host, not Hymio Backend."""

    def __init__(self, path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.transaction() as db:
            db.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS kit_installs (
                    user_id TEXT NOT NULL,
                    kit_id TEXT NOT NULL,
                    version TEXT NOT NULL,
                    installed_at REAL NOT NULL,
                    PRIMARY KEY(user_id, kit_id)
                );
                CREATE TABLE IF NOT EXISTS kit_receipts (
                    user_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    kit_id TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    result TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    PRIMARY KEY(user_id, idempotency_key)
                );
                CREATE TABLE IF NOT EXISTS ledger_entries (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    amount_minor INTEGER NOT NULL,
                    currency TEXT NOT NULL,
                    category TEXT NOT NULL,
                    note TEXT NOT NULL,
                    occurred_on TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ledger_entries_user_date
                    ON ledger_entries(user_id, occurred_on DESC, created_at DESC);
                CREATE TABLE IF NOT EXISTS generated_kits (
                    kit_id TEXT PRIMARY KEY,
                    owner_user_id TEXT NOT NULL,
                    manifest TEXT NOT NULL,
                    app_html TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS generated_kits_owner
                    ON generated_kits(owner_user_id, updated_at DESC);
                CREATE TABLE IF NOT EXISTS kit_records (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    kit_id TEXT NOT NULL,
                    data TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS kit_records_user_time
                    ON kit_records(user_id, kit_id, created_at DESC);
                """
            )
            columns = {row[1] for row in db.execute("PRAGMA table_info(generated_kits)")}
            if "app_html" not in columns:
                db.execute(
                    "ALTER TABLE generated_kits ADD COLUMN app_html TEXT NOT NULL DEFAULT ''"
                )
        self.path.chmod(0o600)

    @contextmanager
    def transaction(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def install(self, user_id, kit_id, version):
        with self.transaction() as db:
            db.execute(
                "INSERT INTO kit_installs(user_id,kit_id,version,installed_at) VALUES(?,?,?,?) "
                "ON CONFLICT(user_id,kit_id) DO UPDATE SET version=excluded.version",
                (user_id, kit_id, version, time.time()),
            )

    def uninstall(self, user_id, kit_id):
        with self.transaction() as db:
            db.execute(
                "DELETE FROM kit_installs WHERE user_id=? AND kit_id=?",
                (user_id, kit_id),
            )

    def installed(self, user_id):
        with self.transaction() as db:
            return {
                row["kit_id"]: row["version"]
                for row in db.execute(
                    "SELECT kit_id,version FROM kit_installs WHERE user_id=?", (user_id,)
                )
            }

    def create_entry(self, user_id, data, idempotency_key):
        if not isinstance(idempotency_key, str) or not 1 <= len(idempotency_key) <= 256:
            raise ValueError("A stable idempotency key is required")
        amount = data.get("amount")
        if (
            isinstance(amount, bool)
            or not isinstance(amount, (int, float))
            or not 0 < amount <= 1_000_000
        ):
            raise ValueError("Amount must be between 0 and 1,000,000")
        amount_minor = round(float(amount) * 100)
        category = data.get("category", "other")
        if category not in CATEGORIES:
            raise ValueError("Unknown category")
        note = data.get("note", "")
        if not isinstance(note, str) or len(note.strip()) > 200:
            raise ValueError("Note must be at most 200 characters")
        occurred_on = data.get("occurred_on") or date.today().isoformat()
        if not isinstance(occurred_on, str):
            raise ValueError("Invalid date")
        try:
            occurred_on = date.fromisoformat(occurred_on).isoformat()
        except ValueError as exc:
            raise ValueError("Invalid date") from exc
        entry_id, now = uuid.uuid4().hex, time.time()
        with self.transaction() as db:
            receipt = db.execute(
                "SELECT kit_id,operation,result FROM kit_receipts "
                "WHERE user_id=? AND idempotency_key=?",
                (user_id, idempotency_key),
            ).fetchone()
            if receipt:
                if receipt["kit_id"] != "hymio.ledger" or receipt["operation"] != "entries.create":
                    raise ValueError("Idempotency key belongs to another operation")
                return json.loads(receipt["result"])
            db.execute(
                "INSERT INTO ledger_entries "
                "(id,user_id,amount_minor,currency,category,note,occurred_on,revision,created_at) "
                "VALUES(?,?,?,?,?,?,?,1,?)",
                (
                    entry_id,
                    user_id,
                    amount_minor,
                    "CNY",
                    category,
                    note.strip(),
                    occurred_on,
                    now,
                ),
            )
            result = {
                "entry": {
                    "id": entry_id,
                    "amount": amount_minor / 100,
                    "currency": "CNY",
                    "category": category,
                    "note": note.strip(),
                    "occurred_on": occurred_on,
                    "revision": 1,
                },
                "message": "这笔记下了。",
            }
            db.execute(
                "INSERT INTO kit_receipts"
                "(user_id,idempotency_key,kit_id,operation,result,created_at) "
                "VALUES(?,?,?,?,?,?)",
                (
                    user_id,
                    idempotency_key,
                    "hymio.ledger",
                    "entries.create",
                    json.dumps(result, ensure_ascii=False, separators=(",", ":")),
                    now,
                ),
            )
            return result

    def list_entries(self, user_id, limit=20):
        if type(limit) is not int or not 1 <= limit <= 30:
            raise ValueError("Limit must be between 1 and 30")
        with self.transaction() as db:
            rows = db.execute(
                "SELECT * FROM ledger_entries WHERE user_id=? "
                "ORDER BY occurred_on DESC,created_at DESC LIMIT ?",
                (user_id, limit),
            )
            return [
                {
                    "id": row["id"],
                    "amount": row["amount_minor"] / 100,
                    "currency": row["currency"],
                    "category": row["category"],
                    "note": row["note"],
                    "occurred_on": row["occurred_on"],
                    "revision": row["revision"],
                }
                for row in rows
            ]

    def summary(self, user_id):
        month = date.today().strftime("%Y-%m")
        with self.transaction() as db:
            row = db.execute(
                "SELECT COALESCE(SUM(amount_minor),0) AS total_minor,COUNT(*) AS count "
                "FROM ledger_entries WHERE user_id=? AND substr(occurred_on,1,7)=?",
                (user_id, month),
            ).fetchone()
            return {
                "month": month,
                "total": row["total_minor"] / 100,
                "count": row["count"],
            }

    def save_generated(self, kit_id, owner_user_id, manifest, app_html):
        now = time.time()
        with self.transaction() as db:
            db.execute(
                "INSERT INTO generated_kits"
                "(kit_id,owner_user_id,manifest,app_html,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?) "
                "ON CONFLICT(kit_id) DO UPDATE SET manifest=excluded.manifest,"
                "updated_at=excluded.updated_at",
                (
                    kit_id,
                    owner_user_id,
                    json.dumps(manifest, ensure_ascii=False, separators=(",", ":")),
                    app_html,
                    now,
                    now,
                ),
            )

    def generated(self, owner_user_id):
        with self.transaction() as db:
            return [
                json.loads(row["manifest"])
                for row in db.execute(
                    "SELECT manifest FROM generated_kits WHERE owner_user_id=? "
                    "ORDER BY updated_at DESC",
                    (owner_user_id,),
                )
            ]

    def generated_app(self, owner_user_id, kit_id):
        with self.transaction() as db:
            row = db.execute(
                "SELECT app_html FROM generated_kits WHERE owner_user_id=? AND kit_id=?",
                (owner_user_id, kit_id),
            ).fetchone()
            if not row or not row["app_html"]:
                raise ValueError("Application UI is unavailable")
            return row["app_html"]

    def create_record(self, user_id, kit_id, data, idempotency_key):
        if not isinstance(idempotency_key, str) or not 1 <= len(idempotency_key) <= 256:
            raise ValueError("A stable idempotency key is required")
        with self.transaction() as db:
            receipt = db.execute(
                "SELECT kit_id,operation,result FROM kit_receipts "
                "WHERE user_id=? AND idempotency_key=?",
                (user_id, idempotency_key),
            ).fetchone()
            if receipt:
                if receipt["kit_id"] != kit_id or receipt["operation"] != "items.create":
                    raise ValueError("Idempotency key belongs to another operation")
                return json.loads(receipt["result"])
            item_id, now = uuid.uuid4().hex, time.time()
            result = {
                "item": {
                    "id": item_id,
                    "fields": data,
                    "revision": 1,
                },
                "message": "已保存。",
            }
            db.execute(
                "INSERT INTO kit_records(id,user_id,kit_id,data,revision,created_at) "
                "VALUES(?,?,?,?,1,?)",
                (
                    item_id,
                    user_id,
                    kit_id,
                    json.dumps(data, ensure_ascii=False, separators=(",", ":")),
                    now,
                ),
            )
            db.execute(
                "INSERT INTO kit_receipts"
                "(user_id,idempotency_key,kit_id,operation,result,created_at) "
                "VALUES(?,?,?,?,?,?)",
                (
                    user_id,
                    idempotency_key,
                    kit_id,
                    "items.create",
                    json.dumps(result, ensure_ascii=False, separators=(",", ":")),
                    now,
                ),
            )
            return result

    def list_records(self, user_id, kit_id, limit=20):
        if type(limit) is not int or not 1 <= limit <= 30:
            raise ValueError("Limit must be between 1 and 30")
        with self.transaction() as db:
            return [
                {
                    "id": row["id"],
                    "fields": json.loads(row["data"]),
                    "revision": row["revision"],
                    "created_at": row["created_at"],
                }
                for row in db.execute(
                    "SELECT * FROM kit_records WHERE user_id=? AND kit_id=? "
                    "ORDER BY created_at DESC LIMIT ?",
                    (user_id, kit_id, limit),
                )
            ]

    def count_records(self, user_id, kit_id):
        with self.transaction() as db:
            return db.execute(
                "SELECT COUNT(*) FROM kit_records WHERE user_id=? AND kit_id=?",
                (user_id, kit_id),
            ).fetchone()[0]
