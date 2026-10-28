"""Outbound personal-device transport for a single Backend process."""

import asyncio
import base64
import json
import secrets
import threading
import time
import uuid
from concurrent.futures import Future

from starlette.responses import JSONResponse
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocketDisconnect

from ..session_store import Unauthorized, digest
from .store import DeviceConflict


class DeviceLink:
    def __init__(self, store):
        self.store = store
        self.lock = threading.RLock()
        self.connections = {}
        self.pending = {}
        with store.transaction() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS link_pairings (
                    hash TEXT PRIMARY KEY, user_id TEXT NOT NULL, expires REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS link_credentials (
                    device_id TEXT PRIMARY KEY, hash TEXT UNIQUE NOT NULL, expires REAL NOT NULL);
                CREATE UNIQUE INDEX IF NOT EXISTS one_personal_mac
                    ON devices(user_id) WHERE kind='personal_mac' AND revoked_at IS NULL;
                CREATE UNIQUE INDEX IF NOT EXISTS one_personal_android
                    ON devices(user_id) WHERE kind='personal_android' AND revoked_at IS NULL;
            """)

    @staticmethod
    def report(frame, kind="personal_mac"):
        caps = frame.get("capabilities", [])
        permissions = frame.get("permissions", {})
        if not isinstance(caps, list) or any(
            c not in {"bash", "computer", "browser"} for c in caps
        ):
            raise ValueError("invalid_capabilities")
        if kind == "personal_android" and any(c in caps for c in ("bash", "browser")):
            raise ValueError("invalid_android_capability")
        if (
            not isinstance(permissions, dict)
            or set(permissions)
            - {"screen_recording", "accessibility", "shell", "unlocked", "screen_awake"}
            or any(type(value) is not bool for value in permissions.values())
        ):
            raise ValueError("invalid_permissions")
        return list(dict.fromkeys(caps)), permissions

    def pairing(self, user_id):
        code = secrets.token_hex(10)
        with self.store.transaction() as db:
            db.execute(
                "DELETE FROM link_pairings WHERE expires<? OR user_id=?", (time.time(), user_id)
            )
            db.execute(
                "INSERT INTO link_pairings VALUES(?,?,?)",
                (digest(code), user_id, time.time() + 300),
            )
        return {"code": code, "expires_at": time.time() + 300}

    def claim(self, code, name, kind="personal_mac"):
        if kind not in {"personal_mac", "personal_android"}:
            raise ValueError("invalid_device_kind")
        if not isinstance(code, str) or len(code) != 20:
            raise Unauthorized()
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
            raise ValueError("invalid_device_name")
        credential = secrets.token_urlsafe(32)
        device_id = uuid.uuid4().hex
        with self.store.transaction() as db:
            pair = db.execute(
                "SELECT * FROM link_pairings WHERE hash=? AND expires>?",
                (digest(code), time.time()),
            ).fetchone()
            if pair is None:
                raise Unauthorized()
            if db.execute(
                "SELECT 1 FROM devices WHERE user_id=? AND kind=? AND revoked_at IS NULL",
                (pair["user_id"], kind),
            ).fetchone():
                raise DeviceConflict(kind + "_already_bound")
            db.execute("DELETE FROM link_pairings WHERE hash=?", (digest(code),))
            db.execute(
                "INSERT INTO devices(id,user_id,name,kind,provider,provider_ref,created_at) "
                "VALUES(?,?,?,?,'link',?,?)",
                (device_id, pair["user_id"], name.strip(), kind, device_id, time.time()),
            )
            db.execute(
                "INSERT INTO link_credentials VALUES(?,?,?)",
                (device_id, digest(credential), time.time() + 90 * 86400),
            )
        return {"device_id": device_id, "credential": credential, "protocol": 1}

    def identity(self, credential):
        if not isinstance(credential, str) or len(credential) > 256:
            raise Unauthorized()
        with self.store.transaction() as db:
            row = db.execute(
                "SELECT d.* FROM devices d JOIN link_credentials c ON c.device_id=d.id "
                "WHERE c.hash=? AND c.expires>? AND d.revoked_at IS NULL",
                (digest(credential), time.time()),
            ).fetchone()
            if row is None:
                raise Unauthorized()
            return dict(row)

    def describe(self, device):
        with self.lock:
            connection = self.connections.get(device["id"])
            online = connection is not None and connection["seen"] > time.monotonic() - 35
            caps = connection["capabilities"] if online else []
            permissions = connection.get("permissions", {}) if online else {}
        state = (
            device["control_state"]
            if device["control_state"] != "active"
            else ("online" if online else "offline")
        )
        return {
            "device_id": device["id"],
            "name": device["name"],
            "kind": device["kind"],
            "provider": "link",
            "generation": device["generation"],
            "state": state,
            "provider_state": "online" if online else "offline",
            "online": state == "online",
            "capabilities": caps,
            "permissions": permissions,
            "guidance": (
                "Wake and unlock the Android phone locally; do not try passwords or bypass locking."
                if online
                and device["kind"] == "personal_android"
                and (
                    permissions.get("unlocked") is False or permissions.get("screen_awake") is False
                )
                else (
                    "On the Android phone, enable HymioDevice accessibility "
                    "and start screen sharing. "
                    "No Bash or DOM browser capability is exposed."
                    if device["kind"] == "personal_android"
                    else "Grant Screen Recording and Accessibility in HymioDevice on this Mac. "
                    "Shell is a separate local opt-in. Do not probe unsupported capabilities."
                )
                if online and not caps
                else ""
            ),
            "workspace": None,
            "resolution": {"width": 1280, "height": 800},
            "supported_actions": (
                ["screenshot", "click", "swipe", "scroll", "type", "key"]
                if device["kind"] == "personal_android"
                else ["screenshot", "click", "scroll", "type", "key"]
            ),
            "supported_keys": ["back", "home", "recents"]
            if device["kind"] == "personal_android"
            else None,
            "preserves_files_on_revoke": True,
            "replaces_device_id": None,
        }

    def execute(self, user_id, data):
        device_id, invocation = data["device_id"], data["invocation_id"]
        device = self.store.get(user_id, device_id)
        request = {"capability": data["capability"], "arguments": data["arguments"]}
        parent = data.get("parent_invocation_id")
        if parent:
            request["parent_invocation_id"] = parent
        timeout = data.get("timeout", 25)
        _, known = self.store.claim(user_id, device_id, invocation, request, timeout + 5)
        if known is not None:
            return known
        with self.lock:
            connection = self.connections.get(device_id)
            if (
                not connection
                or connection["seen"] < time.monotonic() - 35
                or data["capability"] not in connection["capabilities"]
            ):
                return self.store.finish(
                    user_id,
                    invocation,
                    {
                        "device_id": device_id,
                        "invocation_id": invocation,
                        "status": "failed",
                        "error": "link_offline_or_capability_unavailable",
                        "dispatched": False,
                    },
                )
            future = Future()
            self.pending[(user_id, invocation)] = future
            frame = {
                "v": 1,
                "type": "link.command",
                "device_id": device_id,
                "generation": device["generation"],
                "invocation_id": invocation,
                "expires_at": time.time() + timeout,
                **request,
                "execution_environment": data.get("execution_environment", {}),
            }
            sent = asyncio.run_coroutine_threadsafe(
                connection["socket"].send_json(frame), connection["loop"]
            )
        try:
            sent.result(timeout=min(timeout, 5))
            return future.result(timeout=timeout)
        except Exception:
            # A send timeout does not prove the device did not receive the operation.
            return self.store.finish(
                user_id,
                invocation,
                {
                    "device_id": device_id,
                    "invocation_id": invocation,
                    "status": "outcome_unknown",
                    "error": "Link interrupted; do not repeat the operation. Await saved result.",
                },
                release=False,
            )
        finally:
            with self.lock:
                self.pending.pop((user_id, invocation), None)

    def result(self, device, frame):
        invocation = frame["invocation_id"]
        if not isinstance(invocation, str) or not 1 <= len(invocation) <= 200:
            raise ValueError("invalid_invocation")
        if frame.get("generation") != device["generation"]:
            raise ValueError("stale_generation")
        payload = frame["payload"]
        if not isinstance(payload, dict) or len(json.dumps(payload)) > 12 * 1024 * 1024:
            raise ValueError("invalid_result")
        with self.store.transaction() as db:
            command = db.execute(
                "SELECT * FROM device_commands WHERE user_id=? AND device_id=? "
                "AND generation=? AND invocation_id=?",
                (device["user_id"], device["id"], device["generation"], invocation),
            ).fetchone()
            if command is None:
                raise ValueError("unknown_invocation")
            if command["status"] in {"succeeded", "failed"}:
                return json.loads(command["result"])
        unknown = payload.get("outcome_unknown") is True
        rejected = "operation_rejected" in payload
        if "screenshot_base64" in payload:
            image = base64.b64decode(payload.pop("screenshot_base64"), validate=True)
            if not image.startswith(b"\x89PNG\r\n\x1a\n") or len(image) > 8 * 1024 * 1024:
                raise ValueError("invalid_screenshot")
            media_id = self.store.media(device["user_id"], device["id"], image)
            payload["screenshot"] = {
                "attachment_id": media_id,
                "media_id": media_id,
                "url": "/devices/media/" + media_id,
                "mime_type": "image/png",
            }
        result = {
            "device_id": device["id"],
            "invocation_id": invocation,
            "duration_ms": max(0, round((time.time() - command["submitted_at"]) * 1000)),
            "status": "outcome_unknown" if unknown else "failed" if rejected else "succeeded",
            "result": payload,
        }
        result = self.store.finish(
            device["user_id"], invocation, result, release=not unknown, recover=True
        )
        with self.lock:
            future = self.pending.get((device["user_id"], invocation))
            if future and not future.done():
                future.set_result(result)
        return result

    def control(self, user_id, device_id, action):
        device = self.store.get(user_id, device_id)
        if device["provider"] != "link":
            raise ValueError("not_link_device")
        if action == "revoke":
            self.store.revoke(user_id, device_id)
            with self.lock:
                conn = self.connections.pop(device_id, None)
                if conn:
                    asyncio.run_coroutine_threadsafe(conn["socket"].close(code=4401), conn["loop"])
            return {"revoked": True, "stopped": None}
        self.store.set_control_state(
            user_id, device_id, "paused" if action == "pause" else "active"
        )
        return self.describe(self.store.get(user_id, device_id))

    def resolve(self, user_id, device_id, invocation):
        device = self.store.get(user_id, device_id)
        if device["provider"] != "link":
            raise ValueError("not_link_device")
        with self.lock:
            if (user_id, invocation) in self.pending:
                raise DeviceConflict("invocation_running")
        with self.store.transaction() as db:
            row = db.execute(
                "SELECT * FROM device_commands WHERE user_id=? AND device_id=? AND invocation_id=?",
                (user_id, device_id, invocation),
            ).fetchone()
            if row is not None and row["status"] == "running" and row["deadline"] < time.time():
                db.execute(
                    "UPDATE device_commands SET status='outcome_unknown',result=? "
                    "WHERE user_id=? AND invocation_id=?",
                    (
                        json.dumps({"status": "outcome_unknown", "device_id": device_id}),
                        user_id,
                        invocation,
                    ),
                )
            elif row is None or row["status"] != "outcome_unknown":
                raise DeviceConflict("not_unknown_invocation")
            db.execute(
                "DELETE FROM device_locks WHERE user_id=? AND device_id=? AND invocation_id=?",
                (user_id, device_id, invocation),
            )
        return {"resolved": True, "status": "outcome_unknown"}


def link_routes(settings, sessions, bearer, body, link):
    async def endpoint(request):
        try:
            if request.headers.get("origin") and request.headers["origin"] not in settings.origins:
                return JSONResponse({"error": "origin_denied"}, 403)
            data = await body(request)
            if request.url.path.endswith("/claim"):
                result = await asyncio.to_thread(
                    link.claim,
                    data.get("code"),
                    data.get("name", "Device"),
                    data.get("kind", "personal_mac"),
                )
            else:
                identity = await asyncio.to_thread(sessions.verify, bearer(request))
                if request.url.path.endswith("/resolve"):
                    if data.get("acknowledge_unknown") is not True:
                        raise ValueError("acknowledgement_required")
                    result = await asyncio.to_thread(
                        link.resolve,
                        identity["user_id"],
                        request.path_params["device_id"],
                        data["invocation_id"],
                    )
                else:
                    result = await asyncio.to_thread(link.pairing, identity["user_id"])
            return JSONResponse(result, headers={"Cache-Control": "no-store"})
        except Unauthorized:
            return JSONResponse({"error": "unauthorized"}, 401)
        except DeviceConflict as error:
            return JSONResponse({"error": str(error)}, 409)
        except KeyError:
            return JSONResponse({"error": "not_found"}, 404)
        except (ValueError, TypeError):
            return JSONResponse({"error": "bad_request"}, 400)

    async def socket(ws):
        await ws.accept()
        owner = uuid.uuid4().hex
        device = None
        try:
            if ws.headers.get("origin") and ws.headers["origin"] not in settings.origins:
                raise Unauthorized()
            raw = await asyncio.wait_for(ws.receive_text(), 10)
            if len(raw) > 16384:
                raise ValueError("attach_too_large")
            first = json.loads(raw)
            if (
                not isinstance(first, dict)
                or first.get("v") != 1
                or first.get("type") != "link.attach"
            ):
                raise ValueError("attach_required")
            credential = first.get("credential")
            device = await asyncio.to_thread(link.identity, credential)
            caps, permissions = link.report(first, device["kind"])
            with link.lock:
                old = link.connections.get(device["id"])
                link.connections[device["id"]] = {
                    "owner": owner,
                    "socket": ws,
                    "loop": asyncio.get_running_loop(),
                    "seen": time.monotonic(),
                    "capabilities": caps,
                    "permissions": permissions,
                }
            if old:
                await old["socket"].close(code=4009)
            await ws.send_json(
                {
                    "v": 1,
                    "type": "link.ready",
                    "device_id": device["id"],
                    "generation": device["generation"],
                }
            )
            while True:
                raw = await asyncio.wait_for(ws.receive_text(), 35)
                if len(raw) > 12 * 1024 * 1024:
                    raise ValueError("frame_too_large")
                frame = json.loads(raw)
                if not isinstance(frame, dict) or frame.get("v") != 1:
                    raise ValueError("invalid_version")
                device = await asyncio.to_thread(link.identity, credential)
                with link.lock:
                    current = link.connections.get(device["id"])
                    if current is None or current["owner"] != owner:
                        return
                    current["seen"] = time.monotonic()
                if frame.get("type") == "link.ping":
                    if "capabilities" in frame:
                        caps, permissions = link.report(frame, device["kind"])
                        with link.lock:
                            current["capabilities"] = caps
                            current["permissions"] = permissions
                    await ws.send_json({"v": 1, "type": "link.pong"})
                elif frame.get("type") == "link.result":
                    await asyncio.to_thread(link.result, device, frame)
                    await ws.send_json(
                        {"v": 1, "type": "link.ack", "invocation_id": frame["invocation_id"]}
                    )
                else:
                    raise ValueError("unknown_frame")
        except Unauthorized:
            await ws.close(code=4401)
        except (ValueError, KeyError, TypeError):
            await ws.close(code=1008)
        except (WebSocketDisconnect, TimeoutError, RuntimeError):
            pass
        finally:
            if device:
                with link.lock:
                    if link.connections.get(device["id"], {}).get("owner") == owner:
                        link.connections.pop(device["id"], None)

    return [
        Route("/devices/link/pairings", endpoint, methods=["POST"]),
        Route("/devices/link/claim", endpoint, methods=["POST"]),
        Route("/devices/link/{device_id}/resolve", endpoint, methods=["POST"]),
        WebSocketRoute("/devices/link/ws", socket),
    ]
