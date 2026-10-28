---
name: kit-builder
description: Define a clear product brief for Hymio to create or revise a real React and Python application through its dedicated coding agent. Use from the main conversation when the user asks for a new app or an application change; do not use it to write source code directly.
metadata:
  channels: [ios]
---

# Brief the application coding agent

The main conversation chooses the product and acceptance criteria. The application's dedicated
coding context owns source code, builds and releases. Do not paste HTML, React components or Python
handlers into the main conversation.

## Before calling

Pin down four product facts:

1. **One job.** What should the user accomplish, without explanation?
2. **Focal artifact.** The number, list, timeline, canvas or object the app is organized around.
3. **Inputs.** Which values create a record, and which are required?
4. **Done.** What must be visible or possible when the app is complete?

Ask only when a missing choice would materially change the data model. Otherwise make a sensible
product decision and state it through the brief.

## Create

Use `oath-cli kit_build --json` with `action="create"` and:

- a short product name and one-sentence promise;
- a concrete category, accent and user-facing item label;
- up to 12 simple fields (`text`, `number`, `boolean`, `date`);
- `requirements`: a product brief that names the screen's hierarchy, focal state, primary action,
  empty/loading/error behavior, light/dark expectations and non-goals.

Do not include implementation details such as file names, frameworks, routes or internal IDs.
The application is accepted asynchronously. A returned `status=coding` means the coding agent has
the task; it does not mean the app is published.

Omit fields only for deliberately static content such as a guide or breathing exercise.

## Edit

For an installed generated app, use `oath-cli kit_build --json` with `action="edit"`, `kit_id` and `requirements`.
Describe the desired user-visible change, what must remain stable, and how to recognize success.
Do not ask for the source in the main conversation and do not send a full replacement page.

Examples of good briefs:

- “Keep existing expense records and categories. Redesign the summary around this month's total,
  add a category breakdown derived from recent records, and make the add-expense action reachable
  above the keyboard. Do not invent a budget.”
- “Add a search field that filters visible records by note text. Preserve all data and keep the
  current visual hierarchy in light and dark appearance.”

## After the call

Tell the user what is being built, using the product name rather than implementation language.
Do not claim it is ready until the app appears as published or a completion event confirms it.

If the coding context reports a build or tool failure after accepting a new app, keep the same
`kit_id` and call `oath-cli kit_build --json` with `action="edit"` to repair it. Never create a duplicate application
merely because the asynchronous coding turn failed or timed out.

Read the current argument schema with `oath-cli help kit_build`. Use `--json` for structured arguments.
Inspect execution state with `oath-cli status INVOCATION_ID`.
