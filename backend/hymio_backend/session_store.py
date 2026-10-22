import hashlib
import re
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager
from urllib.parse import urlsplit


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def token():
    return secrets.token_urlsafe(32)


def display_name(claims):
    for key in ("name", "preferred_username", "nickname"):
        value = claims.get(key)
        if (
            isinstance(value, str)
            and value.strip()
            and not re.fullmatch(
                r"[0-9a-fA-F]{32}|[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}",
                value.strip(),
            )
        ):
            return value.strip()[:160]
    return "我的账号"


class Unauthorized(Exception):
    pass


class SessionStore:
    def __init__(self, settings):
        self.settings = settings
        settings.database.parent.mkdir(parents=True, exist_ok=True)
        with self.transaction() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY, issuer TEXT NOT NULL, subject TEXT NOT NULL,
                    name TEXT NOT NULL, UNIQUE(issuer, subject));
                CREATE TABLE IF NOT EXISTS logins (
                    flow_hash TEXT PRIMARY KEY, state_hash TEXT UNIQUE NOT NULL,
                    verifier TEXT NOT NULL, nonce TEXT NOT NULL, expires REAL NOT NULL,
                    status TEXT NOT NULL, user_id TEXT, return_uri TEXT NOT NULL, grant_hash TEXT);
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY, user_id TEXT NOT NULL, expires REAL NOT NULL,
                    revoked INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS credentials (
                    hash TEXT PRIMARY KEY, session_id TEXT NOT NULL,
                    kind TEXT NOT NULL, expires REAL NOT NULL, used INTEGER NOT NULL DEFAULT 0);
                CREATE INDEX IF NOT EXISTS credentials_session ON credentials(session_id);
                CREATE INDEX IF NOT EXISTS credentials_expiry ON credentials(kind, expires);
                CREATE INDEX IF NOT EXISTS sessions_expiry ON sessions(expires);
                CREATE TABLE IF NOT EXISTS client_turns (
                    user_id TEXT NOT NULL, message_id TEXT NOT NULL,
                    channel TEXT NOT NULL, client_id TEXT NOT NULL DEFAULT '',
                    device_id TEXT NOT NULL DEFAULT '', trace_id TEXT NOT NULL DEFAULT '',
                    sent_at REAL NOT NULL, accepted_ms REAL, first_response_ms REAL,
                    first_renderable_ms REAL, first_paint_ms REAL, completed_ms REAL,
                    outcome TEXT NOT NULL, step_count INTEGER, model_calls INTEGER,
                    tool_calls INTEGER, tool_successes INTEGER, tool_ms REAL,
                    received_at REAL NOT NULL, PRIMARY KEY(user_id, message_id));
                CREATE INDEX IF NOT EXISTS client_turns_recent
                    ON client_turns(received_at, channel);
            """)
        settings.database.chmod(0o600)
        from .event_log import EventLog

        self.event_log = EventLog(
            settings.database.with_name("observability.sqlite3"),
            retention_days=max(1, min(90, getattr(settings, "observability_retention_days", 7))),
            max_events=max(100, min(1000000, getattr(settings, "observability_max_events", 20000))),
        )
        with self.transaction() as db:
            for link in self.event_log.trace_links():
                db.execute(
                    "UPDATE client_turns SET "
                    "trace_id=CASE WHEN trace_id='' THEN ? ELSE trace_id END,"
                    "accepted_ms=COALESCE(accepted_ms,?),"
                    "outcome=CASE WHEN outcome='sent' AND ? IS NOT NULL "
                    "THEN 'accepted' ELSE outcome END "
                    "WHERE user_id=? AND message_id=?",
                    (
                        link["trace_id"],
                        link["accepted_ms"],
                        link["accepted_ms"],
                        link["user_id"],
                        link["message_id"],
                    ),
                )

    @contextmanager
    def transaction(self):
        db = sqlite3.connect(self.settings.database, timeout=5)
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

    def start(self, return_uri):
        handle, state, verifier, nonce = (token() for _ in range(4))
        with self.transaction() as db:
            db.execute("DELETE FROM logins WHERE expires < ?", (time.time(),))
            if db.execute("SELECT COUNT(*) FROM logins").fetchone()[0] >= 5000:
                raise RuntimeError("Login capacity reached")
            db.execute(
                "INSERT INTO logins VALUES(?,?,?,?,?,'pending',NULL,?,NULL)",
                (digest(handle), digest(state), verifier, nonce, time.time() + 300, return_uri),
            )
        return handle, state, verifier, nonce

    def claim_callback(self, state):
        with self.transaction() as db:
            flow = db.execute(
                "SELECT * FROM logins WHERE state_hash=? AND status='pending' AND expires>?",
                (digest(state), time.time()),
            ).fetchone()
            if not flow:
                raise Unauthorized()
            db.execute("UPDATE logins SET status='processing' WHERE state_hash=?", (digest(state),))
            return dict(flow)

    def finish(self, state, claims=None):
        grant = token()
        with self.transaction() as db:
            user_id = None
            if claims:
                user_id = self._map_user(db, claims)
            db.execute(
                "UPDATE logins SET status=?,user_id=?,verifier='',nonce='',grant_hash=? "
                "WHERE state_hash=?",
                ("done" if claims else "failed", user_id, digest(grant), digest(state)),
            )
            row = db.execute(
                "SELECT return_uri FROM logins WHERE state_hash=?", (digest(state),)
            ).fetchone()
            return grant, row[0]

    def _map_user(self, db, claims):
        issuer, subject = claims["iss"], claims["sub"]
        if not isinstance(subject, str) or not subject:
            raise Unauthorized()
        db.execute(
            "INSERT INTO users VALUES(?,?,?,?) ON CONFLICT(issuer,subject) "
            "DO UPDATE SET name=excluded.name",
            (uuid.uuid4().hex, issuer, subject, display_name(claims)),
        )
        return db.execute(
            "SELECT user_id FROM users WHERE issuer=? AND subject=?", (issuer, subject)
        ).fetchone()[0]

    def create_session(self, claims):
        with self.transaction() as db:
            user_id = self._map_user(db, claims)
            session_id, expiry = uuid.uuid4().hex, time.time() + self.settings.refresh_seconds
            db.execute("INSERT INTO sessions VALUES(?,?,?,0)", (session_id, user_id, expiry))
            return self._issue(db, session_id, user_id, expiry)

    def _issue(self, db, session_id, user_id, session_expiry):
        now = time.time()
        db.execute("DELETE FROM credentials WHERE kind='access' AND (expires<=? OR used=1)", (now,))
        db.execute(
            "DELETE FROM credentials WHERE session_id IN "
            "(SELECT id FROM sessions WHERE expires<=? OR revoked=1)",
            (now,),
        )
        db.execute("DELETE FROM sessions WHERE expires<=? OR revoked=1", (now,))
        access, refresh = token(), token()
        expiry = min(time.time() + self.settings.access_seconds, session_expiry)
        db.executemany(
            "INSERT INTO credentials VALUES(?,?,?,?,0)",
            [
                (digest(access), session_id, "access", expiry),
                (digest(refresh), session_id, "refresh", session_expiry),
            ],
        )
        name = db.execute("SELECT name FROM users WHERE user_id=?", (user_id,)).fetchone()[0]
        return {
            "access_token": access,
            "refresh_token": refresh,
            "expires_at": expiry,
            "user_id": user_id,
            "name": name,
            "oath_ws": urlsplit(self.settings.public_url)
            ._replace(
                scheme="wss" if urlsplit(self.settings.public_url).scheme == "https" else "ws",
                path=urlsplit(self.settings.public_url).path.rstrip("/") + "/agent/ws",
            )
            .geturl(),
            "oath_biz": self.settings.public_url.rstrip("/") + "/oath-biz",
        }

    def exchange(self, handle, grant):
        with self.transaction() as db:
            flow = db.execute(
                "SELECT * FROM logins WHERE flow_hash=? AND expires>?",
                (digest(handle), time.time()),
            ).fetchone()
            if not flow or flow["status"] != "done" or flow["grant_hash"] != digest(grant):
                raise Unauthorized()
            db.execute("DELETE FROM logins WHERE flow_hash=?", (digest(handle),))
            session_id, expiry = uuid.uuid4().hex, time.time() + self.settings.refresh_seconds
            db.execute(
                "INSERT INTO sessions VALUES(?,?,?,0)", (session_id, flow["user_id"], expiry)
            )
            return self._issue(db, session_id, flow["user_id"], expiry)

    def _find(self, db, credential, kind):
        row = db.execute(
            """SELECT c.*, s.user_id, s.revoked, s.expires AS session_expiry
            FROM credentials c JOIN sessions s ON s.id=c.session_id WHERE c.hash=? AND c.kind=?""",
            (digest(credential), kind),
        ).fetchone()
        if (
            not row
            or row["revoked"]
            or row["expires"] <= time.time()
            or row["session_expiry"] <= time.time()
        ):
            raise Unauthorized()
        return row

    def verify(self, credential):
        with self.transaction() as db:
            row = self._find(db, credential, "access")
            if row["used"]:
                raise Unauthorized()
            return {"user_id": row["user_id"], "expires_at": row["expires"]}

    def refresh(self, credential):
        reused = False
        with self.transaction() as db:
            row = self._find(db, credential, "refresh")
            if row["used"]:
                db.execute("UPDATE sessions SET revoked=1 WHERE id=?", (row["session_id"],))
                reused = True
            else:
                db.execute("UPDATE credentials SET used=1 WHERE session_id=?", (row["session_id"],))
                result = self._issue(db, row["session_id"], row["user_id"], row["session_expiry"])
        if reused:
            raise Unauthorized()
        return result

    def logout(self, credential):
        with self.transaction() as db:
            row = db.execute(
                "SELECT session_id FROM credentials WHERE hash=?", (digest(credential),)
            ).fetchone()
            if row:
                db.execute("UPDATE sessions SET revoked=1 WHERE id=?", (row[0],))
