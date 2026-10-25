import asyncio
import json
import socket
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import uvicorn
from starlette.applications import Starlette
from starlette.routing import WebSocketRoute
from websockets.asyncio.client import connect
from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosedError

from hymio_backend.agent_gateway import relay_agent
from hymio_backend.devices.store import DeviceStore
from hymio_backend.session_store import SessionStore


class AgentGatewayTests(unittest.IsolatedAsyncioTestCase):
    async def test_large_status_does_not_disconnect_and_heartbeats_continue(self):
        payload = "x" * (9 * 1024 * 1024)
        forwarded = []

        async def agent(ws):
            forwarded.append(json.loads(await ws.recv()))
            await ws.send(payload)
            async for message in ws:
                if message == "close-too-large":
                    await ws.close(code=1009)
                    return
                await ws.send(message)

        async with serve(agent, "127.0.0.1", 0) as upstream:
            port = upstream.sockets[0].getsockname()[1]
            settings = SimpleNamespace(oath_ws=f"ws://127.0.0.1:{port}", origins=())

            temp = tempfile.TemporaryDirectory()
            self.addCleanup(temp.cleanup)
            channels = DeviceStore(
                SessionStore(SimpleNamespace(database=Path(temp.name) / "state.sqlite"))
            )
            devices = SimpleNamespace(store=channels, ensure_available=lambda user: None)
            sessions = SimpleNamespace(verify=lambda credential: {"user_id": "alice"})

            async def endpoint(ws):
                await relay_agent(ws, settings, sessions, devices)

            app = Starlette(routes=[WebSocketRoute("/agent/ws", endpoint)])
            listener = socket.socket()
            listener.bind(("127.0.0.1", 0))
            server = uvicorn.Server(uvicorn.Config(app, log_level="error", lifespan="off"))
            task = asyncio.create_task(server.serve(sockets=[listener]))
            try:
                async with asyncio.timeout(10):
                    while not server.started:
                        await asyncio.sleep(0.01)
                async with connect(
                    f"ws://127.0.0.1:{listener.getsockname()[1]}/agent/ws", max_size=None
                ) as client:
                    await client.send(
                        json.dumps(
                            {
                                "v": 2,
                                "type": "agent.attach",
                                "payload": {
                                    "credential": "synthetic",
                                    "user_id": "alice",
                                    "client_id": "synthetic-web",
                                    "channel_kind": "ios",
                                },
                            }
                        )
                    )
                    self.assertEqual(len(await asyncio.wait_for(client.recv(), 10)), len(payload))
                    self.assertEqual(forwarded[0]["payload"]["channel_kind"], "ios")
                    for i in range(3):
                        await client.send(f"heartbeat-{i}")
                        self.assertEqual(await asyncio.wait_for(client.recv(), 5), f"heartbeat-{i}")
                    await client.send("close-too-large")
                    with self.assertRaises(ConnectionClosedError) as closed:
                        await asyncio.wait_for(client.recv(), 5)
                    self.assertEqual(closed.exception.rcvd.code, 1009)
            finally:
                server.should_exit = True
                await asyncio.wait_for(task, 10)
                listener.close()
