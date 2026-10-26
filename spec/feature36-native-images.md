# Native image input and media diagnostics

Status: Implemented

## Overview

Vision-capable main models receive uploaded images directly. Hymio owns authorization and
image storage; Oath retains immutable references and resolves bytes only for provider transport.
Document conversion, audio transcription and explicit image analysis remain media tools.

Device tools also return screenshot `media_id` values as `image_refs`. Oath resolves the owned
screenshot for the next main-model call, so a vision-capable agent can act on it without a
second image-analysis tool round trip.

```mermaid
flowchart LR
  Client --> Upload[Owned attachment]
  Upload --> Gateway[Validate and attach references]
  Gateway --> Oath
  Oath --> Resolver[Private owned-image resolver]
  Resolver --> Provider[Native image content parts]
```

The gateway discards client-supplied native references and rebuilds them from authorized
attachments. The resolver verifies the service token and the execution user's ownership.
Image bytes and credentials are excluded from runtime traces and snapshots.

## Media failures

Transport, HTTP status, provider rejection, malformed response, empty output and output-budget
exhaustion are distinct failures. Logs record safe error codes, finish reason, token counts and
stage durations, never keys, image bytes or provider response bodies. No automatic paid retry
is triggered. A failed result is delivered as a terminal tool result, rather than a pending action.

## Deployment

Native vision model choices are explicit configuration. The private resolver is reachable from
Oath workers and uses the existing internal service token. Public attachment access continues
to require the owning user's credentials.

`native_image_models` lists the Hymio model choices that receive image references. Oath also
requires `supports_images = true` on the matching provider entry. The local launcher writes that
capability for these choices and passes `--image-resolver` with the private Backend URL.
Cloud deployments configure `agent.image_resolver_url` and the mounted
`agent.image_resolver_token_file`, or `OATH_IMAGE_RESOLVER_URL` with the existing context token.
The resolver path is `/internal/media/resolve`; do not expose it through the public edge.

SiliconFlow `Qwen/Qwen3-VL-32B-Instruct` is a native image option. Its structured tool calls
must use streaming; the main agent's streaming transport is retained. Credentials and the
deployed selection list remain private configuration, not repository defaults.
