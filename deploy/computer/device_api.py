"""Authenticated device API. All execution occurs on this host as its dedicated user."""

import asyncio
import hmac
import json
import os
import subprocess
from pathlib import Path

from device_runtime import handle
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

TOKEN = Path(os.environ["HYMIO_DEVICE_TOKEN_FILE"]).read_text().strip()
if len(TOKEN) < 32:
    raise ValueError("Device token must contain at least 32 characters")


async def endpoint(request: Request):
    expected = ("Bearer " + TOKEN).encode()
    if not hmac.compare_digest(
        request.headers.get("authorization", "").encode(), expected
    ):
        return JSONResponse({"error": "unauthorized"}, 401)
    action = request.path_params["action"]
    if action not in ("status", "execute", "pause", "resume"):
        return JSONResponse({"error": "not_found"}, 404)
    try:
        body = bytearray()
        async for part in request.stream():
            body.extend(part)
            if len(body) > 65536:
                return JSONResponse({"error": "request_too_large"}, 413)
        data = json.loads(body) if body else {}
        if not isinstance(data, dict) or set(data) - {"request", "deadline"}:
            raise ValueError()
        result = await asyncio.to_thread(handle, {**data, "action": action})
        return JSONResponse(result)
    except (ValueError, KeyError, TypeError):
        return JSONResponse({"error": "invalid_request"}, 400)
    except (OSError, subprocess.SubprocessError):
        return JSONResponse({"error": "device_execution_interrupted"}, 503)


app = Starlette(routes=[Route("/v1/{action}", endpoint, methods=["POST"])])
