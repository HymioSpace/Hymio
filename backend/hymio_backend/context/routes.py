import asyncio
import hmac
import uuid

from starlette.responses import JSONResponse
from starlette.routing import Route

from ..session_store import Unauthorized
from .browse import CATEGORIES, browse
from .client import ContextError, NostalgiaClient
from .dream_proposal import propose
from .ingress import import_conversation


def context_routes(settings, sessions, bearer, body, kits=None):
    client = NostalgiaClient(settings)

    async def endpoint(request):
        try:
            origin = request.headers.get("origin")
            if origin and origin not in settings.origins:
                return JSONResponse({"error": "origin_denied"}, 403)
            internal = request.url.path == "/internal/context/call"
            data = await body(request, limit=262144) if request.method == "POST" else {}
            if request.url.path == "/internal/agent/context":
                expected = settings.service_token_file.read_text().strip()
                if not hmac.compare_digest(bearer(request).encode(), expected.encode()):
                    raise Unauthorized()
                uid = data.get("user_id")
                if not isinstance(uid, str) or not uid:
                    raise ValueError("Invalid user")
                channel = data.get("channel", "unknown")
                if not isinstance(channel, str):
                    channel = "unknown"
                parts = []
                try:
                    assembled = (
                        await asyncio.to_thread(client.call, uid, "assembly")
                    )["data"]
                    core = assembled.get("stable", {}).get("content", "")
                    index = (
                        assembled.get("dynamic", {}).get("summary", {}).get("content", "")
                    )
                    parts.append(
                        "Overall understanding and essential constraints:\n"
                        + core[:4000]
                        + "\n\nSpecific-domain lookup index (read cards and originals "
                        "with recall):\n"
                        + index[:2500]
                        + "\nDo not infer absent facts. Use recall(action=retrieve) for "
                        "details, then read exact cards."
                    )
                except Exception:
                    parts.append(
                        "Personal context is temporarily unavailable. "
                        "Do not invent prior knowledge."
                    )
                if kits is not None and channel == "ios":
                    try:
                        application = await kits.agent_context(uid)
                        parts.append(
                            "## Applications\n"
                            "- Use `kit_build` when the user asks you to make a small application, "
                            "tracker or collection. Omit fields for a purely presentational page.\n"
                            "- Use the unified `kit_call({kit_id, operation, arguments})` proxy only "
                            "for an operation listed below. Do not request a catalog or operation "
                            "list. Static applications intentionally have no operations.\n"
                            "- Use the exact injected schemas. A failed or uncertain write must not "
                            "be repeated under a new invocation.\n\n"
                            + application["content"][:7000]
                        )
                    except Exception:
                        parts.append(
                            "## Applications\n"
                            "Application services are temporarily unavailable. Do not invent, call "
                            "or claim to have created an application operation."
                        )
                return JSONResponse({"content": "\n\n".join(parts)})
            if request.url.path == "/internal/context/assemble":
                expected = settings.service_token_file.read_text().strip()
                if not hmac.compare_digest(bearer(request).encode(), expected.encode()):
                    raise Unauthorized()
                uid = data.get("user_id")
                if not isinstance(uid, str) or not uid:
                    raise ValueError("Invalid user")
                assembled = (await asyncio.to_thread(client.call, uid, "assembly"))["data"]
                core = assembled.get("stable", {}).get("content", "")
                index = assembled.get("dynamic", {}).get("summary", {}).get("content", "")
                content = "Overall understanding and essential constraints:\n" + core[:8000]
                content += (
                    "\n\nSpecific-domain lookup index (read cards and originals with recall):\n"
                    + index[:6000]
                )
                content += (
                    "\nDo not infer absent facts. Use recall(action=retrieve) for details, "
                    "then read exact cards."
                )
                return JSONResponse({"content": content, "version": assembled.get("view_token")})
            if internal:
                expected = settings.service_token_file.read_text().strip()
                if not hmac.compare_digest(bearer(request).encode(), expected.encode()):
                    raise Unauthorized()
                user_id = data.pop("user_id")
                if not isinstance(user_id, str) or not user_id:
                    raise ValueError("Invalid user")
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
                if set(data) - {"text", "category"} or not isinstance(data.get("text"), str):
                    raise ValueError("Provide text")
                category = data.get("category", "uncategorized")
                if not isinstance(category, str) or category not in CATEGORIES:
                    raise ValueError("Invalid category")
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
                        "context": {
                            "text": text,
                            **({"category": category} if "category" in data else {}),
                        },
                        "source": {
                            "kind": "user",
                            "namespace": "hymio.saved",
                            "external_id": str(uuid.uuid5(uuid.NAMESPACE_URL, key)),
                        },
                    },
                )
                return JSONResponse(result["data"], result["status_code"])
            if path == "/context/corrections":
                if set(data) != {"target", "text"} or not isinstance(data["text"], str):
                    raise ValueError("Provide a target and correction")
                target, text = data["target"], data["text"].strip()
                if (
                    not isinstance(target, dict)
                    or set(target) != {"kind", "id"}
                    or target["kind"] not in {"record", "artifact"}
                    or not isinstance(target["id"], str)
                    or not 1 <= len(text) <= 16000
                ):
                    raise ValueError("Invalid correction")
                await asyncio.to_thread(
                    client.call,
                    user_id,
                    "artifacts.read" if target["kind"] == "artifact" else "records.read",
                    item_id=target["id"],
                )
                key = request_key(request)
                # A correction is immutable user evidence, not an immediate rewrite.
                # Keep the payload stable across uncertain retries: identity is target + quote.
                result = await asyncio.to_thread(
                    client.call,
                    user_id,
                    "records.append",
                    operation_id=key,
                    data={
                        "item_type": "context",
                        "context_type": "correction",
                        "context": {"text": text, "correction_target": target},
                        "source": {
                            "kind": "user",
                            "namespace": "hymio.correction",
                            "external_id": str(uuid.uuid5(uuid.NAMESPACE_URL, key)),
                        },
                    },
                )
                return JSONResponse(
                    {"record": result["data"], "state": "pending"}, result["status_code"]
                )
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
            if path == "/context/browse":
                return JSONResponse(await asyncio.to_thread(browse, client, user_id, data))
            if path == "/context/search":
                return JSONResponse(
                    (await asyncio.to_thread(client.call, user_id, "search", data=data))["data"]
                )
            if path in {"/context/graph", "/context/retrieve"}:
                action = "graph.query" if path.endswith("graph") else "retrieve"
                return JSONResponse(
                    (await asyncio.to_thread(client.call, user_id, action, data=data))["data"]
                )
            raise ValueError("Unknown context route")
        except Unauthorized:
            return JSONResponse({"error": "unauthorized"}, 401)
        except ContextError as exc:
            return JSONResponse(exc.data, exc.status)
        except (ValueError, KeyError, TypeError):
            return JSONResponse({"error": "bad_request"}, 400)
        except Exception:
            return JSONResponse({"error": "context_unavailable"}, 503)

    async def dream_endpoint(request):
        try:
            expected = settings.service_token_file.read_text().strip()
            if not hmac.compare_digest(bearer(request).encode(), expected.encode()):
                raise Unauthorized()
            result = await asyncio.to_thread(propose, settings, await body(request, limit=262144))
            return JSONResponse(result)
        except Unauthorized:
            return JSONResponse({"error": "unauthorized"}, 401)
        except ContextError as exc:
            return JSONResponse(exc.data, exc.status)
        except (ValueError, KeyError, TypeError):
            return JSONResponse({"error": "bad_request"}, 400)
        except Exception:
            return JSONResponse({"error": "dreaming_unavailable"}, 503)

    return [
        Route("/internal/context/call", endpoint, methods=["POST"]),
        Route("/internal/agent/context", endpoint, methods=["POST"]),
        Route("/internal/context/assemble", endpoint, methods=["POST"]),
        Route("/internal/dreaming/propose", dream_endpoint, methods=["POST"]),
        Route("/context/imports/conversation", endpoint, methods=["POST"]),
        Route("/context/assembly", endpoint),
        Route("/context/events", endpoint),
        Route("/context/saves", endpoint, methods=["POST"]),
        Route("/context/corrections", endpoint, methods=["POST"]),
        Route("/context/records/{item_id}", endpoint),
        Route("/context/artifacts/{item_id}", endpoint),
        Route("/context/injection", endpoint),
        Route("/context/records", endpoint, methods=["GET", "POST"]),
        Route("/context/search", endpoint, methods=["POST"]),
        Route("/context/browse", endpoint, methods=["POST"]),
        Route("/context/graph", endpoint, methods=["POST"]),
        Route("/context/retrieve", endpoint, methods=["POST"]),
    ]


def request_key(request):
    key = request.headers.get("idempotency-key", "")
    if not 1 <= len(key) <= 120:
        raise ValueError("Provide Idempotency-Key of 1..120 characters")
    return key
