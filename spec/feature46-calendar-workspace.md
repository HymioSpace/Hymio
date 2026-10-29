# Calendar workspace

Status: Implemented

## Product

Tasks opens a real month calendar, with week and day time-grid views. Selection persists across zoom levels. Users can browse previous/next periods, return to today, select a date, and open work from its time position. A separate inbox holds ongoing work without an explicit future schedule; it is not assigned a fabricated date. Home remains a feed of changes and decisions rather than another inventory.

Native iOS uses a seven-column month, a horizontally scrollable week time grid and a focused day grid. Pinch changes calendar granularity; explicit Month/Week/Day controls provide an accessible alternative. Day/week hour density has bounded zoom controls. Web uses a wide month/time-grid canvas and an optional detail inspector. Reduced motion and keyboard/VoiceOver labels apply.

## Date semantics

Run due_at timestamps represent actual occurrences. Upcoming daily/weekly occurrences are projected from the task schedule in its IANA timezone only while the task is active; projections are labelled as repeating plans, not completed execution. Existing occurrences replace projections by task and minute. Cancelled/paused work never creates future projections. A one-off schedule can appear without a materialized run. No invented duration or end time; time-grid blocks are minimum-height labels, with collision lanes for readability, not busy-time reservations. Dates and time axes are presented in the viewer's local timezone, shown explicitly.

## Boundaries

This iteration does not sync calendars, reserve availability, drag-reschedule tasks or invent deadlines. Changes to actual schedules use the existing authenticated editor and scheduler semantics. Same task ID and existing detail/continuation controls remain compatible. Recurrence projection is bounded by the visible period, not an unbounded event expansion.

## Verification

Date-model regression cases cover month boundaries, timezone recurrence, duplicates, paused/finished work and unscheduled work. Native build and interactive month/week/day checks cover selection, zoom, empty days and detail navigation. Synthetic preview data never enters production accounts.

The iOS shell keeps a healthy WebSocket across brief background/foreground transitions, delays teardown
for longer background periods, and preserves cached conversation content while reconnecting. Streaming
updates are coalesced outside the main conversation projection, completed rows stay equatable, and
status-only overlays no longer rebuild for every token delta. Verification includes a signed simulator
build, real-account background/foreground checks, the streaming performance preview, and a Time Profiler
pass; synthetic traffic remains available only in debug previews. The final simulator run restored all
38 cached conversation events immediately, resumed after ten seconds in the background without opening a
new WebSocket, and recorded 1,266 rendered stream frames without a gap over 50 ms and a 35 ms maximum gap.
