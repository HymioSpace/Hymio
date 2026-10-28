---
name: tasks
description: Track accepted work, schedules, progress and delegated outcomes.
---

# Tasks

Use `oath-cli tasks` to maintain work with an outcome. Read `oath-cli help tasks` for schemas.
Use a task for a substantial deliverable, an explicit reminder or future follow-up. Do not create
one for greetings, quick questions, memory updates, small device operations or temporary retries.
Reuse one task when the method changes; a failed attempt does not justify a duplicate task.
Capture work already accepted using action=capture; creating a task dispatches independent background work (now or later),
so it is different from recording a task you are already doing. Reuse the returned task_id and
run_id for progress and completion.

```sh
oath-cli tasks --action list
oath-cli tasks --action get --task-id TASK_ID
```

For app.task.due, start the specified run before acting. Record meaningful intermediate progress
and complete/fail/block it with the outcome. Reminders deliver a message; general work needs an
explicit result. Scheduling uses an IANA timezone and explicit once/daily/weekly fields.

Delegate a task's started run with `oath-cli tasks --action delegate --run-id RUN_ID` so execution
and history remain linked. Generic independent assignments can use `oath-cli subagent_spawn --json`
with objective, success_criteria and bounds; the returned agent_id identifies its separate context. Use subagent_get/list/cancel to
manage it and subagent_notify for important intermediate findings from a child. Completion is an
event. Child agents cannot delegate or manage the owner's tasks.

For blocked work use action=wait with a concrete wait_reason (user/time/external/device/retry),
content and next_step. Provide resume_at as a UTC Unix timestamp only when a later check is useful.
Waiting for a user decision resumes explicitly; do not poll for it. A follow-up event asks you to
check the prerequisite, not repeat a side effect. Use action=progress on the existing run when
actionable again, or explain the remaining blocker. Inspect automatic child history with
action=activity and task_id. Task state describes the outcome; tool status still comes from Oath.
