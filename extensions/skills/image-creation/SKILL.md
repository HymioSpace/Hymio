---
name: image-creation
description: Generate images from text or a character reference using MiniMax image-01.
---

# Image creation

Use `image_generate` when the user asks for an image. Compose a concrete prompt (up to 1500 characters): subject, composition, style, lighting and text if requested. Choose the appropriate aspect_ratio; generate one image per request.

For reference generation, pass one owned image attachment_id. MiniMax currently supports **character references**, best with a single frontal portrait. Do not promise arbitrary image editing or exact preservation of logos, layouts or pixels. Explain that limitation when relevant.

Results include a private `url`. Display it with `![description](url)`. The image is saved by Hymio and remains available across clients; never expose provider credentials or invent a file path. Clearly identify generated images. If the outcome is unknown, do not repeat the paid request automatically.
