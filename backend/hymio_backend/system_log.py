"""Bounded, asynchronous capture of real application log records."""

import logging
import logging.handlers
import queue
import traceback


class EventLogHandler(logging.Handler):
    def __init__(self, store, *, service):
        super().__init__(level=logging.INFO)
        self.store = store
        self.service = service

    def emit(self, record):
        if record.name.startswith("hymio_backend.system_log"):
            return
        try:
            message = record.getMessage()
            if record.exc_info:
                message += "\n" + "".join(traceback.format_exception(*record.exc_info))
            attributes = {
                key: getattr(record, key)
                for key in (
                    "trace_id",
                    "message_id",
                    "user_id",
                    "channel",
                    "invocation_id",
                    "media_operation",
                    "media_model",
                    "media_error_code",
                    "credential_ms",
                    "duration_ms",
                    "media_queue_ms",
                    "processing_ms",
                    "finish_reason",
                    "completion_tokens",
                )
                if getattr(record, key, None) not in (None, "")
            }
            attributes.update(
                {
                    "module": record.module,
                    "function": record.funcName,
                    "line": record.lineno,
                    "process": record.process,
                    "thread": record.threadName,
                }
            )
            self.store.append_log(
                service=self.service,
                level=record.levelname,
                logger=record.name,
                message=message,
                occurred_at=record.created,
                trace_id=str(attributes.get("trace_id", "")),
                message_id=str(attributes.get("message_id", "")),
                channel=str(attributes.get("channel", "unknown")),
                attributes=attributes,
                key=(
                    f"{self.service}:{record.process}:"
                    f"{getattr(record, 'created_ns', int(record.created * 1e9))}:"
                    f"{record.name}:{record.levelno}:{message}"
                ),
            )
        except Exception:
            self.handleError(record)


class LogCapture:
    def __init__(self, store, *, service="hymio-backend"):
        events = queue.SimpleQueue()
        self.listener = logging.handlers.QueueListener(
            events, EventLogHandler(store, service=service), respect_handler_level=True
        )
        self.handler = logging.handlers.QueueHandler(events)
        self.handler.setLevel(logging.INFO)
        self.root = logging.getLogger()
        self.previous_level = self.root.level
        self.root.setLevel(logging.INFO)
        self.listener.start()
        self.root.addHandler(self.handler)

    def stop(self):
        self.root.removeHandler(self.handler)
        self.listener.stop()
        self.root.setLevel(self.previous_level)


__all__ = ["EventLogHandler", "LogCapture"]
