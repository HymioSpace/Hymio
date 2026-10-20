---
name: tasks
description: Manage durable outcomes, scheduled work and bounded expert delegation.
---

# Work that carries on

Use the `tasks` tool for a concrete commitment with a goal and completion condition.
Keep one task for the same outcome; do not create another on every continuation.

- `create`: title, objective, success_criteria, schedule. The service records the first run.
- `list` / `get(task_id)`: inspect commitments, recent runs and results before changing them.
- `edit(task_id)`: change a future contract. Cancel an active run before editing.
- `pause`: pause future scheduling; it does not retract work already admitted.
- `cancel` / `delete`: stop future work and request cancellation of a linked expert.
- `resume`: schedule work again. Completed records remain available.

## Work admission

When `app.task.due` supplies run_id, call `start(run_id)` first. A rejected start means no work
should execute. The returned objective and success criteria are the current contract.
Record significant findings with `progress(run_id, content)`. End with `complete` or `fail`;
use `block` for work that needs new information or user action. Do not leave a known blocker
labelled running. A final chat message alone does not update the task.

For independent work, call `delegate(run_id)` after start. This returns immediately; Backend
records the expert's findings and final outcome. Do not complete the run yourself while it is
delegated. Notifications arrive automatically; never poll for completion in a tool loop.

## Schedules

Always include an explicit IANA timezone for timed work. Ask if unknown.

```json
{"mode":"now","timezone":"UTC"}
{"mode":"once","at":"2030-03-04T09:00:00+08:00","timezone":"Asia/Shanghai"}
{"mode":"daily","time":"09:00","timezone":"Asia/Shanghai"}
{"mode":"weekly","weekday":0,"time":"09:00","timezone":"Asia/Shanghai"}
```

Weekday is Monday=0 through Sunday=6. Late recurring work catches up once, then resumes at the
next future date. Do not promise an exact delivery time: dependencies and running work can delay results.
