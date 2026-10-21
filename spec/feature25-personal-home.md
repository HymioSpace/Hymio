# Personal assistant product surfaces

## Experience

Hymio opens on a short account of real work, with the otter as its companion: what needs
attention, what changed and one thing currently moving forward. Conversation remains a
single continuous destination. Tasks and account controls have clear places; Trace is a
secondary inspection route, not primary navigation.

iOS uses four native tabs (Now, Conversation, Tasks, Account) with separate navigation
stacks and one shared connection. Web uses a labelled sidebar and a wider home composition;
it retains its persistent conversation and focused task inspector. No memory/preferences or
inspiration controls are shown before their behavior exists.

## Information and state

Task groups answer who acts next: needs attention (blocked/failed), in progress, scheduled,
and results. Status uses text and symbols plus restrained color: amber for attention, blue
for work and neutral for past results. Cards show title, the latest useful result/progress
and next action. Details retain the full timeline and management operations.

Home changes compare task/run fingerprints with a per-account, per-backend local baseline
saved on background/visibility changes. A fresh installation uses “recent progress”, never
claims to know an offline interval. Only changed tasks are presented as new progress; ongoing
work is limited to one item. Errors and empty/loading states are distinct, with retry.
Late requests must not cross account boundaries. These local baselines are not message ACKs.

The task editor asks for kind, name, objective and time. Completion criteria and lateness are
progressively disclosed; an empty criterion gets an explicit kind-appropriate default in the
submitted data. Editing says Save changes and preserves schedule timezone. A reminder defaults
to a chosen future time rather than immediate execution.

## Conversation and account

User bubbles size to their content with a maximum width. Work disclosures are quiet single
lines with bounded indentation; final answers stay outside them. Scrolling follows output
only while the user is near the bottom and preserves reading position otherwise. Short/new
conversations align at the top; completion must not scroll into an empty spacer. History
loading preserves its anchor. A visible latest-message action restores following.

Login wording addresses new and returning users alike, with an explicit signup link. Display
names prefer verified human names/usernames and never fall back to a UUID. Device presentation
uses “cloud computer”; provider identifiers remain in diagnostics. Provisioning is owned by the
backend and agent, not a manual preparation button in account settings.

## Visual system

Keep the existing blue scarf otter, system type and adaptive surface/ink/muted/accent tokens.
Use 17pt iOS body, dynamic headings, 44pt controls, semantic backgrounds and one amber attention
pair (light #9A641E on #FFF5E7, dark #F0C384 on #392E21). Home has a compact greeting and
companion and grouped factual cards; only first-use onboarding offers a conversation action. Motion communicates state and
respects Reduce Motion; text/status still explains work without animation. iOS uses native
safe areas, tabs, sheets and keyboard behavior; Web prioritizes scan width and labelled navigation.

## Home lifecycle and extension

Home does not quote the latest assistant response or repeat a conversation-resume button.
A verified new account (task fetch and conversation sync complete, no tasks/history) gets an
introductory card with a single start-conversation action. Returning accounts without updates
get a quiet status card; task history is reachable with a secondary link. Loading and fetch
failure stay distinct from emptiness. Scheduled work appears as its own upcoming module.
Attention, changes, current work and upcoming work are independently rendered modules; a task
cannot appear both as a change and ongoing work. Memory and Kit can add their own modules
with their own loading/empty/content states, without replacing the page shell or simulating
unimplemented entries. There are no reserved blank tiles or disabled future-feature buttons.

Work summaries use compact spacing before the final answer. The iOS work disclosure links
directly to its trace ID; legacy work without an ID does not offer an unrelated list link.
The trace index starts with actual execution records, without a static execution-chain graphic
or an empty synchronized-events section.
