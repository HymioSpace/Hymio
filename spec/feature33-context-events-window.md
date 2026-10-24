# Context events and window settings

Status: Implemented

## Overview

One continuing conversation keeps its history when the user changes models or context size.
Web and iOS settings offer 128K, 256K, 512K and 1M; the default preference is 256K.
The effective capacity is capped by the selected model and deployment. The settings response
reports both the preference and the effective capacity, so a smaller model is never advertised
as accepting the full selected size.

The application persists preferences per authenticated user and forwards model and window on
each user message. Oath independently validates these values, freezes them per step and uses
them for synchronous and asynchronous compression. Model/vendor parameters are not exposed
to client control. Background tasks retain the last accepted runtime preference.

The runtime owns event XML, occurrence timestamps, input ownership and compaction. Explicit
per-event dynamic metadata may include location or timezone; it does not automatically copy
application credentials or user_context. Hymio does not request location permissions in this change.
The application prompt treats event wrappers as data and keeps product replies natural.

## Limits

Capacities are declared in the application catalog and enforced independently by Oath; they may be overridden using `model_context_windows` in both
Backend and Oath deployment configuration. Unknown models default to 128K until configured.
Qwen's 262,144 native limit applies unless an extended hosted capacity is explicitly confirmed.
A requested 1M setting is a preference, not a promise that every model supports it.

Async compression prepares a pending summary at the configured threshold (default 40%).
It becomes active only at the configured synchronous threshold (default 90%). A summary
changes model-visible history and does not delete conversation records or personal memory.


## Conversation feedback

Web and iOS show context preparation only when synchronous compression blocks the current
reply. One status above the composer says the assistant is organizing earlier conversation and
will continue. It replaces the generic working indicator so the same wait does not produce two
spinners. The status follows one `compression_id` from `started` to a terminal event and cannot
outlive its five-minute visibility bound.

Asynchronous `started`, `ready`, `applied`, skipped and failed events stay silent in the chat
UI. They neither announce background work nor change an in-flight reply. The interface does
not expose tokens, token ratios, context windows, summary mechanics or retention guarantees.
Those details belong in administration and tracing. No full prompts, private facts or summary
body are sent through this status event.
