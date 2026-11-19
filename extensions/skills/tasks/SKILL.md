---
name: tasks
description: Manage durable tasks through Oath task tools.
---

Use Oath task_create for accepted background work. Use task_list/get for status,
task_update/message for changes and replies, and task_pause/resume/cancel for control.
Reuse intent_key and existing task IDs. Do not create a task for ordinary immediate answers.

Fixed reminders use executor.kind=program, action=notify and a time trigger.
Do not create a TaskAgent or subagent for them; execution at trigger time calls no model.
Recurring schedules use completion=maintain. Agent execution is for work that actually
needs fresh information, reasoning or adaptive steps.

TaskAgent reports meaningful progress, explicit waits and results with task_report.
Completion is the executor's decision; no generic parent review tool exists.
If a user decision is necessary, explicitly wait for the user and continue after their reply.
Only provide semantic fields supported by actual work; omit absent progress or next steps.
Do not poll in a loop. Significant events return through app.task messages.
Task result notification is owned by the task system; do not send it again through notify_user.
No application generation, Kits or Kit Host tools are provided.
