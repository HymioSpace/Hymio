---
name: tasks
description: Manage durable tasks through Oath task tools.
---

Use task_create for accepted background work, with explicit requirements, trigger, executor,
context, acceptance, and budget. Reuse intent_key and existing task IDs. Use task_list/get
for status; task_update/message for changes and replies; task_pause/resume/cancel for control.
Never poll in a loop. Completion and input requests arrive as app.task events.
Task agents report with task_report. task_review records the main agent's verification of
result evidence; require the user's explicit decision when acceptance.review is user.
Ordinary immediate questions do not create tasks. No application generation tools are provided.
