# Codex desktop

## Send a message

1. Determine the intended project and chat from the user's request and the visible
   interface. If multiple chats match, clarify before sending. Do not create a new
   chat when asked to continue an existing one.
2. Open or focus Codex, capture the screen, and identify the matching chat and
   composer. Do not assume a shortcut, sidebar position or remembered coordinate.
3. Inspect the existing draft. Preserve it; if it conflicts with the requested
   message, ask how to handle it rather than selecting all and overwriting it.
4. Click the verified composer and type the user's message. Forward a concise
   faithful instruction, preserving their target, scope and constraints. Do not
   silently append permission to commit, push, deploy or change security settings.
5. Submit using the visually identified send control. Capture again and verify
   that the message appears in the intended chat. A tool acknowledgement only
   confirms input delivery; it does not prove Codex accepted or completed the work.

If delivery is uncertain, inspect the chat before attempting another send. Never
duplicate a coding request just because the UI is slow.

## Progress, follow-up and interruption

- To check progress, read visible status and recent output through screenshot
  understanding. Distinguish “submitted”, “running”, “needs approval” and “completed”.
  Report visible evidence; do not equate a quiet composer with successful completion.
- A request to check progress is read-only. Do not interrupt, send “continue”, switch
  branches or start another turn unless the user requested it.
- For an authorized follow-up, use the same verified chat. For stop/interruption,
  identify the active chat and its visible stop control first; verify the result.
- Code execution approval, credentials and macOS permissions are not routine chat
  buttons. Show the request to the user; do not approve blanket access on their behalf.
- Do not continuously poll screenshots while coding is running. After verifying
  submission, return to the user; use Hymio task scheduling only if follow-up was
  requested. UI automation currently has no completion-event subscription.

## Future structured integration

Codex App Server is an official protocol for threads, turns, streamed events and
approval handling: https://learn.chatgpt.com/docs/app-server . HymioDevice does not
yet expose an adapter. A separately launched server must not be assumed to share
the existing desktop chat, login or live execution. Do not inspect private Codex
databases or invent protocol calls as a substitute for an implemented adapter.
