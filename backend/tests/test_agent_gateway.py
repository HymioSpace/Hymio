import asyncio
import socket
import unittest
from types import SimpleNamespace

import uvicorn
from starlette.applications import Starlette
from starlette.routing import WebSocketRoute
from websockets.asyncio.client import connect
from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosedError

from hymio_backend.agent_gateway import relay_agent


class AgentGatewayTests(unittest.IsolatedAsyncioTestCase):
    async def test_large_status_does_not_disconnect_and_heartbeats_continue(self):
        payload = "x" * (9 * 1024 * 1024)

        async def agent(ws):
            await ws.send(payload)
            async for message in ws:
                if message == "close-too-large":
                    await ws.close(code=1009)
                    return
                await ws.send(message)

        async with serve(agent, "127.0.0.1", 0) as upstream:
            port = upstream.sockets[0].getsockname()[1]
            settings = SimpleNamespace(oath_ws=f"ws://127.0.0.1:{port}", origins=())

            async def endpoint(ws):
                await relay_agent(ws, settings)

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
                    self.assertEqual(len(await asyncio.wait_for(client.recv(), 10)), len(payload))
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
