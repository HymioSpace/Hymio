import os
from pathlib import Path

import uvicorn

from .app import build_app
from .service import KitsService


def _manifests():
    configured = os.environ.get("KIT_HOST_MANIFESTS_DIR")
    if configured:
        return Path(configured)
    here = Path(__file__).resolve()
    candidates = []
    for depth in (1, 2, 3):
        if depth < len(here.parents):
            candidates.append(here.parents[depth] / "kits")
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    raise RuntimeError("Kit manifest directory is not configured")


database = Path(os.environ.get("KIT_HOST_DATABASE", "/data/kits.sqlite3"))
token_file = Path(os.environ["KIT_HOST_TOKEN_FILE"])
token = token_file.read_text().strip()
if len(token) < 32:
    raise RuntimeError("KIT_HOST_TOKEN_FILE must contain at least 32 characters")
app = build_app(KitsService(database, _manifests()), token)

uvicorn.run(
    app,
    host=os.environ.get("KIT_HOST_HOST", "0.0.0.0"),
    port=int(os.environ.get("KIT_HOST_PORT", "8090")),
    access_log=False,
)
