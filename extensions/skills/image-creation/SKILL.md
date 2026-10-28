---
name: image-creation
description: Generate and edit images through the configured image service.
---

# Images

Read `oath-cli help image_generate` for the provider's current arguments. Use `--json` for
structured references and output settings. The same command supports generation and supported
reference-image edits. Preserve returned attachment IDs and use the authenticated output link.

For a longer generation use `--async`. Inspect an existing invocation with
`oath-cli status ID`; completion also arrives as an event. To interpret attachments, screenshots
or documents, read `oath-cli help multimodal_understand` and pass their returned attachment IDs.
Images already included in native context can be inspected directly.
