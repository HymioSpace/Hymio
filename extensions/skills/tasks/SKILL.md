---
name: tasks
description: Track accepted work, schedules, progress and delegated outcomes.
---

# Tasks

Use `oath-cli tasks` to maintain work with an outcome. Read `oath-cli help tasks` for schemas.
Capture work already accepted using action=capture; creating a schedule dispatches future work,
so it is different from recording a task you are already doing. Reuse the returned task_id and
run_id for progress and completion.

```sh
oath-cli tasks --action list
oath-cli tasks --action get --task-id TASK_ID
```

For app.task.due, start the specified run before acting. Record meaningful intermediate progress
and complete/fail/block it with the outcome. Reminders deliver a message; general work needs an
explicit result. Scheduling uses an IANA timezone and explicit once/daily/weekly fields.

Independent work can use `oath-cli subagent_spawn --json` with objective, success_criteria and
bounds; the returned agent_id identifies its separate context. Use subagent_get/list/cancel to
manage it and subagent_notify for important intermediate findings from a child. Completion is an
event. Child agents cannot delegate or manage the owner's tasks.
