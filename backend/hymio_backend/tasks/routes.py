import asyncio
import hmac
import uuid

import httpx
from starlette.responses import JSONResponse
from starlette.routing import Route

from ..session_store import Unauthorized


def task_routes(settings, sessions, service, bearer, body):
    store = service.store

    async def endpoint(request):
        try:
            origin = request.headers.get("origin")
            if origin and origin not in settings.origins:
                return JSONResponse({"error": "origin_denied"}, 403)
            data = await body(request, limit=131072) if request.method == "POST" else {}
            internal = request.url.path == "/internal/tasks"
            if internal:
                if not hmac.compare_digest(
                    bearer(request).encode(), settings.service_token_file.read_bytes().strip()
                ):
                    raise Unauthorized()
                uid = data["user_id"]
                if not isinstance(uid, str) or not uid:
                    raise ValueError("Invalid user")
                action = data["action"]
            else:
                identity = await asyncio.to_thread(sessions.verify, bearer(request))
                uid = identity["user_id"]
                action = data.get("action", "list") if request.method == "POST" else "list"
            if action == "list":
                result = await asyncio.to_thread(store.list, uid)
            elif action == "get":
                result = await asyncio.to_thread(store.get, uid, data["task_id"])
            elif action == "create":
                result = await asyncio.to_thread(store.create, uid, data, data.get("request_id"))
            elif action == "edit":
                result = await asyncio.to_thread(store.edit, uid, data["task_id"], data)
            elif action in {"pause", "resume", "cancel", "delete"}:
                result = await asyncio.to_thread(store.control, uid, data["task_id"], action)
            elif action == "start":
                result = await asyncio.to_thread(store.start, uid, data["run_id"])
            elif action == "delegate":
                result = await service.delegate(uid, data["run_id"])
            elif action in {"progress", "complete", "fail", "block"}:
                status = {
                    "progress": "running",
                    "complete": "succeeded",
                    "fail": "failed",
                    "block": "blocked",
                }[action]
                result = await asyncio.to_thread(
                    store.update_run,
                    uid,
                    data["run_id"],
                    status,
                    data["content"],
                    data.get("note_id") or uuid.uuid4().hex,
                )
            else:
                raise ValueError("Unknown action")
            return JSONResponse({"tasks": result} if isinstance(result, list) else result)
        except Unauthorized:
            return JSONResponse({"error": "unauthorized"}, 401)
        except (KeyError, TypeError, ValueError) as exc:
            return JSONResponse({"error": "invalid_task", "message": str(exc)}, 400)
        except httpx.HTTPError:
            return JSONResponse({"error": "agent_unavailable"}, 503)

    return [
        Route("/tasks", endpoint, methods=["GET", "POST"]),
        Route("/internal/tasks", endpoint, methods=["POST"]),
    ]
