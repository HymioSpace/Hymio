import asyncio
import hmac
import uuid

from starlette.responses import JSONResponse
from starlette.routing import Route

from ..session_store import Unauthorized
from .service import KitHostUnavailable, KitNotFound, KitNotInstalled


def kit_routes(settings, sessions, service, bearer, body):
    async def endpoint(request):
        try:
            origin = request.headers.get("origin")
            if origin and origin not in settings.origins:
                return JSONResponse({"error": "origin_denied"}, 403)
            path = request.url.path
            if path == "/internal/kits":
                expected = settings.service_token_file.read_bytes().strip()
                if not hmac.compare_digest(bearer(request).encode(), expected):
                    raise Unauthorized()
                data = await body(request, limit=65536)
                user_id = data.get("user_id")
                if not isinstance(user_id, str) or not user_id:
                    raise ValueError("Invalid user")
                operation_id = data.get("invocation_id")
                if not isinstance(operation_id, str) or not operation_id:
                    raise ValueError("Invocation id is required")
                result = await service.invoke(
                    user_id,
                    data.get("kit_id"),
                    data.get("operation"),
                    data.get("arguments", {}),
                    operation_id,
                )
                return JSONResponse(result["result"])
            if path == "/internal/kits/generate":
                expected = settings.service_token_file.read_bytes().strip()
                if not hmac.compare_digest(bearer(request).encode(), expected):
                    raise Unauthorized()
                data = await body(request, limit=600000)
                user_id = data.get("user_id")
                if not isinstance(user_id, str) or not user_id:
                    raise ValueError("Invalid user")
                return JSONResponse(await service.generate(user_id, data.get("spec")))

            identity = await asyncio.to_thread(sessions.verify, bearer(request))
            user_id = identity["user_id"]
            if path == "/kits" and request.method == "GET":
                return JSONResponse({"kits": await service.catalog(user_id)})
            if path.startswith("/kits/"):
                parts = path.strip("/").split("/")
                if len(parts) == 3 and parts[2] in {"install", "uninstall"}:
                    if request.method != "POST":
                        return JSONResponse({"error": "method_not_allowed"}, 405)
                    if parts[2] == "install":
                        return JSONResponse(await service.install(user_id, parts[1]))
                    return JSONResponse(await service.uninstall(user_id, parts[1]))
                if len(parts) == 3 and parts[2] == "app" and request.method == "GET":
                    return JSONResponse(await service.app(user_id, parts[1]))
                if (
                    len(parts) == 4
                    and parts[2] == "actions"
                    and request.method == "POST"
                ):
                    data = await body(request, limit=131072)
                    key = request.headers.get("idempotency-key") or uuid.uuid4().hex
                    return JSONResponse(
                        await service.invoke(
                            user_id,
                            parts[1],
                            parts[3],
                            data,
                            key,
                        )
                    )
            return JSONResponse({"error": "not_found"}, 404)
        except Unauthorized:
            return JSONResponse({"error": "unauthorized"}, 401)
        except KitNotInstalled:
            return JSONResponse({"error": "kit_not_installed"}, 409)
        except KitNotFound:
            return JSONResponse({"error": "kit_not_found"}, 404)
        except KitHostUnavailable:
            return JSONResponse({"error": "kit_host_unavailable"}, 503)
        except (KeyError, TypeError, ValueError) as exc:
            return JSONResponse({"error": "invalid_kit_request", "message": str(exc)}, 400)

    return [
        Route("/kits", endpoint, methods=["GET"]),
        Route("/kits/{kit_id}/app", endpoint, methods=["GET"]),
        Route("/kits/{kit_id}/install", endpoint, methods=["POST"]),
        Route("/kits/{kit_id}/uninstall", endpoint, methods=["POST"]),
        Route("/kits/{kit_id}/actions/{operation}", endpoint, methods=["POST"]),
        Route("/internal/kits", endpoint, methods=["POST"]),
        Route("/internal/kits/generate", endpoint, methods=["POST"]),
    ]
