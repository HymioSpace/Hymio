# iOS push notifications and Live Activities

Status: Implementing

## Product boundary

Push notifications reconnect the user to work that continues outside the visible conversation.
Live Activities show the current, bounded work at a glance. The Tasks screen remains the source for
full history and results.

The model may request a notification through `notify_user`, but it does not decide APNs delivery.
Hymio Backend validates the event, applies user preferences and foreground suppression, and writes
a durable outbox record. An APNs worker performs delivery and retries. Live Activity state changes
are rule-driven; the model cannot create arbitrary system activities or interactive controls.

## Events

- `started`: after scheduled work has been accepted by `tasks.start`.
- `attention`: a run is blocked or the user must resolve a decision.
- `completion`: a task or long-running conversation reached a useful terminal result.
- `chat_reply`: a task-free conversation reply is ready while the user is elsewhere.

Immediate answers, greetings, intermediate tool calls and routine progress do not generate push
notifications. A deterministic Backend rule supplies a terminal fallback if the model omits its
completion request. Task/run identity is the deduplication key.

## Privacy

Lock-screen details are disabled by default. Generic text describes the event without exposing the
task title, conversation, result, tool arguments or credentials. Users may opt into task details.
Foreground delivery is suppressed because the corresponding in-app state is already visible.
Focus, scheduled summaries and notification preview visibility remain system-controlled.

## Live Activity

There is one aggregate activity per user and installation:

- `working`: one or more accepted runs are active.
- `waiting`: the app is blocked on the user.
- `completed`: the latest run completed.
- `failed`: the latest run ended unsuccessfully.

The activity starts only for work initiated in the app and remains after it moves to the background.
Scheduled work in a fully closed app falls back to notifications in v1. A new run updates the
existing activity instead of creating another; all runs ending ends the activity. The maximum
lifetime is eight hours, followed by a 15-minute completion presentation.

Compact and minimal Dynamic Island views must remain legible inside the 28-point limited-width
circle. Lock-screen and expanded views use system text styles, at least 11-point type, semantic
colors, and a direct deep link to the related task or chat.

## Client controls

Account settings expose start, completion, attention and reply categories, task details on the lock
screen, and Live Activity use. Notification authorization is requested in context rather than on
launch. The app registers APNs and ActivityKit tokens per installation, refreshes them on launch,
and invalidates them on logout.

Push and Live Activity taps route to the related task or conversation. Foreground notifications are
handled in-app without another banner.

## Failure behavior

Registration tokens, event candidates and delivery state survive process restarts. APNs failures
are bounded and observable; invalid tokens are disabled. Missing APNs configuration leaves the
Backend functional and reports `configured=false`. A failed push never changes task state. Activity
push failure leaves the app-local activity usable and is refreshed on foreground return.
