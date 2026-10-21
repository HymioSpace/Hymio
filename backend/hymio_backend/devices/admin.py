"""Administrator-only resource control. Service credentials and user role claims cannot enter."""

import asyncio

from starlette.responses import JSONResponse
from starlette.routing import Route

from ..session_store import Unauthorized
from .resources import ResourceCapacity, ResourceDenied
from .service import DeviceService
from .store import DeviceConflict


def admin_routes(settings, sessions, bearer, body):
    service = DeviceService(settings, sessions)

    async def endpoint(request):
        try:
            origin = request.headers.get("origin")
            if origin and origin not in settings.origins:
                return JSONResponse({"error": "origin_denied"}, 403)
            identity = await asyncio.to_thread(sessions.verify, bearer(request))
            actor = identity["user_id"]
            admin = actor in getattr(settings, "admin_user_ids", ())
            if request.url.path == "/admin/api/me":
                return JSONResponse({"is_admin": admin})
            if not admin:
                return JSONResponse({"error": "administrator_required"}, 403)
            if request.method == "GET":
                query = request.query_params.get("q", "")[:160]
                offset = max(0, int(request.query_params.get("offset", 0)))
                result = await asyncio.to_thread(service.resources.overview, query, offset)
                for provider in result["providers"]:
                    provider["configured"] = provider["provider"] in service.providers
                return JSONResponse(result)
            data = await body(request)
            if request.url.path.endswith("/grants"):
                if data["enabled"] and data["provider"] not in service.providers:
                    raise ValueError("provider_not_configured")
                await asyncio.to_thread(
                    service.resources.grant,
                    actor,
                    data["user_id"],
                    data["provider"],
                    data["enabled"],
                    data.get("kind", "cloud_desktop"),
                )
                return JSONResponse({"updated": True})
            device_id = request.path_params["device_id"]
            with sessions.transaction() as db:
                row = db.execute("SELECT * FROM devices WHERE id=?", (device_id,)).fetchone()
                if not row:
                    raise KeyError()
                device = dict(row)
            action = data.get("action")
            if action == "release":
                if data.get("confirm") != device_id:
                    raise ValueError("release_confirmation_required")
                service.resources.audit(actor, device_id, "release_requested")
                result = await asyncio.to_thread(service.revoke, device["user_id"], device_id)
                service.resources.audit(
                    actor,
                    device_id,
                    "release_confirmed"
                    if result.get("stopped") is not False
                    else "release_unknown",
                )
                return JSONResponse(result)
            if action == "reconcile":
                record = service.store.provision_record(device["user_id"], device_id)
                if (
                    device["provider_ref"]
                    or not record
                    or record["status"] not in ("running", "outcome_unknown")
                ):
                    raise ValueError("not_an_uncertain_create")
                result = await asyncio.to_thread(service.provision, device["user_id"])
                service.resources.audit(actor, device_id, "reconcile")
                return JSONResponse(result)
            if action in ("pause", "resume"):
                result = await asyncio.to_thread(
                    service.control, device["user_id"], device_id, action, administrator=True
                )
                service.resources.audit(actor, device_id, action)
                return JSONResponse(result)
            raise ValueError("invalid_action")
        except Unauthorized:
            return JSONResponse({"error": "unauthorized"}, 401)
        except ResourceDenied:
            return JSONResponse({"error": "resource_access_denied"}, 403)
        except ResourceCapacity as error:
            return JSONResponse({"error": str(error)}, 409)
        except DeviceConflict:
            return JSONResponse({"error": "resource_busy_or_capacity_exhausted"}, 409)
        except KeyError:
            return JSONResponse({"error": "not_found"}, 404)
        except (TypeError, ValueError):
            return JSONResponse({"error": "invalid_admin_request"}, 400)
        except Exception:
            return JSONResponse({"error": "resource_provider_unavailable"}, 503)

    return [
        Route("/admin/api/me", endpoint),
        Route("/admin/api/resources", endpoint),
        Route("/admin/api/resources/grants", endpoint, methods=["POST"]),
        Route("/admin/api/resources/devices/{device_id}", endpoint, methods=["POST"]),
    ]
