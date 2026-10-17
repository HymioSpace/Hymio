# Chrome

Browser extension entry points, background tasks, content scripts and capture permissions live here. Reuse suitable web UI, A2UI, protocol and communication packages from `packages/`.

Page capture becomes an import through Hymio's Context API. An ongoing sync connection is a separate, explicit authorization. Browser-specific capture permissions do not grant access to every connector or Kit.

Status: responsibility scaffold; no extension manifest or build yet.
