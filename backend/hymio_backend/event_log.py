"""Durable message lifecycle and indexed, bounded event search."""

import hashlib
import json
import re
import sqlite3
import time
import unicodedata
from contextlib import contextmanager, nullcontext


def tokens(text):
    # Character tokens make short Chinese queries work with SQLite's unicode tokenizer.
    normalized = re.sub(
        r"([\u3400-\u9fff])", r" \1 ", unicodedata.normalize("NFKC", text).casefold()
    )
    return " ".join(re.findall(r"[^\W_]+", normalized))


def safe(value, depth=0):
    if depth > 8:
        return "[nested value omitted]"
    if isinstance(value, dict):
        return {
            str(k): "[redacted]"
            if re.search(
                r"password|secret|authorization|api.?key|access.?token|refresh.?token", str(k), re.I
            )
            else safe(v, depth + 1)
            for k, v in list(value.items())[:100]
        }
    if isinstance(value, list):
        return [safe(v, depth + 1) for v in value[:100]]
    if isinstance(value, str):
        if value.startswith(("{", "[")) and len(value) < 131072:
            try:
                return safe(json.loads(value), depth + 1)
            except ValueError:
                pass
        return re.sub(r"(?i)Bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [redacted]", value)[:16000]
    return value


class EventLog:
    def __init__(self, path, *, retention_days=7, max_events=20000):
        self.path = path
        self.retention = retention_days * 86400
        self.max_events = max_events
        self.last_prune = 0.0
        with self.connect(write=True) as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY, event_key TEXT UNIQUE NOT NULL,
                    user_id TEXT NOT NULL, message_id TEXT NOT NULL, trace_id TEXT NOT NULL,
                    channel TEXT NOT NULL, stage TEXT NOT NULL, occurred_at REAL NOT NULL,
                    source TEXT NOT NULL DEFAULT 'application',
                    body TEXT NOT NULL, searchable TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS events_message ON events(user_id,message_id,id);
                CREATE INDEX IF NOT EXISTS events_trace ON events(user_id,trace_id,id);
                CREATE INDEX IF NOT EXISTS events_time ON events(occurred_at,channel);
                CREATE VIRTUAL TABLE IF NOT EXISTS event_fts USING fts5(
                    searchable, content='events',content_rowid='id');
                CREATE TRIGGER IF NOT EXISTS events_insert AFTER INSERT ON events BEGIN
                    INSERT INTO event_fts(rowid,searchable) VALUES(new.id,new.searchable); END;
                CREATE TRIGGER IF NOT EXISTS events_delete AFTER DELETE ON events BEGIN
                    INSERT INTO event_fts(event_fts,rowid,searchable)
                        VALUES('delete',old.id,old.searchable); END;
                CREATE TABLE IF NOT EXISTS trace_jobs (
                    user_id TEXT NOT NULL,trace_id TEXT NOT NULL,message_id TEXT NOT NULL,
                    channel TEXT NOT NULL,next_at REAL NOT NULL,expires_at REAL NOT NULL,
                    PRIMARY KEY(user_id,trace_id));
                CREATE INDEX IF NOT EXISTS jobs_due ON trace_jobs(next_at);
            """)
            columns = {row[1] for row in db.execute("PRAGMA table_info(events)")}
            if "source" not in columns:
                db.execute(
                    "ALTER TABLE events ADD COLUMN source TEXT NOT NULL DEFAULT 'application'"
                )
            db.execute(
                "CREATE INDEX IF NOT EXISTS events_source_time "
                "ON events(source,occurred_at,channel)"
            )
            db.execute(
                """UPDATE events SET source='otel'
                WHERE source='application' AND (
                  stage IN ('server.step.status','invoke_agent','queue.publish','queue.consume')
                  OR stage LIKE 'oath.%'
                  OR stage LIKE 'chat %'
                  OR stage LIKE 'gen_ai.%'
                  OR stage LIKE 'execute_tool %'
                )"""
            )
        path.chmod(0o600)
        self.repair_trace_links()

    @contextmanager
    def connect(self, *, write=False):
        db = sqlite3.connect(self.path, timeout=2)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA cache_size=-1024")
            db.execute("PRAGMA temp_store=FILE")
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def append(
        self,
        user_id,
        message_id,
        stage,
        body,
        *,
        trace_id="",
        channel="unknown",
        key=None,
        occurred_at=None,
        source="application",
        _db=None,
    ):
        body = json.dumps(safe(body), ensure_ascii=False, separators=(",", ":"))[:32768]
        now = time.time()
        identity = key or f"{user_id}:{message_id}:{stage}"
        if not key and not message_id:
            identity += ":" + trace_id + ":" + hashlib.sha256(body.encode()).hexdigest()
        event_key = hashlib.sha256(identity.encode()).hexdigest()
        with nullcontext(_db) if _db is not None else self.connect(write=True) as db:
            inserted = (
                db.execute(
                    "INSERT OR IGNORE INTO events(event_key,user_id,message_id,trace_id,channel,"
                    "stage,occurred_at,source,body,searchable) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (
                        event_key,
                        user_id,
                        message_id,
                        trace_id,
                        channel,
                        stage,
                        occurred_at or now,
                        source,
                        body,
                        tokens(f"{message_id} {trace_id} {stage} {source} {body}"),
                    ),
                ).rowcount
                > 0
            )
            if trace_id:
                if message_id:
                    db.execute(
                        "UPDATE events SET trace_id=? WHERE user_id=? AND message_id=? "
                        "AND trace_id=''",
                        (trace_id, user_id, message_id),
                    )
                db.execute(
                    "INSERT INTO trace_jobs VALUES(?,?,?,?,?,?) ON CONFLICT(user_id,trace_id) "
                    "DO UPDATE SET message_id=CASE WHEN excluded.message_id<>'' "
                    "THEN excluded.message_id "
                    "ELSE trace_jobs.message_id END",
                    (user_id, trace_id, message_id, channel, now, now + 3600),
                )
            if now - self.last_prune >= 60:
                db.execute("DELETE FROM events WHERE occurred_at<?", (now - self.retention,))
                db.execute(
                    "DELETE FROM events WHERE id IN "
                    "(SELECT id FROM events ORDER BY id DESC LIMIT -1 OFFSET ?)",
                    (self.max_events,),
                )
                db.execute("DELETE FROM trace_jobs WHERE expires_at<?", (now,))
                self.last_prune = now
        return inserted

    def search(self, query, *, since, channel="", source="application", limit=100):
        phrase = tokens(query)
        if not phrase:
            return []
        with self.connect() as db:
            rows = [
                dict(r)
                for r in db.execute(
                    "SELECT e.* FROM event_fts JOIN events e ON e.id=event_fts.rowid "
                    "WHERE event_fts MATCH ? AND e.occurred_at>=? "
                    + ("AND e.channel=? " if channel else "")
                    + ("AND e.source=? " if source else "")
                    + "ORDER BY e.occurred_at DESC LIMIT ?",
                    tuple(
                        ['"' + phrase + '"', since]
                        + ([channel] if channel else [])
                        + ([source] if source else [])
                        + [limit]
                    ),
                )
            ]
        for row in rows:
            row["snippet"] = row["body"]
        return rows

    def indexed_messages(self, *, since, channel="", source="application"):
        with self.connect() as db:
            return int(
                db.execute(
                    "SELECT COUNT(DISTINCT user_id || ':' || message_id) FROM events "
                    "WHERE occurred_at>=?"
                    + (" AND channel=?" if channel else "")
                    + (" AND source=?" if source else ""),
                    tuple([since] + ([channel] if channel else []) + ([source] if source else [])),
                ).fetchone()[0]
            )

    def detail(self, user_id, *, message_id="", trace_id="", source="application"):
        with self.connect() as db:
            rows = list(
                db.execute(
                    "SELECT * FROM events WHERE user_id=? AND "
                    + ("message_id=? " if message_id else "trace_id=? ")
                    + ("AND source=? " if source else "")
                    + "ORDER BY id LIMIT 500",
                    (user_id, message_id or trace_id, source)
                    if source
                    else (user_id, message_id or trace_id),
                )
            )
        if not rows:
            return []
        return [
            {
                "span_id": "message-"
                + hashlib.sha256((user_id + (message_id or trace_id)).encode()).hexdigest()[:16],
                "name": "message.lifecycle",
                "parent_span_id": None,
                "trace_id": trace_id or "message:" + message_id,
                "kind": "INTERNAL",
                "status": "UNSET",
                "duration_ms": None,
                "links": [],
                "start_unix_nano": int(rows[0]["occurred_at"] * 1e9),
                "end_unix_nano": None,
                "attributes": {"hymio.message_id": rows[0]["message_id"]},
                "events": [
                    {
                        "name": r["stage"],
                        "unix_nano": int(r["occurred_at"] * 1e9),
                        "attributes": {"body": r["body"]},
                    }
                    for r in rows
                ],
            }
        ]

    def index_trace(self, job, trace):
        count = 0
        with self.connect(write=True) as db:
            for span in trace.get("spans", [])[:128]:
                span_id = str(span.get("span_id", ""))
                for i, event in enumerate(
                    [
                        {"name": span.get("name"), "attributes": span.get("attributes", {})},
                        *span.get("events", []),
                    ][:100]
                ):
                    if count >= 256:
                        return
                    count += 1
                    self.append(
                        job["user_id"],
                        job["message_id"],
                        str(event.get("name", "trace")),
                        event,
                        trace_id=job["trace_id"],
                        channel=job["channel"],
                        source="otel",
                        _db=db,
                        key=f"{job['user_id']}:{job['trace_id']}:{span_id}:{i}",
                    )

    def repair_trace_links(self):
        with self.connect(write=True) as db:
            rows = list(
                db.execute(
                    "SELECT id,user_id,message_id,channel,body FROM events "
                    "WHERE trace_id='' AND stage IN ('gateway.ack','client.ack') "
                    "ORDER BY id DESC LIMIT 10000"
                )
            )
            now = time.time()
            for row in rows:
                try:
                    trace_id = str(json.loads(row["body"]).get("trace_id", ""))
                except (TypeError, ValueError):
                    continue
                if not re.fullmatch(r"[0-9a-f]{32}", trace_id):
                    continue
                db.execute(
                    "UPDATE events SET trace_id=? WHERE user_id=? AND message_id=? AND trace_id=''",
                    (trace_id, row["user_id"], row["message_id"]),
                )
                db.execute(
                    "INSERT INTO trace_jobs VALUES(?,?,?,?,?,?) "
                    "ON CONFLICT(user_id,trace_id) DO UPDATE SET "
                    "message_id=CASE WHEN excluded.message_id<>'' THEN excluded.message_id "
                    "ELSE trace_jobs.message_id END",
                    (
                        row["user_id"],
                        trace_id,
                        row["message_id"],
                        row["channel"],
                        now,
                        now + 3600,
                    ),
                )

    def trace_links(self):
        with self.connect() as db:
            rows = []
            for row in db.execute(
                """SELECT user_id,message_id,MAX(trace_id) AS trace_id,MAX(channel) AS channel,
                MIN(CASE WHEN source='application' AND stage='gateway.received'
                    THEN occurred_at END) AS received_at,
                MIN(CASE WHEN source='application' AND stage='gateway.ack'
                    THEN occurred_at END) AS ack_at
                FROM events WHERE message_id<>''
                GROUP BY user_id,message_id
                HAVING MAX(trace_id)<>''
                ORDER BY MAX(id) DESC LIMIT 5000"""
            ):
                link = dict(row)
                link["accepted_ms"] = (
                    round(max(0, (link["ack_at"] - link["received_at"]) * 1000), 3)
                    if link["ack_at"] is not None and link["received_at"] is not None
                    else None
                )
                link.pop("received_at")
                link.pop("ack_at")
                rows.append(link)
            return rows

    def jobs(self):
        with self.connect() as db:
            return [
                dict(r)
                for r in db.execute(
                    "SELECT * FROM trace_jobs WHERE next_at<=? AND expires_at>? "
                    "ORDER BY next_at LIMIT 4",
                    (time.time(), time.time()),
                )
            ]

    def defer(self, job, *, complete=False):
        with self.connect(write=True) as db:
            if complete:
                db.execute(
                    "DELETE FROM trace_jobs WHERE user_id=? AND trace_id=?",
                    (job["user_id"], job["trace_id"]),
                )
            else:
                db.execute(
                    "UPDATE trace_jobs SET next_at=? WHERE user_id=? AND trace_id=?",
                    (time.time() + 30, job["user_id"], job["trace_id"]),
                )


async def run_indexer(settings, sessions, upstream):
    import asyncio
    import logging

    while True:
        try:
            token_file = settings.oath_admin_token_file
            if token_file is not None:
                for job in await asyncio.to_thread(sessions.event_log.jobs):
                    complete = False
                    try:
                        buffer = bytearray()
                        async with upstream.stream(
                            "GET",
                            settings.oath_biz.rstrip("/") + "/admin/trace",
                            params={"user_id": job["user_id"], "trace_id": job["trace_id"]},
                            headers={"Authorization": "Bearer " + token_file.read_text().strip()},
                            timeout=5,
                        ) as response:
                            response.raise_for_status()
                            async for chunk in response.aiter_bytes():
                                if len(buffer) + len(chunk) > 8 * 1024 * 1024:
                                    complete = True
                                    await asyncio.to_thread(
                                        sessions.event_log.append,
                                        job["user_id"],
                                        job["message_id"],
                                        "trace.index_size_limit",
                                        {"limit_bytes": 8 * 1024 * 1024},
                                        trace_id=job["trace_id"],
                                        channel=job["channel"],
                                        source="otel",
                                    )
                                    break
                                buffer.extend(chunk)
                        if complete:
                            await asyncio.to_thread(sessions.event_log.defer, job, complete=True)
                            continue
                        trace = json.loads(buffer)
                        await asyncio.to_thread(sessions.event_log.index_trace, job, trace)
                        if job["message_id"]:
                            from .client_telemetry import trace_stats

                            stats = trace_stats(trace)

                            def save_stats():
                                with sessions.transaction() as db:
                                    db.execute(
                                        "UPDATE client_turns SET step_count=?,model_calls=?,"
                                        "tool_calls=?,tool_successes=?,tool_ms=? "
                                        "WHERE user_id=? AND message_id=?",
                                        (
                                            stats.get("step_count"),
                                            stats.get("model_calls"),
                                            stats.get("tool_calls"),
                                            stats.get("tool_successes"),
                                            stats.get("tool_ms"),
                                            job["user_id"],
                                            job["message_id"],
                                        ),
                                    )

                            await asyncio.to_thread(save_stats)
                        spans = trace.get("spans", [])
                        complete = bool(spans) and all(s.get("end_unix_nano") for s in spans)
                    except Exception:
                        logging.getLogger(__name__).warning("Trace index enrichment unavailable")
                    await asyncio.to_thread(sessions.event_log.defer, job, complete=complete)
        except Exception:
            logging.getLogger(__name__).exception("Event index worker unavailable")
        await asyncio.sleep(5)
