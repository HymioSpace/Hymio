import hmac
import json

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from .service import KitNotFound, KitNotInstalled


def build_app(service, token):
    async def body(request, limit=131072):
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > limit:
                raise ValueError("Request too large")
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError("Expected object")
        return value

    async def endpoint(request):
        try:
            if request.url.path == "/health":
                return JSONResponse({"alive": True})
            authorization = request.headers.get("authorization", "")
            supplied = authorization[7:] if authorization.startswith("Bearer ") else ""
            if not hmac.compare_digest(supplied.encode(), token.encode()):
                return JSONResponse({"error": "unauthorized"}, 401)
            data = await body(request)
            user_id = data.get("user_id")
            if not isinstance(user_id, str) or not user_id:
                raise ValueError("Invalid user")
            action = request.url.path
            if action == "/v1/catalog":
                return JSONResponse({"kits": service.catalog(user_id)})
            if action == "/v1/install":
                return JSONResponse(service.install(user_id, data.get("kit_id")))
            if action == "/v1/uninstall":
                return JSONResponse(service.uninstall(user_id, data.get("kit_id")))
            if action == "/v1/generate":
                return JSONResponse(service.generate(user_id, data.get("spec")))
            if action == "/v1/app":
                return JSONResponse(service.app(user_id, data.get("kit_id")))
            if action == "/v1/agent-context":
                return JSONResponse(service.agent_context(user_id))
            if action == "/v1/invoke":
                return JSONResponse(
                    service.invoke(
                        user_id,
                        data.get("kit_id"),
                        data.get("operation"),
                        data.get("arguments", {}),
                        data.get("idempotency_key"),
                    )
                )
            return JSONResponse({"error": "not_found"}, 404)
        except KitNotInstalled:
            return JSONResponse({"error": "kit_not_installed"}, 409)
        except KitNotFound:
            return JSONResponse({"error": "kit_not_found"}, 404)
        except (KeyError, TypeError, ValueError) as exc:
            return JSONResponse({"error": "invalid_kit_request", "message": str(exc)}, 400)

    return Starlette(
        routes=[
            Route("/health", endpoint),
            Route("/v1/{operation}", endpoint, methods=["POST"]),
        ]
    )
