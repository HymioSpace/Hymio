"""Device lifecycle and execution, independent of HTTP transport."""

import base64
import time
import uuid

from .api_provider import APIComputer, targets_from_config
from .daytona_provider import DaytonaComputer
from .providers import (
    DeviceProfile,
    DispatchRejected,
    E2BComputer,
    ProviderUnavailable,
    ProvisionRejected,
    provider_failure,
)
from .resources import ResourceDenied
from .store import DeviceConflict, DeviceStore
from .validation import validate


class DeviceService:
    def __init__(self, settings, sessions, link=None):
        self.settings = settings
        self.store = DeviceStore(sessions)
        self.link = link
        self.resources = self.store.resources
        self.providers = {}
        import os

        key_file = getattr(settings, "daytona_key_file", None)
        if (key_file and key_file.is_file() and key_file.read_text().strip()) or os.environ.get(
            "DAYTONA_API_KEY"
        ):
            self.providers["daytona"] = DaytonaComputer(
                getattr(settings, "daytona_key_file", None),
                getattr(settings, "daytona_api_url", "https://app.daytona.io/api"),
                getattr(settings, "daytona_snapshot", ""),
            )
        targets = targets_from_config(getattr(settings, "device_api_targets", ()))
        if targets:
            self.providers["device_api"] = APIComputer(targets)
        import importlib.util

        if (
            settings.e2b_key_file
            and settings.e2b_key_file.is_file()
            and importlib.util.find_spec("e2b_desktop")
        ):
            self.providers["e2b"] = E2BComputer(settings.e2b_key_file, settings.e2b_template)

    def provider(self, device):
        if device["provider"] not in self.providers:
            raise ProviderUnavailable("provider_not_configured")
        return self.providers[device["provider"]]

    def physical(self, device):
        provider = self.provider(device)
        if hasattr(provider, "probe"):
            result = provider.probe(device)
            if result.get("error"):
                raise ProviderUnavailable(result["error"])
            return result["state"]
        return provider.state(device)

    def describe(self, device):
        if device["provider"] == "link" and self.link:
            return self.link.describe(device)
        channel = device["provider"] == "channel"
        configured = self.providers.get(device["provider"])
        profile = (
            getattr(configured, "profile", DeviceProfile())
            if configured is not None
            else DeviceProfile(capabilities=())
        )
        provider_error = None
        try:
            physical = (
                ("online" if device["last_seen"] > time.time() - 75 else "offline")
                if channel
                else (self.physical(device) if device["provider_ref"] else "offline")
            )
        except ProviderUnavailable as error:
            physical, provider_error = "offline", error.code
        state = (
            "missing"
            if physical == "missing"
            else device["control_state"]
            if device["control_state"] != "active"
            else physical
        )
        if not channel and not device["provider_ref"]:
            record = self.store.provision_record(device["user_id"], device["id"])
            state = (
                "preparing"
                if record is None or record["status"] == "running"
                else "recovery_required"
            )
        return {
            "device_id": device["id"],
            "name": "E2B 云电脑" if device["provider"] == "e2b" else device["name"],
            "kind": device["kind"],
            "provider": device["provider"],
            "generation": device["generation"],
            "state": state,
            "provider_state": physical,
            "provider_error": provider_error,
            "online": state == "online",
            "capabilities": []
            if channel or self.resources.provider(device["user_id"]) != device["provider"]
            else list(profile.capabilities),
            "workspace": None if channel else profile.workspace,
            "resolution": {"width": profile.resolution[0], "height": profile.resolution[1]},
            "preserves_files_on_revoke": profile.preserves_files_on_revoke,
            "replaces_device_id": device.get("replaces_device_id"),
        }

    def provision(self, user_id):
        provider_name = self.resources.provider(user_id)
        if provider_name is None:
            raise ResourceDenied("resource_access_denied")
        self.provider({"provider": provider_name})
        device = self.store.create(user_id, provider_name)
        if not device["provider_ref"]:
            prior = self.store.provision_record(user_id, device["id"])
            if prior and prior["status"] in {"running", "outcome_unknown"}:
                lock = self.store.expired_execution(user_id, device["id"])
                provider = self.provider(device)
                reference = (
                    provider.recover(device) if lock and hasattr(provider, "recover") else None
                )
                if not reference:
                    raise DeviceConflict("provision_outcome_unknown")
                self.store.set_ref(user_id, device["id"], reference)
                self.resources.mark(device["id"], "allocated")
                self.store.release_expired_execution(user_id, device["id"], lock)
                return self.describe(self.store.get(user_id, device["id"]))
            invocation = "provision:" + device["id"] + ":" + uuid.uuid4().hex
            _, result = self.store.claim(
                user_id, device["id"], invocation, {"provision": device["provider"]}, 120
            )
            if result is None:
                try:
                    reference = self.provider(device).provision(device)
                    try:
                        self.store.set_ref(user_id, device["id"], reference)
                    except Exception:
                        self.provider(device).stop({**device, "provider_ref": reference})
                        raise
                    self.store.finish(user_id, invocation, {"status": "succeeded"})
                    self.resources.mark(device["id"], "allocated")
                except ProvisionRejected as error:
                    self.resources.mark(device["id"], "released")
                    self.store.finish(
                        user_id,
                        invocation,
                        {"status": "failed", "error": error.code, "dispatched": False},
                    )
                    raise
                except Exception:
                    self.resources.mark(device["id"], "outcome_unknown")
                    self.store.finish(
                        user_id, invocation, {"status": "outcome_unknown"}, release=False
                    )
                    raise
        return self.describe(self.store.get(user_id, device["id"]))

    def _settle_expired_execution(self, user_id, device, physical):
        lock = self.store.expired_execution(user_id, device["id"])
        if lock is None:
            return False
        if physical == "online":
            if not self.provider(device).execution_idle(device):
                raise DeviceConflict("device_execution_still_running")
        elif physical not in ("paused", "missing"):
            raise DeviceConflict("device_state_unknown")
        if not self.store.release_expired_execution(user_id, device["id"], lock):
            raise DeviceConflict("device_lock_changed")
        return True

    def ensure_available(self, user_id, *, wake=False):
        provider_name = self.resources.provider(user_id)
        if provider_name is None:
            return {
                "action": "unavailable",
                "error": "resource_access_denied",
                "notice": "Cloud devices are available only after administrator approval.",
            }
        preferred = self.providers.get(provider_name)
        if (
            preferred is not None
            and hasattr(preferred, "assigned")
            and not preferred.assigned(user_id)
        ):
            return {
                "action": "unavailable",
                "error": "device_not_assigned",
                "notice": "No cloud computer has been assigned to this account.",
            }
        recovery = self.store.recovery(user_id)
        if recovery and recovery["retry_at"] > time.time():
            return {
                "action": "unavailable",
                "error": recovery["error"],
                "retry_after_seconds": max(1, round(recovery["retry_at"] - time.time())),
                "notice": "Recovery is backing off. Keep the binding; do not repeat repairs.",
            }
        owner = self.store.begin_ensure(user_id)
        if owner is None:
            return {
                "action": "preparing",
                "notice": "Cloud computer preparation is already in progress.",
            }
        try:
            device = next(
                (
                    d
                    for d in self.store.list(user_id)
                    if d["kind"] == "cloud_desktop" and d["provider"] == provider_name
                ),
                None,
            )
            action = "created" if device is None else "reused"
            if device and device["provider_ref"]:
                physical = self.physical(device)
                if self.store.reconcile_control(user_id, device["id"], physical):
                    device = self.store.get(user_id, device["id"])
                try:
                    self._settle_expired_execution(user_id, device, physical)
                except DeviceConflict:
                    return {
                        "action": "recovery_required",
                        "device": self.describe(device),
                        "notice": (
                            "Prior execution is still being verified. "
                            "The computer and files were preserved."
                        ),
                    }
                if physical == "missing":
                    profile = getattr(self.provider(device), "profile", DeviceProfile())
                    if not profile.replace_missing:
                        return {
                            "action": "recovery_required",
                            "device": self.describe(device),
                            "notice": "Original device is missing; automatic replacement disabled.",
                        }
                    device = self.store.replace_missing(user_id, device["id"])
                    action = "replaced"
                elif physical == "offline":
                    return {
                        "action": "unavailable",
                        "device": self.describe(device),
                        "notice": "Provider unavailable; existing environment was not replaced.",
                    }
                elif physical in ("online", "paused"):
                    if physical == "online" and device["control_state"] == "active":
                        self.store.recovery(user_id, clear=True)
                        return {"action": "reused", "device": self.describe(device)}
                    if physical == "online" and device["control_state"] != "active":
                        return {"action": "recovery_required", "device": self.describe(device)}
                    # Paused environments retain the same binding and filesystem.

                    if device["control_state"] == "paused" and not wake:
                        self.store.recovery(user_id, clear=True)
                        return {"action": "paused", "device": self.describe(device)}
                    result = self.control(user_id, device["id"], "resume")
                    self.store.recovery(user_id, clear=True)
                    return {"action": "resumed", "device": result}
                elif device["control_state"] != "active":
                    return {"action": "recovery_required", "device": self.describe(device)}
            try:
                result = self.provision(user_id)
            except DeviceConflict:
                return {
                    "action": "recovery_required",
                    "notice": "Prior operation running or outcome unknown. Do not repeat commands.",
                }
            if result["online"]:
                self.store.recovery(user_id, clear=True)
            return {
                "action": action if result["online"] else result["state"],
                "device": result,
                "notice": "Deleted sandbox replaced by empty computer. Old files were not restored."
                if result.get("replaces_device_id")
                else "",
            }
        except ProviderUnavailable as error:
            retry = self.store.recovery(user_id, error=error.code)
            return {
                "action": "unavailable",
                "error": error.code,
                "retry_after_seconds": max(1, round(retry["retry_at"] - time.time())),
                "notice": "Provider unavailable. Computer preserved; do not loop or recreate it.",
            }
        finally:
            self.store.finish_ensure(user_id, owner)

    def execute(self, user_id, data):
        device_id, invocation_id = data["device_id"], data["invocation_id"]
        if (
            not isinstance(device_id, str)
            or not isinstance(invocation_id, str)
            or not 1 <= len(invocation_id) <= 200
        ):
            raise ValueError("invalid_identity")
        capability, arguments = data["capability"], data["arguments"]
        validate(capability, arguments)
        timeout = data.get("timeout", 25)
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not 0 < timeout <= 120
        ):
            raise ValueError("invalid_timeout")
        request = {"capability": capability, "arguments": arguments}
        if data.get("parent_invocation_id"):
            request["parent_invocation_id"] = data["parent_invocation_id"]
        selected = self.store.get(user_id, device_id)
        if (
            capability == "computer"
            and arguments.get("action") == "swipe"
            and (selected["provider"] != "link" or selected["kind"] != "personal_android")
        ):
            raise ValueError("device_action_not_supported")
        if selected["provider"] == "link" and self.link:
            return self.link.execute(user_id, data)
        if selected["provider"] == "channel":
            raise ValueError("device_is_not_controllable")
        self.resources.require(user_id, selected["provider"])
        profile = getattr(self.provider(selected), "profile", DeviceProfile())
        if capability not in profile.capabilities:
            raise ValueError("device_capability_not_supported")
        device, known = self.store.claim(user_id, device_id, invocation_id, request, timeout + 5)
        if known is not None:
            return known
        started = time.monotonic()
        try:
            physical = self.physical(device)
            if physical == "paused":
                self.provider(device).resume(device)
                physical = self.physical(device)
            if physical != "online":
                return self.store.finish(
                    user_id,
                    invocation_id,
                    {
                        "device_id": device_id,
                        "invocation_id": invocation_id,
                        "status": "failed",
                        "error": "Device unavailable; no command was dispatched",
                    },
                )
        except Exception as error:
            return self.store.finish(
                user_id,
                invocation_id,
                {
                    "device_id": device_id,
                    "invocation_id": invocation_id,
                    "status": "failed",
                    "error": "Computer unavailable before command dispatch",
                    "provider_error": provider_failure(error).code,
                    "dispatched": False,
                },
            )
        try:
            remaining = timeout - (time.monotonic() - started)
            if remaining <= 0:
                return self.store.finish(
                    user_id,
                    invocation_id,
                    {
                        "device_id": device_id,
                        "invocation_id": invocation_id,
                        "status": "failed",
                        "error": "Deadline expired before dispatch",
                        "dispatched": False,
                    },
                )
            payload = self.provider(device).execute(
                device,
                {
                    **request,
                    "timeout": remaining,
                    "execution_environment": data.get("execution_environment", {}),
                },
                remaining,
            )
            if "operation_rejected" in payload:
                return self.store.finish(
                    user_id,
                    invocation_id,
                    {
                        "device_id": device_id,
                        "invocation_id": invocation_id,
                        "status": "failed",
                        "error": payload["operation_rejected"],
                    },
                )
            if "screenshot_base64" in payload:
                image = base64.b64decode(payload.pop("screenshot_base64"), validate=True)
                if len(image) > 8 * 1024 * 1024:
                    raise ValueError("image_too_large")
                media_id = self.store.media(user_id, device_id, image)
                payload["screenshot"] = {
                    "attachment_id": media_id,
                    "media_id": media_id,
                    "url": "/devices/media/" + media_id,
                    "mime_type": "image/png",
                }
            result = {
                "device_id": device_id,
                "invocation_id": invocation_id,
                "status": "succeeded",
                "result": payload,
                "duration_ms": round((time.monotonic() - started) * 1000),
            }
            return self.store.finish(user_id, invocation_id, result)
        except DispatchRejected as error:
            return self.store.finish(
                user_id,
                invocation_id,
                {
                    "device_id": device_id,
                    "invocation_id": invocation_id,
                    "status": "failed",
                    "error": error.code,
                    "dispatched": False,
                },
            )
        except Exception:
            result = {
                "device_id": device_id,
                "invocation_id": invocation_id,
                "status": "outcome_unknown",
                "error": (
                    "Execution interrupted; query the original invocation. Do not repeat effects."
                ),
            }
            return self.store.finish(user_id, invocation_id, result, release=False)

    def control(self, user_id, device_id, action, *, administrator=False):
        device = self.store.get(user_id, device_id)
        if device["provider"] == "link" and self.link:
            if action not in ("pause", "resume"):
                raise ValueError("invalid_control")
            return self.link.control(user_id, device_id, action)
        if device["provider"] == "channel" or not device["provider_ref"]:
            raise ValueError("not_a_provisioned_computer")
        if action not in ("pause", "resume"):
            raise ValueError("invalid_control")
        if not administrator:
            self.resources.require(user_id, device["provider"])
        desired = "paused" if action == "pause" else "active"
        provider = self.provider(device)
        physical = self.physical(device)
        if self.store.reconcile_control(user_id, device_id, physical):
            device = self.store.get(user_id, device_id)
        self._settle_expired_execution(user_id, device, physical)
        actual = "paused" if action == "pause" else "online"
        if physical == actual:
            self.store.set_control_state(user_id, device_id, desired)
            return self.describe(self.store.get(user_id, device_id))
        if physical not in ("online", "paused"):
            raise DeviceConflict("device_unavailable")
        control_id = self.store.begin_control(user_id, device_id, action)
        try:
            getattr(provider, action)(device)
        except Exception:
            self.store.finish_control(user_id, device_id, control_id, "recovery_required")
            raise
        self.store.finish_control(user_id, device_id, control_id, desired)
        return self.describe(self.store.get(user_id, device_id))

    def revoke(self, user_id, device_id):
        with self.store.transaction() as db:
            row = db.execute(
                "SELECT * FROM devices WHERE id=? AND user_id=?", (device_id, user_id)
            ).fetchone()
            if row is None:
                raise KeyError("device_not_found")
            selected = dict(row)
        if selected["provider"] == "link" and self.link:
            return self.link.control(user_id, device_id, "revoke")
        device = selected
        if not device["revoked_at"] and device["provider"] != "channel" and device["provider_ref"]:
            try:
                physical = self.physical(device)
                if self.store.reconcile_control(user_id, device_id, physical):
                    device = self.store.get(user_id, device_id)
                self._settle_expired_execution(user_id, device, physical)
            except ProviderUnavailable:
                pass
        with self.store.transaction() as db:
            row = db.execute(
                "SELECT * FROM devices WHERE id=? AND user_id=?", (device_id, user_id)
            ).fetchone()
            if row is None:
                raise KeyError("device_not_found")
            device = dict(row)
            if device["provider"] == "channel":
                db.execute(
                    "UPDATE devices SET revoked_at=?,generation=generation+1 WHERE id=?",
                    (time.time(), device_id),
                )
                return {"revoked": True, "stopped": True}
            lock = db.execute(
                "SELECT * FROM device_locks WHERE device_id=?", (device_id,)
            ).fetchone()
            if lock and (
                lock["deadline"] > time.time() or not lock["invocation_id"].startswith("control:")
            ):
                raise DeviceConflict("device_busy_or_outcome_unknown")
            if not device["provider_ref"]:
                record = db.execute(
                    "SELECT state FROM resource_allocations WHERE device_id=?", (device_id,)
                ).fetchone()
                if record and record["state"] != "released":
                    raise DeviceConflict("provision_requires_recovery")
            control_id = "control:release:" + uuid.uuid4().hex
            db.execute(
                "INSERT OR REPLACE INTO device_locks VALUES(?,?,?,?)",
                (device_id, user_id, control_id, time.time() + 120),
            )
            db.execute(
                "UPDATE devices SET revoked_at=?,generation=generation+1 WHERE id=?",
                (time.time(), device_id),
            )
        self.resources.mark(device_id, "releasing")
        try:
            provider = self.provider(device)
            outcome = (
                provider.stop(device)
                if device["provider_ref"] and provider.state(device) != "missing"
                else None
            )
        except Exception:
            self.resources.mark(device_id, "release_unknown")
            return {"revoked": True, "stopped": False}
        self.resources.mark(device_id, "released")
        with self.store.transaction() as db:
            db.execute(
                "DELETE FROM device_locks WHERE device_id=? AND invocation_id=?",
                (device_id, control_id),
            )
        return {"revoked": True, "stopped": None if outcome == "detached" else True}
