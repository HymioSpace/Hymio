"""Hymio channel ownership around Oath's authenticated transport."""

import asyncio
import json
import logging
import time
from contextlib import suppress

from starlette.websockets import WebSocketDisconnect
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, InvalidHandshake

from . import client_telemetry
from .devices.connections import ChannelConnection
from .media.store import MAX_ITEMS
from .session_store import Unauthorized

_log = logging.getLogger(__name__)


async def relay_agent(websocket, settings, sessions, devices, media=None):
    origin = websocket.headers.get("origin")
    if origin and origin not in settings.origins:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    channel = ChannelConnection(sessions, devices)
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=10)
        first = await channel.attach(raw)
        messages = {}
        background_tasks = set()

        def background(coroutine):
            task = asyncio.create_task(coroutine)
            background_tasks.add(task)
            task.add_done_callback(background_tasks.discard)

        async def log_event(message_id, stage, data, trace_id="", source="application"):
            if not getattr(sessions, "event_log", None):
                return
            try:
                await asyncio.to_thread(
                    sessions.event_log.append,
                    channel.user_id,
                    message_id,
                    stage,
                    data,
                    trace_id=trace_id,
                    channel="desk" if channel.kind == "mac" else channel.kind,
                    source=source,
                )
            except Exception:
                _log.exception("Message lifecycle log unavailable")

        async with connect(
            settings.oath_ws,
            open_timeout=10,
            # Preserve complete tool results and history frames from Oath.
            max_size=None,
            max_queue=1,
            proxy=None,
            ping_interval=20,
            ping_timeout=20,
        ) as upstream:
            await upstream.send(json.dumps(first))

            async def to_agent():
                while True:
                    frame = await websocket.receive()
                    if frame["type"] == "websocket.disconnect":
                        return
                    if frame.get("text") is None:
                        await websocket.close(code=1003)
                        return
                    if not await channel.owns():
                        await websocket.close(code=4009, reason="Channel opened elsewhere")
                        return
                    raw = frame["text"]
                    try:
                        incoming = json.loads(raw)
                        if isinstance(incoming, dict) and incoming.get("type") == "user.message":
                            message_id = str(incoming.get("id", ""))[:128]
                            channel_name = "desk" if channel.kind == "mac" else channel.kind
                            _log.info(
                                "Gateway received user message",
                                extra={
                                    "message_id": message_id,
                                    "channel": channel_name,
                                    "user_id": channel.user_id,
                                },
                            )
                            background(
                                log_event(
                                    message_id,
                                    "gateway.received",
                                    incoming.get("payload", {}),
                                )
                            )
                            messages[message_id] = time.monotonic()
                            if len(messages) > 256:
                                messages.pop(next(iter(messages)))

                            async def record_gateway_sample():
                                try:
                                    await asyncio.to_thread(
                                        client_telemetry.record,
                                        sessions,
                                        channel.user_id,
                                        {
                                            "message_id": message_id,
                                            "sent_at": time.time() * 1000,
                                            "outcome": "sent",
                                            "channel": "desk"
                                            if channel.kind == "mac"
                                            else channel.kind,
                                        },
                                        None,
                                    )
                                except Exception:
                                    _log.exception("Gateway turn sample unavailable")

                            background(record_gateway_sample())
                    except (ValueError, TypeError):
                        pass
                    if media is not None:
                        command = None
                        try:
                            command = json.loads(raw)
                            if not isinstance(command, dict):
                                raise ValueError("invalid_command")
                            if command.get("type") == "user.message":
                                payload = command.get("payload")
                                if not isinstance(payload, dict):
                                    raise ValueError("invalid_payload")
                                context = payload.get("user_context")
                                if not isinstance(context, dict):
                                    raise ValueError("invalid_context")
                                ids = context.get("attachment_ids", [])
                                if not isinstance(ids, list) or len(ids) > MAX_ITEMS:
                                    raise ValueError("invalid_attachments")
                                for identifier in ids:
                                    if not isinstance(identifier, str):
                                        raise ValueError("invalid_attachment")
                                    await asyncio.to_thread(
                                        media.reference, channel.user_id, identifier
                                    )
                                selected = await asyncio.to_thread(
                                    media.model, channel.user_id, settings.model_options[0]
                                )
                                payload["model"] = (
                                    selected
                                    if selected in settings.model_options
                                    else settings.model_options[0]
                                )
                                payload["context_window"] = await asyncio.to_thread(
                                    media.context_window, channel.user_id
                                )
                                raw = json.dumps(command)
                        except (ValueError, KeyError, LookupError):
                            await websocket.send_json(
                                {
                                    "v": 2,
                                    "type": "error",
                                    "id": command.get("id") if isinstance(command, dict) else None,
                                    "code": "invalid_message",
                                    "message": "消息或附件无效，请检查后重试。",
                                }
                            )
                            continue
                    await upstream.send(raw)

            async def to_client():
                async for message in upstream:
                    if not isinstance(message, str):
                        await websocket.close(code=1003)
                        return
                    await websocket.send_text(message)
                    try:
                        frame = json.loads(message)
                        if frame.get("type") in {"ack", "error"} and frame.get("id") in messages:
                            identifier = frame["id"]
                            trace_id = (
                                str(frame.get("trace_id", "")) if frame.get("type") == "ack" else ""
                            )
                            started = None
                            accepted_ms = None
                            if frame.get("type") == "ack":
                                started = messages.pop(identifier)
                                accepted_ms = max(0, round((time.monotonic() - started) * 1000, 3))
                            await log_event(
                                identifier,
                                "gateway." + frame["type"],
                                frame,
                                trace_id,
                            )
                            log_method = _log.info if frame["type"] == "ack" else _log.warning
                            log_method(
                                (
                                    "Gateway acknowledged user message"
                                    if frame["type"] == "ack"
                                    else "Gateway rejected user message"
                                ),
                                extra={
                                    "message_id": identifier,
                                    "trace_id": trace_id,
                                    "channel": "desk" if channel.kind == "mac" else channel.kind,
                                    "user_id": channel.user_id,
                                },
                            )
                            if accepted_ms is not None:

                                async def record_gateway_ack(
                                    message_id=identifier,
                                    accepted=accepted_ms,
                                    trace=trace_id,
                                ):
                                    try:
                                        await asyncio.to_thread(
                                            client_telemetry.record,
                                            sessions,
                                            channel.user_id,
                                            {
                                                "message_id": message_id,
                                                "sent_at": time.time() * 1000 - accepted,
                                                "accepted_ms": accepted,
                                                "trace_id": trace,
                                                "outcome": "accepted",
                                                "channel": "desk"
                                                if channel.kind == "mac"
                                                else channel.kind,
                                            },
                                            None,
                                        )
                                    except Exception:
                                        _log.exception("Gateway ACK sample unavailable")

                                background(record_gateway_ack())
                        elif frame.get("type") == "event":
                            event = frame
                            payload = event.get("payload", {})
                            trace_id = payload.get("trace_id", "")
                            if trace_id:
                                await log_event(
                                    "",
                                    "server." + str(event.get("event_type", "event")),
                                    payload,
                                    trace_id,
                                    source="otel",
                                )
                    except (ValueError, TypeError, AttributeError):
                        pass

            tasks = [
                asyncio.create_task(to_agent()),
                asyncio.create_task(to_client()),
                asyncio.create_task(channel.maintain(websocket)),
            ]
            try:
                done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    task.result()
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
    except (Unauthorized, ValueError):
        with suppress(RuntimeError, WebSocketDisconnect):
            await websocket.close(code=1008, reason="Invalid channel credentials")
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
        await channel.close()
        with suppress(RuntimeError, WebSocketDisconnect):
            await websocket.close()
