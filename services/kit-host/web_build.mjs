import fs from "node:fs/promises"
import { createRequire } from "node:module"
import os from "node:os"
import path from "node:path"

const require = createRequire(new URL("./web/package.json", import.meta.url))
const { build } = require("esbuild")
const request = JSON.parse(await readStdin())
const root = await fs.mkdtemp(path.join(os.tmpdir(), "hymio-kit-web-"))

try {
  for (const [relative, content] of Object.entries(request.files || {})) {
    const target = safePath(root, relative)
    await fs.mkdir(path.dirname(target), { recursive: true })
    await fs.writeFile(target, content)
  }
  const result = await build({
    absWorkingDir: root,
    entryPoints: [request.entry],
    outdir: "out",
    bundle: true,
    write: false,
    format: "esm",
    platform: "browser",
    target: ["safari17"],
    jsx: "automatic",
    minify: true,
    sourcemap: false,
    legalComments: "none",
    define: { "process.env.NODE_ENV": '"production"' },
    nodePaths: [request.modules],
    logLevel: "silent",
  })
  let javascript = ""
  let css = ""
  for (const output of result.outputFiles || []) {
    if (output.path.endsWith(".js")) javascript += output.text
    if (output.path.endsWith(".css")) css += output.text
  }
  if (!javascript) throw new Error("React entry produced no JavaScript")
  javascript = javascript.replaceAll("</script", "<\\/script")
  css = css.replaceAll("</style", "<\\/style")
  const policy =
    "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; " +
    "img-src data:; font-src data:; connect-src 'none'; frame-src 'none'; " +
    "media-src 'none'; form-action 'none'; base-uri 'none'; navigate-to 'none'"
  const html =
    "<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">" +
    "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1,viewport-fit=cover\">" +
    `<meta http-equiv="Content-Security-Policy" content="${policy}">` +
    "<meta name=\"color-scheme\" content=\"light dark\">" +
    `<style>${css}</style></head><body><div id="root"></div>` +
    `<script type="module">${javascript}</script></body></html>`
  process.stdout.write(
    JSON.stringify({ ok: true, html, bytes: Buffer.byteLength(html), errors: [] }),
  )
} catch (error) {
  const messages = []
  for (const item of error?.errors || []) {
    messages.push(
      `${item.location?.file || "web"}:${item.location?.line || 0}:${item.location?.column || 0} ` +
        item.text,
    )
  }
  if (!messages.length) messages.push(error instanceof Error ? error.message : String(error))
  process.stdout.write(
    JSON.stringify({ ok: false, html: "", bytes: 0, errors: messages.slice(0, 20) }),
  )
} finally {
  await fs.rm(root, { recursive: true, force: true })
}

function safePath(root, relative) {
  if (typeof relative !== "string" || relative === "" || path.isAbsolute(relative)) {
    throw new Error("Invalid source path")
  }
  const target = path.resolve(root, relative)
  if (!target.startsWith(root + path.sep)) throw new Error("Source path escapes workspace")
  return target
}

function readStdin() {
  return new Promise((resolve, reject) => {
    let body = ""
    process.stdin.setEncoding("utf8")
    process.stdin.on("data", (chunk) => {
      body += chunk
      if (body.length > 2 * 1024 * 1024) reject(new Error("Build input is too large"))
    })
    process.stdin.on("end", () => resolve(body))
    process.stdin.on("error", reject)
  })
}
