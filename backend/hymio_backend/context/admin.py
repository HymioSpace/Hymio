"""Administrator adapters keep context credentials on the server."""

import asyncio
import hashlib
import uuid

from starlette.responses import JSONResponse
from starlette.routing import Route

from ..session_store import Unauthorized
from .browse import browse
from .client import ContextError
from .dream_proposal import SYSTEM_PROMPT


def nostalgia_admin_routes(settings, sessions, discovery, bearer, body):
    async def endpoint(request):
        try:
            identity = await asyncio.to_thread(sessions.verify, bearer(request))
            if identity["user_id"] not in settings.admin_user_ids:
                return JSONResponse({"error": "administrator_required"}, 403)
            origin = request.headers.get("origin")
            if origin and origin not in settings.origins:
                return JSONResponse({"error": "origin_denied"}, 403)
            users = discovery.users()
            uid = request.query_params.get("user_id") or (users[0] if users else "")
            if request.method == "GET":
                result = {
                    "users": users,
                    "user_id": uid,
                    "prompt": SYSTEM_PROMPT,
                    "prompt_sha256": hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest(),
                }
                if uid:
                    if uid not in users:
                        raise ValueError("Unknown context owner")
                    try:
                        result["runtime"] = (
                            await asyncio.to_thread(discovery.client.call, uid, "operations.status")
                        )["data"]
                    except ContextError:
                        result["runtime"] = {"unavailable": True}
                    result["opportunities"] = await asyncio.to_thread(discovery.list, uid)
                return JSONResponse(result)
            data = await body(request, limit=32768)
            uid = data.get("user_id", uid)
            if uid not in users:
                raise ValueError("Unknown context owner")
            action = data.get("action")
            if action == "browse":
                return JSONResponse(
                    await asyncio.to_thread(browse, discovery.client, uid, data.get("options", {}))
                )
            if action == "read" and data.get("kind") in {"record", "artifact"}:
                return JSONResponse(
                    (
                        await asyncio.to_thread(
                            discovery.client.call,
                            uid,
                            "records.read" if data["kind"] == "record" else "artifacts.read",
                            item_id=data["id"],
                        )
                    )["data"]
                )
            if action in {"accept", "dismiss"}:
                if action == "accept":
                    return JSONResponse(await asyncio.to_thread(discovery.accept, uid, data["id"]))
                await asyncio.to_thread(discovery.dismiss, uid, data["id"])
                return JSONResponse({"dismissed": True})
            if action == "correct":
                text = data.get("text")
                if not isinstance(text, str) or not 1 <= len(text.strip()) <= 16000:
                    raise ValueError("Correction text required")
                # Append an operator correction; never erase original evidence or bypass dreaming.
                return JSONResponse(
                    (
                        await asyncio.to_thread(
                            discovery.client.call,
                            uid,
                            "records.append",
                            operation_id=request.headers.get("idempotency-key") or uuid.uuid4().hex,
                            data={
                                "item_type": "context",
                                "context_type": "text",
                                "context": {
                                    "text": text.strip(),
                                    "provenance": {"kind": "admin_correction"},
                                },
                                "source": {
                                    "kind": "user",
                                    "namespace": "hymio.admin.correction",
                                    "external_id": data.get("id", "general"),
                                },
                            },
                        )
                    )["data"]
                )
            raise ValueError("Unknown action")
        except Unauthorized:
            return JSONResponse({"error": "unauthorized"}, 401)
        except ContextError as exc:
            return JSONResponse(exc.data, exc.status)
        except (ValueError, KeyError, TypeError):
            return JSONResponse({"error": "invalid_context_request"}, 400)

    return [Route("/admin/api/nostalgia", endpoint, methods=["GET", "POST"])]
