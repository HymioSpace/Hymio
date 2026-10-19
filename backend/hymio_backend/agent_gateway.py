"""Transport-only bridge. Oath owns authentication and event delivery."""

import asyncio
import logging
from contextlib import suppress

from starlette.websockets import WebSocketDisconnect
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, InvalidHandshake

_log = logging.getLogger(__name__)


async def relay_agent(websocket, settings):
    origin = websocket.headers.get("origin")
    if origin and origin not in settings.origins:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    try:
        async with connect(
            settings.oath_ws,
            open_timeout=10,
            # Oath emits full history/status frames; preserve the direct WS contract.
            max_size=None,
            max_queue=1,
            proxy=None,
            ping_interval=20,
            ping_timeout=20,
        ) as upstream:

            async def to_agent():
                while True:
                    frame = await websocket.receive()
                    if frame["type"] == "websocket.disconnect":
                        return
                    if frame.get("text") is None:
                        await websocket.close(code=1003)
                        return
                    await upstream.send(frame["text"])

            async def to_client():
                async for message in upstream:
                    if not isinstance(message, str):
                        await websocket.close(code=1003)
                        return
                    await websocket.send_text(message)

            tasks = [asyncio.create_task(to_agent()), asyncio.create_task(to_client())]
            try:
                done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    task.result()
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
    except ConnectionClosed as error:
        frame = error.rcvd or error.sent
        code = frame.code if frame else 1013
        if code in (1004, 1005, 1006, 1015):
            code = 1013
        _log.info("Agent upstream closed: code=%s", code)
        with suppress(RuntimeError, WebSocketDisconnect):
            await websocket.close(code=code, reason="Agent connection closed")
        return
    except (OSError, TimeoutError, InvalidHandshake) as error:
        _log.warning("Agent upstream unavailable: %s", type(error).__name__)
        with suppress(RuntimeError, WebSocketDisconnect):
            await websocket.close(code=1013, reason="Agent temporarily unavailable")
        return
    except WebSocketDisconnect:
        return
    finally:
        with suppress(RuntimeError, WebSocketDisconnect):
            await websocket.close()
