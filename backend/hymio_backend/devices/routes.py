import asyncio
import hmac
import logging

from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from ..session_store import Unauthorized
from .resources import ResourceCapacity, ResourceDenied
from .service import DeviceService
from .store import DeviceConflict

_log = logging.getLogger(__name__)


def device_routes(settings, sessions, bearer, body):
    service = DeviceService(settings, sessions)
    store = service.store
    preparing = {}

    async def ensure(user_id, *, wake=False):
        task = preparing.get(user_id)
        if task is None or task.done():
            task = asyncio.create_task(
                asyncio.to_thread(service.ensure_available, user_id, wake=wake)
            )
            preparing[user_id] = task

            def finished(done):
                if preparing.get(user_id) is done:
                    preparing.pop(user_id, None)
                if not done.cancelled():
                    error = done.exception()
                    if error:
                        _log.warning("Computer preparation interrupted: %s", type(error).__name__)

            task.add_done_callback(finished)
        try:
            return await asyncio.wait_for(asyncio.shield(task), timeout=3)
        except TimeoutError:
            return {
                "action": "preparing",
                "notice": "Preparation continues in Backend. Do not poll or run repair commands.",
            }

    async def endpoint(request):
        try:
            origin = request.headers.get("origin")
            if origin and origin not in settings.origins:
                return JSONResponse({"error": "origin_denied"}, 403)
            internal = request.url.path.startswith("/internal/devices")
            data = await body(request) if request.method == "POST" else {}
            if internal:
                expected = settings.service_token_file.read_text().strip()
                if not hmac.compare_digest(bearer(request).encode(), expected.encode()):
                    raise Unauthorized()
                user_id = data["user_id"]
                if not isinstance(user_id, str) or not user_id:
                    raise ValueError("invalid_user")
            else:
                identity = await asyncio.to_thread(sessions.verify, bearer(request))
                user_id = identity["user_id"]
            path = request.url.path
            binding = None
            if path.endswith("/ensure"):
                return JSONResponse(await ensure(user_id))
            if internal and path.endswith("/list"):
                try:
                    binding = await ensure(user_id, wake=True)
                except DeviceConflict:
                    binding = {
                        "action": "blocked",
                        "notice": "Computer requires recovery; do not repeat commands.",
                    }
            if "/commands" in path or path.endswith("/command"):
                device_id = data["device_id"] if internal else request.path_params["device_id"]
                invocation_id = (
                    data.get("invocation_id")
                    if internal
                    else request.path_params.get("invocation_id")
                )
                try:
                    result = await asyncio.to_thread(
                        store.commands,
                        user_id,
                        device_id,
                        invocation_id,
                        int(request.query_params.get("limit", 20)),
                    )
                except KeyError as error:
                    if error.args and error.args[0] == "command_not_found":
                        return JSONResponse(
                            {
                                "error": "not_a_device_invocation",
                                "notice": (
                                    "This invocation is not a device command. Only bash, browser "
                                    "and computer executions can be queried here."
                                ),
                            },
                            404,
                        )
                    raise
                return JSONResponse(result if invocation_id else {"commands": result})
            if path.endswith(("/pause", "/resume")):
                result = await asyncio.to_thread(
                    service.control,
                    user_id,
                    request.path_params["device_id"],
                    path.rsplit("/", 1)[1],
                )
                return JSONResponse(result)
            if path.endswith("/register"):
                bound = await asyncio.to_thread(
                    store.bind, user_id, data["installation_id"], data["kind"]
                )
                return JSONResponse(service.describe(bound))
            if path.endswith("/heartbeat"):
                await asyncio.to_thread(store.heartbeat, user_id, request.path_params["device_id"])
                return JSONResponse({"alive": True})
            if path.endswith("/execute"):
                if not internal:
                    data["invocation_id"] = data.get("invocation_id", "")
                return JSONResponse(await asyncio.to_thread(service.execute, user_id, data))
            if path.endswith("/provision"):
                return JSONResponse(await asyncio.to_thread(service.provision, user_id))
            if "/media/" in path:
                image = await asyncio.to_thread(
                    store.read_media, user_id, request.path_params["media_id"]
                )
                return Response(image, media_type="image/png")
            if path.endswith("/revoke"):
                result = await asyncio.to_thread(
                    service.revoke, user_id, request.path_params["device_id"]
                )
                return JSONResponse(result)
            provider = await asyncio.to_thread(service.resources.provider, user_id)
            devices = [
                device
                for device in await asyncio.to_thread(store.list, user_id)
                if device["kind"] != "cloud_desktop" or device["provider"] == provider
            ]
            described = await asyncio.gather(
                *[asyncio.to_thread(service.describe, device) for device in devices]
            )
            return JSONResponse(
                {
                    "devices": described,
                    "binding": binding,
                    "guidance": (
                        "Use an online device with the required capability. "
                        "Web, iOS and Mac bindings currently provide conversation only; "
                        "binding them does not enable native control."
                        if any(device["capabilities"] for device in described)
                        else "Cloud computer may be preparing. Report binding state and wait. "
                        "Web, iOS and Mac are conversation channels, not execution targets."
                    ),
                }
            )
        except Unauthorized:
            return JSONResponse({"error": "unauthorized"}, 401)
        except ResourceDenied:
            return JSONResponse({"error": "resource_access_denied"}, 403)
        except ResourceCapacity as error:
            return JSONResponse({"error": str(error)}, 409)
        except DeviceConflict as error:
            return JSONResponse({"error": str(error)}, 409)
        except KeyError:
            return JSONResponse({"error": "not_found"}, 404)
        except (ValueError, TypeError):
            return JSONResponse({"error": "bad_request"}, 400)
        except Exception:
            return JSONResponse({"error": "device_service_unavailable"}, 503)

    return [
        Route("/devices", endpoint),
        Route("/devices/provision", endpoint, methods=["POST"]),
        Route("/devices/ensure", endpoint, methods=["POST"]),
        Route("/devices/register", endpoint, methods=["POST"]),
        Route("/devices/{device_id}/heartbeat", endpoint, methods=["POST"]),
        Route("/devices/{device_id}/pause", endpoint, methods=["POST"]),
        Route("/devices/{device_id}/resume", endpoint, methods=["POST"]),
        Route("/devices/{device_id}/commands", endpoint),
        Route("/devices/{device_id}/commands/{invocation_id}", endpoint),
        Route("/devices/execute", endpoint, methods=["POST"]),
        Route("/devices/{device_id}/revoke", endpoint, methods=["POST"]),
        Route("/devices/media/{media_id}", endpoint),
        Route("/internal/devices/list", endpoint, methods=["POST"]),
        Route("/internal/devices/execute", endpoint, methods=["POST"]),
        Route("/internal/devices/command", endpoint, methods=["POST"]),
    ]
