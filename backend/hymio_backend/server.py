import asyncio
import hmac
import json
import re
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

import httpx
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route, WebSocketRoute

from .agent_gateway import relay_agent
from .devices.service import DeviceService
from .browser_callback import browser_callback
from .casdoor_accounts import AccountRejected, CasdoorAccounts
from .devices.routes import device_routes
from .oidc import Oidc
from .session_store import SessionStore, Unauthorized


def bearer(request):
    header = request.headers.get("authorization", "")
    return header[7:] if header.startswith("Bearer ") else ""


async def body(request):
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 16384:
            raise ValueError("Request too large")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("Expected object")
    return value


def text(data, key):
    value = data.get(key)
    if not isinstance(value, str) or not 1 <= len(value) <= 8192:
        raise ValueError("Invalid field")
    return value


def build_app(settings, *, provider=None):
    store = SessionStore(settings)
    oidc = provider or Oidc(settings)
    accounts = CasdoorAccounts(settings, oidc)
    upstream = httpx.AsyncClient(timeout=10, follow_redirects=False, trust_env=False)

    @asynccontextmanager
    async def lifespan(app):
        yield
        await upstream.aclose()
        if hasattr(oidc, "http"):
            oidc.http.close()

    async def endpoint(request):
        try:
            origin = request.headers.get("origin")
            if origin and origin not in settings.origins:
                return JSONResponse({"error": "origin_denied"}, 403)
            path = request.url.path
            if path == "/health":
                return JSONResponse({"alive": True})
            if path == "/auth/options":
                return JSONResponse(
                    {
                        "login_method": settings.login_method,
                        "signup_enabled": settings.signup_enabled,
                        "invitation_required": settings.invitation_codes_file is not None,
                    }
                )
            if path == "/auth/account":
                if settings.login_method != "account":
                    return JSONResponse({"error": "account_login_disabled"}, 403)
                data = await body(request)
                action = text(data, "action")
                if action == "signup" and not settings.signup_enabled:
                    return JSONResponse({"error": "registration_closed"}, 403)
                if action == "signup" and settings.invitation_codes_file:
                    invitation = data.get("invitation_code", "")
                    if not isinstance(invitation, str) or len(invitation) > 256:
                        return JSONResponse({"error": "invalid_invitation"}, 403)
                    try:
                        codes = await asyncio.to_thread(settings.invitation_codes_file.read_text)
                    except (OSError, UnicodeError):
                        return JSONResponse({"error": "registration_unavailable"}, 503)
                    valid = [code.strip() for code in codes.splitlines() if code.strip()]
                    if not any(
                        hmac.compare_digest(invitation.strip().encode(), code.encode())
                        for code in valid
                    ):
                        return JSONResponse({"error": "invalid_invitation"}, 403)
                username, password = text(data, "username"), text(data, "password")
                if action not in ("login", "signup") or not re.fullmatch(
                    r"[A-Za-z0-9_-]{3,32}", username
                ):
                    raise ValueError("Invalid account")
                if not (8 if action == "signup" else 1) <= len(password) <= 128:
                    raise ValueError("Invalid password length")
                claims = await asyncio.to_thread(accounts.authenticate, action, username, password)
                return JSONResponse(await asyncio.to_thread(store.create_session, claims))
            if path == "/auth/start":
                data = await body(request)
                return_uri = text(data, "return_uri")
                uri = urlsplit(return_uri)
                loopback = (
                    uri.scheme == "http"
                    and uri.hostname == "127.0.0.1"
                    and uri.port
                    and uri.path == "/hymio-callback"
                    and not uri.query
                    and not uri.fragment
                    and uri.username is None
                    and uri.password is None
                )
                if return_uri not in settings.origins and not loopback:
                    raise ValueError("Invalid return URI")
                handle, state, verifier, nonce = await asyncio.to_thread(store.start, return_uri)
                url = await asyncio.to_thread(oidc.authorize_url, state, verifier, nonce)
                return JSONResponse(
                    {"flow_id": handle, "authorization_url": url, "expires_in": 300}
                )
            if path == "/auth/callback":
                state = request.query_params.get("state", "")
                flow = await asyncio.to_thread(store.claim_callback, state)
                try:
                    if request.query_params.get("error"):
                        raise Unauthorized()
                    claims = await asyncio.to_thread(
                        oidc.exchange, request.query_params.get("code", ""), flow
                    )
                    grant, return_uri = await asyncio.to_thread(store.finish, state, claims)
                except Exception:
                    await asyncio.to_thread(store.finish, state)
                    return browser_callback(flow["return_uri"], error="login_failed")
                return browser_callback(return_uri, grant=grant)
            if path == "/auth/exchange":
                data = await body(request)
                result = await asyncio.to_thread(
                    store.exchange, text(data, "flow_id"), text(data, "login_code")
                )
                return JSONResponse(result)
            if path == "/auth/refresh":
                result = await asyncio.to_thread(
                    store.refresh, text(await body(request), "refresh_token")
                )
                return JSONResponse(result)
            if path == "/auth/logout":
                await asyncio.to_thread(store.logout, bearer(request))
                return JSONResponse({"logged_out": True})
            if path == "/internal/auth/verify":
                expected = settings.service_token_file.read_text().strip()
                if not hmac.compare_digest(bearer(request).encode(), expected.encode()):
                    raise Unauthorized()
                return JSONResponse(
                    await asyncio.to_thread(store.verify, text(await body(request), "credential"))
                )
            identity = await asyncio.to_thread(store.verify, bearer(request))
            if path == "/auth/me":
                return JSONResponse(identity)
            if path.startswith("/oath-biz/"):
                target = path.removeprefix("/oath-biz")
                params = dict(request.query_params)
            else:
                target = "/list_traces" if path == "/agent/traces" else "/query_trace"
                params = (
                    {"limit": "30"}
                    if target == "/list_traces"
                    else {"trace_id": request.path_params["trace_id"]}
                )
            response = await upstream.get(
                settings.oath_biz.rstrip("/") + target,
                params=params,
                headers={"Authorization": "Bearer " + bearer(request)},
            )
            return JSONResponse(response.json(), response.status_code)
        except AccountRejected:
            return JSONResponse({"error": "account_rejected"}, 401)
        except Unauthorized:
            return JSONResponse({"error": "unauthorized"}, 401)
        except (ValueError, KeyError):
            return JSONResponse({"error": "bad_request"}, 400)
        except Exception:
            return JSONResponse({"error": "service_unavailable"}, 503)

    channel_devices = DeviceService(settings, store)

    async def agent_socket(websocket):
        await relay_agent(websocket, settings, store, channel_devices)

    routes = device_routes(settings, store, bearer, body) + [
        WebSocketRoute("/agent/ws", agent_socket),
        Route("/health", endpoint),
        Route("/auth/options", endpoint),
        Route("/auth/callback", endpoint),
        Route("/auth/me", endpoint),
        Route("/agent/traces", endpoint),
        Route("/agent/traces/{trace_id}", endpoint),
    ]
    routes += [
        Route("/oath-biz" + path, endpoint)
        for path in ("/heartbeat", "/list_traces", "/query_trace", "/conversation_history")
    ]
    routes += [
        Route(path, endpoint, methods=["POST"])
        for path in (
            "/auth/start",
            "/auth/account",
            "/auth/exchange",
            "/auth/refresh",
            "/auth/logout",
            "/internal/auth/verify",
        )
    ]
    app = Starlette(routes=routes, lifespan=lifespan)

    async def private_response(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    app.add_middleware(BaseHTTPMiddleware, dispatch=private_response)
    return CORSMiddleware(
        app,
        allow_origins=list(settings.origins),
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type", "X-Oath-User-Id"],
    )
