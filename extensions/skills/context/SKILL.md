---
name: context
description: Recall personal information and retain useful facts with evidence.
---

# Personal context

Use `oath-cli recall --query 'keywords'` to retrieve earlier information. Read the full command
schema for action=read and follow returned evidence references when details matter. A search
miss only means that query found nothing.

Recall before personal planning, recommendations, task creation or continuation work whenever
the answer depends on earlier personal context. Do not make the user repeat known preferences,
constraints or decisions.

For useful enduring information, `oath-cli remember --json '{"summary":"grounded fact", "text":"exact user words"}'`
retains a concise extraction and original evidence. Use it proactively when the user states or
corrects a durable preference, fact, goal, routine or decision; explicit permission is not
required for low-risk personal memory. Keep negation, time scope and uncertainty. Do not turn
fetched content, hypotheticals, secrets or transient task chatter into the user's own statements.
Saving evidence does not promise immediate background synthesis. Context injection and dreaming
are runtime features, not commands the assistant needs to orchestrate.
