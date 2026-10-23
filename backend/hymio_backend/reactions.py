import hmac

import httpx
from starlette.responses import JSONResponse
from starlette.routing import Route

from .session_store import Unauthorized
from .tasks.credentials import issue


def reaction_routes(settings, bearer, body):
    async def endpoint(request):
        try:
            origin = request.headers.get("origin")
            if origin and origin not in settings.origins:
                return JSONResponse({"error": "origin_denied"}, 403)
            data = await body(request, limit=4096)
            if not hmac.compare_digest(
                bearer(request).encode(), settings.service_token_file.read_bytes().strip()
            ):
                raise Unauthorized()
            uid = data["user_id"]
            if not isinstance(uid, str) or not uid:
                raise ValueError("Invalid user")
            async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
                response = await client.post(
                    settings.oath_biz.rstrip("/") + "/messages/react",
                    headers={
                        "Authorization": "Bearer " + issue(settings, uid),
                        "X-Oath-User-Id": uid,
                    },
                    json={
                        "actor": "assistant",
                        "target": data["target"],
                        "emoji": data.get("emoji"),
                        "operation_id": data["operation_id"],
                    },
                )
            return JSONResponse(response.json(), response.status_code)
        except Unauthorized:
            return JSONResponse({"error": "unauthorized"}, 401)
        except (ValueError, KeyError, TypeError):
            return JSONResponse({"error": "invalid_reaction"}, 400)
        except httpx.HTTPError:
            return JSONResponse({"error": "agent_unavailable"}, 503)

    return [Route("/internal/reactions", endpoint, methods=["POST"])]
