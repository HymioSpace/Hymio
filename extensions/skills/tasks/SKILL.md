---
name: tasks
description: Track user intentions, intermediate findings, blockers and results from conversation; optionally schedule or delegate work.
---

# Keep the user's work in view

A task is an outcome accepted from conversation, including ordinary questions that require research,
comparisons, writing and practical work. Scheduling is optional. Keep one record for the same intent.
Do not create tasks for greetings or interpret a tentative idea as permission to act.

## Current conversation

`capture(title, objective, success_criteria, intent_key)` records an already admitted task as running.
It does not enqueue a reminder, rerun the request or interrupt the conversation. Choose a stable key
for this specific outcome and reuse it after uncertainty; the returned runs[0].id is the run_id.
An existing key returns its original task, including a completed one; it never reopens it.

For a small completed answer, capture with status=succeeded and content to save the outcome in one call.
For ongoing work, use `progress(run_id, content, phase, next_step)`. Record discoveries, decisions,
partial deliverables and what remains. Use `block` for missing access or a decision, explaining both
what is missing and how to proceed. Later `progress` resumes the same run. Use `complete` or `fail`
for the actual terminal result. A chat response alone does not update the task. Do not fabricate stages
or percentages. Backend restart does not prove the underlying work is still executing.

```json
{"action":"capture","intent_key":"compare-two-offers-2026-10-21","title":"Compare the two offers","objective":"Compare the attached offers for the user's requirements","success_criteria":"A sourced recommendation with tradeoffs","phase":"Reading the offers","next_step":"Compare costs and exclusions"}
```

Use list/get to find existing work before creating a continuation. Cancel obsolete work when the
user changes direction. Separate deliverables can have separate tasks; tool invocations cannot.

## Future work

`create(title, objective, success_criteria, schedule)` admits NEW work through the scheduler.
Do not use it to record work already being executed. For app.task.due call start(run_id) before any
external action. A rejected start means no work should execute. Then record milestones and finish.

```json
{"mode":"now","timezone":"UTC"}
{"mode":"once","at":"2030-03-04T09:00:00+08:00","timezone":"Asia/Shanghai"}
{"mode":"daily","time":"09:00","timezone":"Asia/Shanghai"}
{"mode":"weekly","weekday":0,"time":"09:00","timezone":"Asia/Shanghai"}
```

Timed work requires the user's IANA timezone. Weekday is Monday=0. Late recurrence catches up once,
then resumes at the next future date. Do not promise precise delivery times.

## Controls and experts

- edit changes a future contract; cancel an active run before changing it.
- pause stops future scheduling, not work already admitted; resume schedules another attempt if none is live.
- cancel/delete stop future work and request cancellation of a linked expert.
- delegate(run_id) attaches a bounded independent expert to a running run. Progress and completion
  arrive automatically. Do not poll, delegate twice or complete its run yourself.
- list/get show owner-scoped records, findings and results. A task's schedule state is separate from
  the run's execution status. A running record means accepted unfinished work, not proof of a live worker.
