"""User/channel ownership is separate from Oath's event delivery cursor."""

import asyncio
import json
import logging
import time
import uuid

from ..session_store import Unauthorized

_log = logging.getLogger(__name__)


class ChannelConnection:
    def __init__(self, sessions, devices):
        self.sessions, self.devices = sessions, devices
        self.owner = uuid.uuid4().hex
        self.user_id = self.kind = None
        self.recovery = None

    async def attach(self, raw):
        if len(raw) > 16384:
            raise ValueError("attach_too_large")
        first = json.loads(raw)
        if (
            not isinstance(first, dict)
            or first.get("v") != 2
            or first.get("type") != "agent.attach"
        ):
            raise ValueError("attach_required")
        payload = first.get("payload")
        if not isinstance(payload, dict):
            raise ValueError("invalid_attach")
        identity = await asyncio.to_thread(self.sessions.verify, payload.get("credential", ""))
        if payload.get("user_id") not in (None, identity["user_id"]):
            raise Unauthorized()
        client_id = payload.get("client_id")
        if not isinstance(client_id, str) or not 1 <= len(client_id) <= 128:
            raise ValueError("invalid_client_id")
        kind = payload.get("channel_kind", "web")
        if kind not in ("web", "ios", "mac"):
            raise ValueError("invalid_channel")
        self.user_id, self.kind = identity["user_id"], kind
        await asyncio.to_thread(self.devices.store.connection_claim, self.user_id, kind, self.owner)
        return first

    async def owns(self):
        return await asyncio.to_thread(
            self.devices.store.connection_renew, self.user_id, self.kind, self.owner
        )

    async def recover(self):
        try:
            await asyncio.to_thread(self.devices.ensure_available, self.user_id)
        except Exception as error:
            _log.warning("Automatic computer recovery unavailable: %s", type(error).__name__)

    async def maintain(self, websocket):
        next_check = 0
        while True:
            if not await self.owns():
                await websocket.close(code=4009, reason="Channel opened elsewhere")
                return
            if time.monotonic() >= next_check and (self.recovery is None or self.recovery.done()):
                self.recovery = asyncio.create_task(self.recover())
                next_check = time.monotonic() + 60
            await asyncio.sleep(2)

    async def close(self):
        if self.recovery:
            self.recovery.cancel()
            await asyncio.gather(self.recovery, return_exceptions=True)
        if self.user_id and self.kind:
            await asyncio.to_thread(
                self.devices.store.connection_release, self.user_id, self.kind, self.owner
            )
