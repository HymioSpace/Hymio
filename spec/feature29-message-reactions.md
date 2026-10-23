# Assistant message reactions

## Product behavior

Hymio may react once to a user message with 👍 ❤️ 😂 🎉 🤔 👎. The interaction is one-way:
users cannot react to Hymio and clients expose no reaction picker or mutation endpoint. Web and
iOS render the reaction as a small opaque capsule attached to the lower-left edge of the user
bubble without covering message text. At iOS accessibility Dynamic Type sizes the capsule moves
into the metadata row below the bubble.

Reactions are optional social feedback tied to the user's tone. They must not replace a useful
answer, create a task, or appear on every message. The prompt and `react` extension define when
an emoji is appropriate.

## Identity and persistence

The agent copies the persisted `user_message` id and never guesses a target. Hymio resolves the
target, verifies ownership and role, then emits a durable `message.reaction.changed` event with
`actor: assistant`. The private `/internal/reactions` route forces that actor; there is no public
client mutation route.

Snapshots and incremental events both replace the assistant actor slot by message identity.
Reaction events do not create chat rows, start a turn, collapse a final reply, or change unread
counts. Replay of the same operation id is idempotent.

## Validation

Verify that only the internal service token can call the mutation, the public route is absent,
assistant reactions survive snapshot and incremental replay on both clients, and a reaction does
not create a text message. Inspect bubble-edge placement at normal and accessibility text sizes.
