---
name: context
description: Find personal information, earlier decisions, preferences and source history with Nostalgia.
priority: 20
---

Use nostalgia action=injection for the published short index and recent pending buffer.
For remembered topics call action=search with data={target:"all",mode:"text",query:"..."}.
Use filters for source, topic, time or root_id; follow next_cursor for exact filtered lists.
Read full source records using records.read and full cards using artifacts.read.
Use records.list with query.root_id to inspect source changes over time.

Published cards and unprocessed updates may disagree. State which information is published
and which is still pending; show source references when they explain the answer. A search miss
is not proof of absence. Read truncated buffer items by their original row IDs.
If Oath truncates a tool result and supplies detail_key, use detail_read to retrieve its full
JSON before using ETags or page cursors. Prefer small pages for large originals.

Save an explicit user memory or change request with records.append and a stable operation_id.
Context uses item_type=context, context_type and context JSON. An operation request uses
item_type=command and command={command_type,command_content,target_root_ids?}. Do not place
credentials in content. A 201 response means stored, not that the requested change took effect.
Draft edits are described by the dreaming skill and use a Hymio-created dream_id.
