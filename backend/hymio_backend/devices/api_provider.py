"""Hymio speaks HTTPS to devices; host setup and execution are outside the backend."""

import json
import ssl
import time
from pathlib import Path

import httpx

from .providers import (
    ComputerProvider,
    DeviceProfile,
    DispatchRejected,
    ProviderUnavailable,
    ProvisionRejected,
)
from .target_config import APITarget, targets_from_config

__all__ = ["APIComputer", "APITarget", "targets_from_config"]


class APIComputer(ComputerProvider):
    profile = DeviceProfile(preserves_files_on_revoke=True, replace_missing=False)

    def __init__(self, targets):
        self.targets = {t.id: t for t in targets}

    def assigned(self, user_id):
        return any(t.user_id == user_id for t in self.targets.values())

    def target(self, device):
        target = self.targets.get(device["provider_ref"])
        if target is None or target.user_id != device["user_id"]:
            raise ProviderUnavailable("device_not_assigned")
        return target

    def call(self, target, payload, timeout=10):
        data = dict(payload)
        action = data.pop("action")
        token = Path(target.token_file).read_text().strip()
        context = ssl.create_default_context(cafile=target.ca_file or None)
        try:
            with httpx.Client(
                verify=context,
                trust_env=False,
                follow_redirects=False,
                timeout=httpx.Timeout(timeout, connect=min(5, timeout)),
            ) as client:
                with client.stream(
                    "POST",
                    target.base_url + "/v1/" + action,
                    headers={"Authorization": "Bearer " + token},
                    json=data,
                ) as response:
                    if response.status_code in (401, 403):
                        raise ProviderUnavailable("device_authentication_failed")
                    if response.status_code != 200:
                        raise ProviderUnavailable("device_api_unavailable")
                    raw = bytearray()
                    for part in response.iter_bytes():
                        raw.extend(part)
                        if len(raw) > 12 * 1024 * 1024:
                            raise ProviderUnavailable("device_response_too_large")
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise ValueError()
        except httpx.HTTPError:
            raise ProviderUnavailable("device_api_unavailable") from None
        except ValueError:
            raise ProviderUnavailable("device_protocol_error") from None
        if result.get("error"):
            raise ProviderUnavailable("device_execution_interrupted")
        return result

    def provision(self, device):
        target = next((t for t in self.targets.values() if t.user_id == device["user_id"]), None)
        if target is None:
            raise ProvisionRejected("device_not_assigned")
        try:
            self.call(target, {"action": "status"})
        except ProviderUnavailable as error:
            raise ProvisionRejected(error.code) from None
        return target.id

    def recover(self, device):
        return self.provision(device)

    def state(self, device):
        return self.call(self.target(device), {"action": "status"})["state"]

    def inspect(self, device):
        return self.state(device) == "online"

    def execution_idle(self, device):
        return self.call(self.target(device), {"action": "status"}).get("idle") is True

    def execute(self, device, request, timeout):
        result = self.call(
            self.target(device),
            {"action": "execute", "request": request, "deadline": time.time() + timeout},
            timeout=timeout,
        )
        if result.get("rejected"):
            raise DispatchRejected(result["rejected"])
        return result["result"]

    def pause(self, device):
        self.call(self.target(device), {"action": "pause"})

    def resume(self, device):
        self.call(self.target(device), {"action": "resume"})

    def stop(self, device):
        self.target(device)
        return "detached"
