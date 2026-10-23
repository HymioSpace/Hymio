---
name: context
description: Find personal information, earlier decisions, preferences and source history with Nostalgia.
priority: 20
---

Use the `recall` tool before answering questions about the user's earlier preferences, history,
relationships, goals or routines.
Use the `remember` tool when the user asks Hymio to retain a statement or explicitly shares a
durable personal fact. Preserve the statement verbatim; do not claim success before the result.
Context injection is performed by the runtime context builder. Do not call or invent an
`injection` tool.

Published cards and unprocessed updates may disagree. State which information is published
and which is still pending; show source references when they explain the answer. A search miss
is not proof of absence. Read truncated buffer items by their original row IDs.
If Oath truncates a tool result and supplies detail_key, use detail_read to retrieve its full
JSON before using ETags or page cursors. Prefer small pages for large originals.

Dreaming runs internally in Nostalgia on a configured schedule. It is not an Agent action; do
not start, commit or discuss a dreaming draft from ordinary conversation.
