"""Private device endpoint configuration; standard library only for bootstrap use."""

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


@dataclass(frozen=True)
class APITarget:
    id: str
    user_id: str
    base_url: str
    token_file: str
    ca_file: str = ""


def targets_from_config(items, base=None):
    base = base or Path.cwd()
    targets = []
    if not isinstance(items, (tuple, list)):
        raise ValueError("device_api_targets must be an array of tables")
    for item in items:
        target = APITarget(**item)
        url = urlsplit(target.base_url)
        if (
            not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", target.id)
            or not isinstance(target.user_id, str)
            or not 1 <= len(target.user_id) <= 256
            or url.scheme != "https"
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
            or url.path not in ("", "/")
        ):
            raise ValueError("Invalid device API target")
        paths = {}
        for field in ("token_file", "ca_file"):
            value = getattr(target, field)
            if not value and field == "ca_file":
                continue
            path = Path(value).expanduser()
            path = path if path.is_absolute() else base / path
            if not path.is_file():
                raise ValueError("Missing device API token or CA file")
            if field == "token_file":
                if path.stat().st_mode & 0o077:
                    raise ValueError("Device API token_file must have mode 0600 or stricter")
                if len(path.read_text().strip()) < 32:
                    raise ValueError("Device API token must contain at least 32 characters")
            paths[field] = str(path.resolve())
        targets.append(APITarget(**{**item, **paths, "base_url": target.base_url.rstrip("/")}))
    for values in (
        [t.id for t in targets],
        [t.user_id for t in targets],
        [t.base_url for t in targets],
    ):
        if len(set(values)) != len(values):
            raise ValueError("Device API assignments must be unique")
    return tuple(targets)
