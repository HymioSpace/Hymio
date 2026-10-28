"""Public CLI transport; execution capability validation is owned by Oath."""

from starlette.responses import JSONResponse, Response
from starlette.routing import Route

ASSETS = {"client", "manifest", "install"}
OPERATIONS = {"tools", "invoke", "status", "detach"}


def cli_routes(settings, upstream):
    async def endpoint(request):
        name = request.path_params["operation"]
        if name not in ASSETS | OPERATIONS:
            return JSONResponse({"error": "not_found"}, 404)
        if request.method == "GET" and name not in ASSETS | {"tools"}:
            return JSONResponse({"error": "method_not_allowed"}, 405)
        if request.method == "POST" and name not in {"invoke", "status", "detach"}:
            return JSONResponse({"error": "method_not_allowed"}, 405)
        content = bytearray()
        async for chunk in request.stream():
            content.extend(chunk)
            if len(content) > 65536:
                return JSONResponse({"error": "request_too_large"}, 413)
        try:
            response = await upstream.request(
                request.method,
                settings.oath_biz.rstrip("/") + "/cli/" + name,
                headers={
                    "Authorization": request.headers.get("authorization", ""),
                    "Content-Type": "application/json",
                },
                content=bytes(content),
                timeout=12,
                follow_redirects=False,
            )
            return Response(
                response.content,
                status_code=response.status_code,
                headers={
                    "Content-Type": response.headers.get("content-type", "application/json"),
                    "Cache-Control": "no-store",
                    "X-Content-Type-Options": "nosniff",
                },
            )
        except Exception:
            return JSONResponse({"error": "cli_unavailable"}, 503)

    return [Route("/agent/cli/{operation}", endpoint, methods=["GET", "POST"])]
