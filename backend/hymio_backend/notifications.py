"""Durable user notifications and rule-driven Live Activity updates."""

import asyncio
import hashlib
import hmac
import logging
import time
from typing import Any

import httpx
import jwt
from starlette.responses import JSONResponse
from starlette.routing import Route

from .session_store import Unauthorized

_log = logging.getLogger(__name__)
PREFERENCE_KEYS = {
    "started": "start_enabled",
    "completion": "completion_enabled",
    "attention": "attention_enabled",
    "chat_reply": "reply_enabled",
}
KINDS = {"started", "completion", "attention", "chat_reply"}


def _boolean(data, key, default=None):
    value = data.get(key, default)
    if value is None or type(value) is not bool:
        raise ValueError(f"{key} must be a boolean")
    return int(value)


class NotificationService:
    def __init__(self, settings, sessions):
        self.settings = settings
        self.sessions = sessions
        self.wake = asyncio.Event()
        with sessions.transaction() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS notification_preferences (
                    user_id TEXT PRIMARY KEY,
                    start_enabled INTEGER NOT NULL DEFAULT 1,
                    completion_enabled INTEGER NOT NULL DEFAULT 1,
                    attention_enabled INTEGER NOT NULL DEFAULT 1,
                    reply_enabled INTEGER NOT NULL DEFAULT 1,
                    show_details INTEGER NOT NULL DEFAULT 0,
                    live_activity_enabled INTEGER NOT NULL DEFAULT 1,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS push_devices (
                    user_id TEXT NOT NULL,
                    installation_id TEXT NOT NULL,
                    token TEXT NOT NULL,
                    environment TEXT NOT NULL,
                    locale TEXT NOT NULL DEFAULT '',
                    timezone TEXT NOT NULL DEFAULT '',
                    app_version TEXT NOT NULL DEFAULT '',
                    active_until REAL NOT NULL DEFAULT 0,
                    invalidated INTEGER NOT NULL DEFAULT 0,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY(user_id, installation_id)
                );
                CREATE TABLE IF NOT EXISTS notification_outbox (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_key TEXT UNIQUE NOT NULL,
                    user_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    summary TEXT NOT NULL DEFAULT '',
                    route TEXT NOT NULL DEFAULT '',
                    task_id TEXT NOT NULL DEFAULT '',
                    run_id TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL,
                    deliver_after REAL NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'pending',
                    last_error TEXT NOT NULL DEFAULT '',
                    sent_at REAL
                );
                CREATE INDEX IF NOT EXISTS push_pending
                    ON notification_outbox(status, deliver_after, id);
                CREATE TABLE IF NOT EXISTS live_activity_tokens (
                    user_id TEXT NOT NULL,
                    installation_id TEXT NOT NULL,
                    activity_id TEXT NOT NULL,
                    token TEXT NOT NULL,
                    environment TEXT NOT NULL,
                    state TEXT NOT NULL DEFAULT 'working',
                    summary TEXT NOT NULL DEFAULT '',
                    task_id TEXT NOT NULL DEFAULT '',
                    started_at REAL NOT NULL DEFAULT 0,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY(user_id, installation_id, activity_id)
                );
                """
            )
        self.apns = None
        if self.configured:
            self.apns = httpx.AsyncClient(http2=True, timeout=15, trust_env=False)

    @property
    def configured(self):
        return bool(
            getattr(self.settings, "apns_key_file", None)
            and getattr(self.settings, "apns_key_id", "")
            and getattr(self.settings, "apns_team_id", "")
            and getattr(self.settings, "apns_bundle_id", "")
        )

    def _preferences(self, uid):
        with self.sessions.transaction() as db:
            row = db.execute(
                "SELECT * FROM notification_preferences WHERE user_id=?", (uid,)
            ).fetchone()
            if row is None:
                db.execute(
                    "INSERT INTO notification_preferences(user_id,updated_at) VALUES(?,?)",
                    (uid, time.time()),
                )
                row = db.execute(
                    "SELECT * FROM notification_preferences WHERE user_id=?", (uid,)
                ).fetchone()
            return dict(row)

    def status(self, uid):
        preferences = self._preferences(uid)
        with self.sessions.transaction() as db:
            devices = db.execute(
                "SELECT installation_id,environment,app_version,active_until,updated_at "
                "FROM push_devices WHERE user_id=? AND invalidated=0 ORDER BY updated_at DESC",
                (uid,),
            ).fetchall()
        return {
            "configured": self.configured,
            "preferences": {
                key: bool(preferences[key])
                for key in (
                    "start_enabled",
                    "completion_enabled",
                    "attention_enabled",
                    "reply_enabled",
                    "show_details",
                    "live_activity_enabled",
                )
            },
            "devices": [dict(row) for row in devices],
        }

    def update(self, uid, data):
        action = data.get("action", "get")
        if action == "get":
            return self.status(uid)
        if action == "register":
            installation = data.get("installation_id")
            token = data.get("token")
            environment = data.get("environment")
            if (
                not isinstance(installation, str)
                or not 8 <= len(installation) <= 160
                or not isinstance(token, str)
                or not 32 <= len(token) <= 512
                or environment not in {"sandbox", "production"}
            ):
                raise ValueError("invalid_push_registration")
            self._preferences(uid)
            with self.sessions.transaction() as db:
                db.execute(
                    "INSERT INTO push_devices(user_id,installation_id,token,environment,"
                    "locale,timezone,app_version,active_until,invalidated,updated_at) "
                    "VALUES(?,?,?,?,?,?,?,?,0,?) ON CONFLICT(user_id,installation_id) "
                    "DO UPDATE SET token=excluded.token,environment=excluded.environment,"
                    "locale=excluded.locale,timezone=excluded.timezone,"
                    "app_version=excluded.app_version,active_until=excluded.active_until,"
                    "invalidated=0,updated_at=excluded.updated_at",
                    (
                        uid,
                        installation,
                        token,
                        environment,
                        str(data.get("locale", ""))[:32],
                        str(data.get("timezone", ""))[:64],
                        str(data.get("app_version", ""))[:32],
                        time.time() + 90,
                        time.time(),
                    ),
                )
            self.wake.set()
            return {"registered": True}
        if action == "unregister":
            installation = data.get("installation_id")
            if not isinstance(installation, str) or not installation:
                raise ValueError("installation_id required")
            with self.sessions.transaction() as db:
                db.execute(
                    "UPDATE push_devices SET invalidated=1,updated_at=? "
                    "WHERE user_id=? AND installation_id=?",
                    (time.time(), uid, installation),
                )
                db.execute(
                    "DELETE FROM live_activity_tokens WHERE user_id=? AND installation_id=?",
                    (uid, installation),
                )
            return {"unregistered": True}
        if action == "presence":
            installation = data.get("installation_id")
            if not isinstance(installation, str) or not installation:
                raise ValueError("installation_id required")
            active = data.get("active", False)
            if type(active) is not bool:
                raise ValueError("active must be a boolean")
            with self.sessions.transaction() as db:
                db.execute(
                    "UPDATE push_devices SET active_until=?,updated_at=? "
                    "WHERE user_id=? AND installation_id=?",
                    (time.time() + (90 if active else 0), time.time(), uid, installation),
                )
            return {"recorded": True}
        if action == "preferences":
            updates = {}
            for key in (
                "start_enabled",
                "completion_enabled",
                "attention_enabled",
                "reply_enabled",
                "show_details",
                "live_activity_enabled",
            ):
                if key in data:
                    updates[key] = _boolean(data, key)
            if not updates:
                raise ValueError("no_preferences")
            self._preferences(uid)
            with self.sessions.transaction() as db:
                fields = ",".join(f"{key}=?" for key in updates)
                db.execute(
                    f"UPDATE notification_preferences SET {fields},updated_at=? WHERE user_id=?",
                    (*updates.values(), time.time(), uid),
                )
            return self.status(uid)
        if action == "live_activity_register":
            installation = data.get("installation_id")
            activity_id = data.get("activity_id")
            token = data.get("token")
            environment = data.get("environment")
            if (
                not isinstance(installation, str)
                or not installation
                or not isinstance(activity_id, str)
                or not 8 <= len(activity_id) <= 512
                or not isinstance(token, str)
                or not 32 <= len(token) <= 512
                or environment not in {"sandbox", "production"}
            ):
                raise ValueError("invalid_live_activity_registration")
            with self.sessions.transaction() as db:
                db.execute(
                    "INSERT INTO live_activity_tokens(user_id,installation_id,activity_id,"
                    "token,environment,state,summary,task_id,started_at,updated_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(user_id,installation_id,activity_id) "
                    "DO UPDATE SET token=excluded.token,environment=excluded.environment,"
                    "state=excluded.state,summary=excluded.summary,task_id=excluded.task_id,"
                    "updated_at=excluded.updated_at",
                    (
                        uid,
                        installation,
                        activity_id,
                        token,
                        environment,
                        str(data.get("state", "working"))[:24],
                        str(data.get("summary", ""))[:160],
                        str(data.get("task_id", ""))[:160],
                        time.time(),
                        time.time(),
                    ),
                )
            return {"registered": True}
        if action == "live_activity_unregister":
            activity_id = data.get("activity_id")
            if not isinstance(activity_id, str) or not activity_id:
                raise ValueError("activity_id required")
            with self.sessions.transaction() as db:
                db.execute(
                    "DELETE FROM live_activity_tokens WHERE user_id=? AND activity_id=?",
                    (uid, activity_id),
                )
            return {"unregistered": True}
        raise ValueError("unknown_notification_action")

    def notify(self, uid, data, request_id=""):
        kind = data.get("kind")
        if kind not in KINDS:
            raise ValueError("invalid_notification_kind")
        summary = data.get("summary", "")
        if not isinstance(summary, str) or len(summary.strip()) > 180:
            raise ValueError("notification summary must be at most 180 characters")
        task_id = data.get("task_id", "")
        run_id = data.get("run_id", "")
        if any(not isinstance(value, str) or len(value) > 160 for value in (task_id, run_id)):
            raise ValueError("invalid_notification_identity")
        preferences = self._preferences(uid)
        preference = PREFERENCE_KEYS[kind]
        if not preferences[preference]:
            return {"accepted": True, "status": "suppressed", "reason": "preference"}
        with self.sessions.transaction() as db:
            if task_id and not db.execute(
                "SELECT 1 FROM tasks WHERE user_id=? AND id=?", (uid, task_id)
            ).fetchone():
                raise ValueError("task_not_found")
            if run_id and not db.execute(
                "SELECT 1 FROM task_runs WHERE user_id=? AND id=? AND task_id=?",
                (uid, run_id, task_id),
            ).fetchone():
                raise ValueError("run_not_found")
            devices = db.execute(
                "SELECT 1 FROM push_devices WHERE user_id=? AND invalidated=0 LIMIT 1",
                (uid,),
            ).fetchone()
            if devices is None:
                return {"accepted": True, "status": "no_device"}
            stable = (
                f"task:{task_id}:run:{run_id}:{kind}"
                if task_id and run_id
                else "model:" + hashlib.sha256((request_id or summary).encode()).hexdigest()
            )
            now = time.time()
            db.execute(
                "INSERT OR IGNORE INTO notification_outbox(event_key,user_id,kind,summary,"
                "route,task_id,run_id,created_at,deliver_after) VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    stable,
                    uid,
                    kind,
                    summary.strip(),
                    ("task:" + task_id if task_id else "chat"),
                    task_id,
                    run_id,
                    now,
                    now,
                ),
            )
        self.wake.set()
        return {"accepted": True, "status": "queued"}

    def _jwt(self):
        now = int(time.time())
        cached = getattr(self, "_apns_jwt", None)
        if cached and cached[0] > now - 3000:
            return cached[1]
        key = self.settings.apns_key_file.read_text()
        token = jwt.encode(
            {"iss": self.settings.apns_team_id, "iat": now},
            key,
            algorithm="ES256",
            headers={"kid": self.settings.apns_key_id},
        )
        self._apns_jwt = (now, token)
        return token

    async def _send(self, token, environment, topic, payload, priority="10"):
        host = (
            "https://api.sandbox.push.apple.com"
            if environment == "sandbox"
            else "https://api.push.apple.com"
        )
        response = await self.apns.post(
            f"{host}/3/device/{token}",
            json=payload,
            headers={
                "authorization": "bearer " + self._jwt(),
                "apns-topic": topic,
                "apns-push-type": (
                    "alert" if topic == self.settings.apns_bundle_id else "liveactivity"
                ),
                "apns-priority": priority,
                "content-type": "application/json",
            },
        )
        return response

    def _payload(self, row, details):
        generic = {
            "started": ("Hymio", "正在处理一项任务"),
            "completion": ("任务已完成", "打开 Hymio 查看结果"),
            "attention": ("需要你确认", "有一项工作正在等你"),
            "chat_reply": ("回复已准备好", "打开 Hymio 继续对话"),
        }[row["kind"]]
        title, body = generic
        if details and row["summary"]:
            body = row["summary"]
        return {
            "aps": {
                "alert": {"title": title, "body": body},
                "sound": "default",
                "thread-id": row["task_id"] or row["route"],
                "interruption-level": "active",
            },
            "route": row["route"],
            "event_id": row["event_key"],
        }

    async def _update_live_activities(self, row, devices):
        if self.apns is None:
            return
        with self.sessions.transaction() as db:
            activities = db.execute(
                "SELECT * FROM live_activity_tokens WHERE user_id=?", (row["user_id"],)
            ).fetchall()
            task = None
            if row["task_id"]:
                task = db.execute(
                    "SELECT t.title,r.phase,r.next_step,r.status "
                    "FROM tasks t JOIN task_runs r ON r.task_id=t.id "
                    "WHERE t.user_id=? AND t.id=? AND r.id=?",
                    (row["user_id"], row["task_id"], row["run_id"]),
                ).fetchone()
        show_details = bool(
            self._preferences(row["user_id"])["show_details"]
        )
        now = time.time()
        for activity in activities:
            event = "end" if row["kind"] in {"completion", "chat_reply"} else "update"
            status = {
                "started": "working",
                "completion": "completed",
                "attention": "waiting",
                "chat_reply": "completed",
            }[row["kind"]]
            generic_phase = {
                "working": "正在处理",
                "completed": "已完成",
                "waiting": "等待你确认",
            }[status]
            phase = generic_phase
            if task and status in {"working", "waiting"}:
                phase = (task["phase"] or task["next_step"] or generic_phase)[:72]
            state = {
                "title": (
                    (task["title"] if task else row["summary"])[:80]
                    if show_details
                    else "Hymio"
                ),
                "phase": phase,
                "status": status,
                "activeCount": 1 if status == "working" else 0,
                "startedAt": int(float(activity["started_at"])),
                "updatedAt": int(now),
                "taskID": row["task_id"],
            }
            aps: dict[str, Any] = {
                "timestamp": int(now),
                "event": event,
                "content-state": state,
                "relevance-score": 100 if status != "completed" else 20,
                "stale-date": int(now + 8 * 3600),
            }
            if event == "end":
                aps["dismissal-date"] = int(now + 900)
            payload = {"aps": aps, "activity-id": activity["activity_id"]}
            try:
                response = await self._send(
                    activity["token"],
                    activity["environment"],
                    self.settings.apns_bundle_id + ".push-type.liveactivity",
                    payload,
                    priority="5",
                )
                if response.status_code == 410:
                    with self.sessions.transaction() as db:
                        db.execute(
                            "DELETE FROM live_activity_tokens WHERE user_id=? AND "
                            "installation_id=? AND activity_id=?",
                            (
                                activity["user_id"],
                                activity["installation_id"],
                                activity["activity_id"],
                            ),
                        )
                else:
                    response.raise_for_status()
            except Exception as exc:
                _log.warning("Live Activity push failed: %s", type(exc).__name__)

    async def deliver(self):
        now = time.time()
        with self.sessions.transaction() as db:
            rows = [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM notification_outbox WHERE status='pending' "
                    "AND deliver_after<=? ORDER BY id LIMIT 20",
                    (now,),
                )
            ]
        if not rows:
            return
        if not self.configured:
            with self.sessions.transaction() as db:
                db.executemany(
                    "UPDATE notification_outbox SET status='unconfigured',last_error=? WHERE id=?",
                    [("APNs is not configured", row["id"]) for row in rows],
                )
            return
        for row in rows:
            uid = row["user_id"]
            preferences = self._preferences(uid)
            with self.sessions.transaction() as db:
                devices = [
                    dict(device)
                    for device in db.execute(
                        "SELECT * FROM push_devices WHERE user_id=? AND invalidated=0",
                        (uid,),
                    )
                ]
            if not devices:
                status, error = "no_device", ""
            elif any(device["active_until"] >= time.time() for device in devices):
                status, error = "suppressed_foreground", ""
            else:
                accepted = 0
                errors = []
                payload = self._payload(row, bool(preferences["show_details"]))
                for device in devices:
                    try:
                        response = await self._send(
                            device["token"],
                            device["environment"],
                            self.settings.apns_bundle_id,
                            payload,
                        )
                        if response.status_code == 410:
                            with self.sessions.transaction() as db:
                                db.execute(
                                    "UPDATE push_devices SET invalidated=1 WHERE user_id=? "
                                    "AND installation_id=?",
                                    (uid, device["installation_id"]),
                                )
                        elif 200 <= response.status_code < 300:
                            accepted += 1
                        else:
                            errors.append(f"{response.status_code}")
                    except Exception as exc:
                        errors.append(type(exc).__name__)
                status = "sent" if accepted else "failed"
                error = ",".join(errors[:3])
            with self.sessions.transaction() as db:
                db.execute(
                    "UPDATE notification_outbox SET status=?,attempts=attempts+1,"
                    "last_error=?,sent_at=? WHERE id=?",
                    (status, error[:500], time.time() if status == "sent" else None, row["id"]),
                )
            await self._update_live_activities(row, devices)

    async def run(self):
        while True:
            try:
                await self.deliver()
            except Exception as exc:
                _log.warning("Notification delivery recovering: %s", type(exc).__name__)
            try:
                await asyncio.wait_for(self.wake.wait(), timeout=15)
                self.wake.clear()
            except TimeoutError:
                pass

    async def close(self):
        if self.apns is not None:
            await self.apns.aclose()


def notification_routes(settings, sessions, bearer, body, service):
    async def endpoint(request):
        try:
            data = await body(request) if request.method == "POST" else {}
            if request.url.path == "/internal/notifications":
                expected = settings.service_token_file.read_text().strip()
                if not hmac.compare_digest(bearer(request).encode(), expected.encode()):
                    raise Unauthorized()
                uid = data.get("user_id")
                if not isinstance(uid, str) or not uid:
                    raise ValueError("invalid_user")
                return JSONResponse(
                    service.notify(uid, data, str(data.get("request_id", ""))[:160])
                )
            identity = await asyncio.to_thread(sessions.verify, bearer(request))
            return JSONResponse(service.update(identity["user_id"], data))
        except Unauthorized:
            return JSONResponse({"error": "unauthorized"}, 401)
        except (KeyError, TypeError, ValueError) as error:
            return JSONResponse(
                {"error": "invalid_notification_request", "message": str(error)}, 400
            )

    return [
        Route("/notifications", endpoint, methods=["GET", "POST"]),
        Route("/internal/notifications", endpoint, methods=["POST"]),
    ]
