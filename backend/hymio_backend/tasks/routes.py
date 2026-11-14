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
            if request.url.path.startswith("/agents/"):
                return JSONResponse(
                    await service.oath(
                        uid,
                        "/subagents/activity",
                        {"agent_id": request.path_params["agent_id"], "limit": 60},
                    )
                )
            if action == "list":
                result = await asyncio.to_thread(store.list, uid)
            elif action == "get":
                result = await asyncio.to_thread(store.get, uid, data["task_id"])
            elif action in {"create", "capture"}:
                if action == "capture" and not internal:
                    raise ValueError("Only the agent can capture work already in progress")
                result = await asyncio.to_thread(
                    store.capture if action == "capture" else store.create,
                    uid,
                    data,
                    data.get("request_id"),
                )
            elif action in {"accept_suggestion", "dismiss_suggestion"}:
                if action == "accept_suggestion":
                    result = await asyncio.to_thread(
                        service.discovery.accept, uid, data["suggestion_id"]
                    )
                else:
                    await asyncio.to_thread(service.discovery.dismiss, uid, data["suggestion_id"])
                    return JSONResponse({"dismissed": True})
            elif action == "continue":
                result = await asyncio.to_thread(
                    store.request_continuation,
                    uid,
                    data["task_id"],
                    data.get("request_id")
                    or request.headers.get("idempotency-key")
                    or uuid.uuid4().hex,
                    data.get("content", ""),
                )
            elif action == "wait":
                result = await asyncio.to_thread(
                    store.wait,
                    uid,
                    data["run_id"],
                    data["wait_reason"],
                    data["content"],
                    data["next_step"],
                    data.get("resume_at"),
                    data.get("note_id") or data.get("request_id") or uuid.uuid4().hex,
                )
            elif action == "activity":
                value = await asyncio.to_thread(store.get, uid, data["task_id"])
                agent = next(
                    (
                        r.get("agent_id")
                        for r in value["runs"]
                        if r.get("agent_id") and r["agent_id"] != "pending"
                    ),
                    None,
                )
                return JSONResponse(
                    await service.oath(uid, "/subagents/activity", {"agent_id": agent})
                    if agent
                    else {"entries": [], "status": "not_delegated"}
                )
            elif action == "edit":
                result = await asyncio.to_thread(store.edit, uid, data["task_id"], data)
            elif action in {"pause", "resume", "cancel", "delete"}:
                result = await asyncio.to_thread(store.control, uid, data["task_id"], action)
            elif action == "start":
                result = await asyncio.to_thread(
                    store.start, uid, data["run_id"], data.get("request_id") if internal else None
                )
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
                    phase=data.get("phase"),
                    next_step=data.get("next_step"),
                    invocation_id=data.get("request_id") if internal else None,
                )
            else:
                raise ValueError("Unknown action")
            if isinstance(result, list):
                suggestions = (
                    await asyncio.to_thread(service.discovery.list, uid)
                    if hasattr(service, "discovery")
                    else []
                )
                return JSONResponse(
                    {
                        "tasks": result,
                        "suggestions": [v for v in suggestions if v["state"] == "pending"],
                    }
                )
            return JSONResponse(result)
        except Unauthorized:
            return JSONResponse({"error": "unauthorized"}, 401)
        except (KeyError, TypeError, ValueError) as exc:
            return JSONResponse({"error": "invalid_task", "message": str(exc)}, 400)
        except httpx.HTTPError:
            return JSONResponse({"error": "agent_unavailable"}, 503)

    return [
        Route("/tasks", endpoint, methods=["GET", "POST"]),
        Route("/agents/{agent_id}/activity", endpoint, methods=["GET"]),
        Route("/internal/tasks", endpoint, methods=["POST"]),
    ]
