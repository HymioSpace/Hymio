# Streaming responsiveness and runtime latency

Status: Implemented

## Overview

Network receipt, durable cursor progress and visible text have separate clocks. Internal runtime
events still advance the cursor but do not rebuild chat views. Decoding runs off the main actor;
known non-display events decode only their protocol/identity envelope. Display events and history
snapshots decode once before reaching the UI. ACK still follows successful cache persistence.

The presentation buffer reveals Unicode characters at a bounded rate. Appending source text does
not restart the reveal timer; large completed backlogs catch up within a bounded interval instead
of leaving a long artificial delay. Completed/history messages do not restart typewriter animation
when unrelated tool status or view updates arrive. Reduced motion and foreground recovery can
show the complete text immediately.

Conversation updates coalesce adjacent deltas for the same step, attempt and channel, preserving
ordering at terminal messages, retries and side events. Only affected message/turn data changes.
Date parsing is cached; unrelated tool results are excluded from each turn's equality comparison.
These changes preserve message IDs, offline boundaries, retry status and turn folding semantics.

## Diagnostics

Measure model TTFT/first-content separately from receipt, first render and final display. Runtime
`invoke_agent` spans include preparation and persistence; they are not provider latency. Public
reports contain timings and synthetic samples, never production prompts or user identifiers.
