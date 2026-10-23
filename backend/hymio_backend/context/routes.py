import asyncio
import hmac
import uuid

from starlette.responses import JSONResponse
from starlette.routing import Route

from ..session_store import Unauthorized
from .client import ContextError, NostalgiaClient
from .dreaming import dispatch
from .ingress import import_conversation


def context_routes(settings, sessions, bearer, body):
    client = NostalgiaClient(settings)

    async def endpoint(request):
        try:
            origin = request.headers.get("origin")
            if origin and origin not in settings.origins:
                return JSONResponse({"error": "origin_denied"}, 403)
            internal = request.url.path == "/internal/context/call"
            data = await body(request, limit=262144) if request.method == "POST" else {}
            if internal:
                expected = settings.service_token_file.read_text().strip()
                if not hmac.compare_digest(bearer(request).encode(), expected.encode()):
                    raise Unauthorized()
                user_id = data.pop("user_id")
                if not isinstance(user_id, str) or not user_id:
                    raise ValueError("Invalid user")
                if data.get("action") == "dreams.begin":
                    raise ValueError("Start dreams through Hymio, not a tool")
                result = await asyncio.to_thread(client.call, user_id, **data)
                return JSONResponse(result)
            identity = await asyncio.to_thread(sessions.verify, bearer(request))
            user_id = identity["user_id"]
            path = request.url.path
            if path == "/context/imports/conversation":
                result = await import_conversation(settings, client, user_id, bearer(request), data)
                return JSONResponse(result)
            if path in {"/context/assembly", "/context/events"}:
                action = path.rsplit("/", 1)[-1]
                return JSONResponse(
                    (
                        await asyncio.to_thread(
                            client.call, user_id, action, query=dict(request.query_params)
                        )
                    )["data"]
                )
            if path == "/context/records" and request.method == "GET":
                return JSONResponse(
                    (
                        await asyncio.to_thread(
                            client.call, user_id, "records.list", query=dict(request.query_params)
                        )
                    )["data"]
                )
            if path.startswith("/context/records/") or path.startswith("/context/artifacts/"):
                action = "records.read" if "/records/" in path else "artifacts.read"
                return JSONResponse(
                    (
                        await asyncio.to_thread(
                            client.call, user_id, action, item_id=request.path_params["item_id"]
                        )
                    )["data"]
                )
            if path == "/context/saves":
                if set(data) != {"text"} or not isinstance(data["text"], str):
                    raise ValueError("Provide text")
                text = data["text"].strip()
                if not 1 <= len(text) <= 16000:
                    raise ValueError("Invalid text length")
                key = request_key(request)
                result = await asyncio.to_thread(
                    client.call,
                    user_id,
                    "records.append",
                    operation_id=key,
                    data={
                        "item_type": "context",
                        "context_type": "text",
                        "context": {"text": text},
                        "source": {
                            "kind": "user",
                            "namespace": "hymio.saved",
                            "external_id": str(uuid.uuid5(uuid.NAMESPACE_URL, key)),
                        },
                    },
                )
                return JSONResponse(result["data"], result["status_code"])
            if path == "/context/injection":
                return JSONResponse(
                    (await asyncio.to_thread(client.call, user_id, "injection"))["data"]
                )
            if path == "/context/records":
                source = data.get("source") or {}
                if source.get("kind", "legacy") not in {"legacy", "user"}:
                    raise ValueError("Application projections require trusted ingress")
                key = request_key(request)
                result = await asyncio.to_thread(
                    client.call, user_id, "records.append", data=data, operation_id=key
                )
                return JSONResponse(result["data"], result["status_code"])
            if path == "/context/search":
                return JSONResponse(
                    (await asyncio.to_thread(client.call, user_id, "search", data=data))["data"]
                )
            key = request_key(request) if request.method == "POST" else None
            if path == "/context/dreams":
                if data:
                    raise ValueError("Dream start has no body fields")
                result = await asyncio.to_thread(
                    client.call, user_id, "dreams.begin", operation_id="begin:" + key
                )
                dream_id = result["data"]["dream_id"]
            else:
                dream_id = request.path_params["dream_id"]
            current = await asyncio.to_thread(
                client.call, user_id, "dreams.read", dream_id=dream_id
            )
            dream = current["data"]
            if request.method == "GET" or dream["state"] != "draft":
                return JSONResponse(dream)
            if path.endswith("/abort"):
                result = await asyncio.to_thread(
                    client.call,
                    user_id,
                    "dreams.abort",
                    dream_id=dream_id,
                    operation_id="abort:" + key,
                )
                return JSONResponse(result["data"])
            if data:
                raise ValueError("Resume has no body fields")
            injection = await asyncio.to_thread(client.call, user_id, "injection")
            result = await dispatch(
                settings, bearer(request), user_id, dream, injection["data"], key
            )
            return JSONResponse(result, 202)
        except Unauthorized:
            return JSONResponse({"error": "unauthorized"}, 401)
        except ContextError as exc:
            return JSONResponse(exc.data, exc.status)
        except (ValueError, KeyError, TypeError):
            return JSONResponse({"error": "bad_request"}, 400)
        except Exception:
            return JSONResponse({"error": "context_unavailable"}, 503)

    return [
        Route("/internal/context/call", endpoint, methods=["POST"]),
        Route("/context/imports/conversation", endpoint, methods=["POST"]),
        Route("/context/assembly", endpoint),
        Route("/context/events", endpoint),
        Route("/context/saves", endpoint, methods=["POST"]),
        Route("/context/records/{item_id}", endpoint),
        Route("/context/artifacts/{item_id}", endpoint),
        Route("/context/injection", endpoint),
        Route("/context/records", endpoint, methods=["GET", "POST"]),
        Route("/context/search", endpoint, methods=["POST"]),
        Route("/context/dreams", endpoint, methods=["POST"]),
        Route("/context/dreams/{dream_id}", endpoint),
        Route("/context/dreams/{dream_id}/resume", endpoint, methods=["POST"]),
        Route("/context/dreams/{dream_id}/abort", endpoint, methods=["POST"]),
    ]


def request_key(request):
    key = request.headers.get("idempotency-key", "")
    if not 1 <= len(key) <= 120:
        raise ValueError("Provide Idempotency-Key of 1..120 characters")
    return key
