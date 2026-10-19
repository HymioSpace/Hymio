"""Device lifecycle and execution, independent of HTTP transport."""

import base64
import time

from .providers import E2BComputer
from .store import DeviceStore
from .validation import validate


class DeviceService:
    def __init__(self, settings, sessions):
        self.settings = settings
        self.store = DeviceStore(sessions)
        self.providers = {}
        if settings.e2b_key_file:
            self.providers["e2b"] = E2BComputer(settings.e2b_key_file, settings.e2b_template)

    def provider(self, device):
        if device["provider"] not in self.providers:
            raise ValueError("provider_not_configured")
        return self.providers[device["provider"]]

    def describe(self, device):
        channel = device["provider"] == "channel"
        physical = (
            ("online" if device["last_seen"] > time.time() - 75 else "offline")
            if channel
            else (self.provider(device).state(device) if device["provider_ref"] else "offline")
        )
        state = device["control_state"] if device["control_state"] != "active" else physical
        return {
            "device_id": device["id"],
            "name": "E2B 云电脑" if device["provider"] == "e2b" else device["name"],
            "kind": device["kind"],
            "provider": device["provider"],
            "generation": device["generation"],
            "state": state,
            "provider_state": physical,
            "online": state == "online",
            "capabilities": [] if channel else ["bash", "browser", "computer"],
            "workspace": None if channel else "~/workspace",
            "resolution": {"width": 1280, "height": 800},
            "preserves_files_on_revoke": False,
        }

    def provision(self, user_id):
        device = self.store.create(user_id, self.settings.computer_provider)
        if not device["provider_ref"]:
            invocation = "provision:" + device["id"]
            _, result = self.store.claim(
                user_id, device["id"], invocation, {"provision": device["provider"]}, 120
            )
            if result is None:
                try:
                    reference = self.provider(device).provision(device)
                    self.store.set_ref(user_id, device["id"], reference)
                    self.store.finish(user_id, invocation, {"status": "succeeded"})
                except Exception:
                    self.store.finish(
                        user_id, invocation, {"status": "outcome_unknown"}, release=False
                    )
                    raise
        return self.describe(self.store.get(user_id, device["id"]))

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
        selected = self.store.get(user_id, device_id)
        if selected["provider"] == "channel":
            raise ValueError("device_is_not_controllable")
        device, known = self.store.claim(user_id, device_id, invocation_id, request, timeout + 5)
        if known is not None:
            return known
        started = time.monotonic()
        try:
            if self.provider(device).state(device) != "online":
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
                    },
                )
            payload = self.provider(device).execute(
                device, {**request, "timeout": remaining}, remaining
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

    def control(self, user_id, device_id, action):
        device = self.store.get(user_id, device_id)
        if device["provider"] == "channel" or not device["provider_ref"]:
            raise ValueError("not_a_provisioned_computer")
        if action not in ("pause", "resume"):
            raise ValueError("invalid_control")
        desired = "paused" if action == "pause" else "active"
        provider = self.provider(device)
        if device["control_state"] == desired and provider.state(device) == (
            "paused" if action == "pause" else "online"
        ):
            return self.describe(device)
        control_id = self.store.begin_control(user_id, device_id, action)
        try:
            getattr(provider, action)(device)
        except Exception:
            self.store.finish_control(user_id, device_id, control_id, "recovery_required")
            raise
        self.store.finish_control(user_id, device_id, control_id, desired)
        return self.describe(self.store.get(user_id, device_id))

    def revoke(self, user_id, device_id):
        device = self.store.get(user_id, device_id)
        self.store.revoke(user_id, device_id)
        stopped = True
        if device["provider"] != "channel" and device["provider_ref"]:
            try:
                self.provider(device).stop(device)
            except Exception:
                stopped = False
        return {"revoked": True, "stopped": stopped}
