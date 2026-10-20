import asyncio
import hmac

from starlette.responses import JSONResponse
from starlette.routing import Route

from ..session_store import Unauthorized
from .client import ContextError, NostalgiaClient
from .dreaming import dispatch


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
            if path == "/context/injection":
                return JSONResponse(
                    (await asyncio.to_thread(client.call, user_id, "injection"))["data"]
                )
            if path == "/context/records":
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
        Route("/context/injection", endpoint),
        Route("/context/records", endpoint, methods=["POST"]),
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
