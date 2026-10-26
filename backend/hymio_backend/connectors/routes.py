import asyncio
import hmac

from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route

from ..session_store import Unauthorized
from .catalog import PROVIDERS, ConnectorError


def connector_routes(settings, sessions, service, bearer, body):
    async def endpoint(request):
        try:
            provider = request.path_params.get("provider")
            if provider:
                try:
                    await service.callback(
                        provider,
                        request.query_params.get("state", ""),
                        request.query_params.get("code"),
                        bool(request.query_params.get("error")),
                    )
                    message = "连接已建立。你可以关闭此页，回到 Hymio 查看同步进展。"
                    status = 200
                except ConnectorError:
                    message = "连接未完成或授权已过期。请回到 Hymio 重试。"
                    status = 400
                return HTMLResponse(
                    "<!doctype html><html lang='zh'><meta charset='utf-8'><meta n"
                    "ame='viewport' content='width=device-width'><title>Hymio · 连"
                    "接</title><body style='font-family:system-ui;background:#f6f7"
                    "fb;color:#20273b;display:grid;place-content:center;min-heigh"
                    "t:90vh;margin:24px'><main><h1>Hymio</h1><p>"
                    + message
                    + "</p></main></body></html>",
                    status_code=status,
                    headers={
                        "Content-Security-Policy": (
                            "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'"
                        ),
                        "Referrer-Policy": "no-referrer",
                    },
                )
            origin = request.headers.get("origin")
            if origin and origin not in settings.origins:
                return JSONResponse({"error": "origin_denied"}, 403)
            data = await body(request, limit=512 * 1024) if request.method == "POST" else {}
            if request.url.path == "/internal/connectors/call":
                expected = settings.service_token_file.read_text().strip()
                if not hmac.compare_digest(bearer(request).encode(), expected.encode()):
                    raise Unauthorized()
                uid = data.get("user_id")
                if not isinstance(uid, str) or not uid:
                    raise ValueError()
                if data.get("action", "list") == "list":
                    return JSONResponse(
                        {"connections": await asyncio.to_thread(service.store.list, uid)}
                    )
                if data.get("action") != "read":
                    raise ConnectorError("read_only_connector_tool")
                return JSONResponse(
                    {
                        "items": await asyncio.to_thread(
                            service.read,
                            uid,
                            data.get("connection_id"),
                            data.get("query", ""),
                            data.get("limit", 20),
                        )
                    }
                )
            uid = (await asyncio.to_thread(sessions.verify, bearer(request)))["user_id"]
            cid = request.path_params.get("cid")
            if request.method == "GET":
                return JSONResponse(
                    {
                        "providers": service.catalog(),
                        "connections": await asyncio.to_thread(service.store.list, uid),
                    }
                )
            if not cid:
                p = data.get("provider")
                if p not in PROVIDERS:
                    raise ConnectorError("unknown_provider")
                if data.get("consent") is not True:
                    raise ConnectorError("upload_consent_required")
                if PROVIDERS[p]["transport"] == "oauth" and not service.registration(p):
                    raise ConnectorError("provider_not_configured", 503)
                if PROVIDERS[p]["transport"] == "device" and (
                    not data.get("device_id") or data.get("platform") != "ios"
                ):
                    raise ConnectorError("use_ios_permissions")
                value = await asyncio.to_thread(
                    service.store.create, uid, p, data.get("device_id", ""), data.get("name", "")
                )
            elif request.url.path.endswith("/authorize"):
                value = await asyncio.to_thread(service.authorize, uid, cid)
            elif request.url.path.endswith("/ingest"):
                value = await asyncio.to_thread(service.ingest, uid, cid, data)
            elif data.get("action") == "disconnect":
                value = await service.disconnect(uid, cid)
            else:
                value = await asyncio.to_thread(service.store.action, uid, cid, data.get("action"))
            return JSONResponse(value)
        except Unauthorized:
            return JSONResponse({"error": "unauthorized"}, 401)
        except ConnectorError as exc:
            return JSONResponse({"error": exc.code}, exc.status)
        except (ValueError, TypeError, KeyError):
            return JSONResponse({"error": "invalid_connector_request"}, 400)

    return [
        Route("/connectors", endpoint, methods=["GET", "POST"]),
        Route("/connectors/{cid}", endpoint, methods=["POST"]),
        Route("/connectors/{cid}/authorize", endpoint, methods=["POST"]),
        Route("/connectors/{cid}/ingest", endpoint, methods=["POST"]),
        Route("/connectors/oauth/{provider}/callback", endpoint),
        Route("/internal/connectors/call", endpoint, methods=["POST"]),
    ]
