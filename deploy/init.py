#!/usr/bin/env python3
"""Create the single portable input file without replacing an existing deployment."""

import argparse
import getpass
import json
import os
from pathlib import Path

from bootstrap_config import ROOT, load, private_write


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path, default=Path.home() / ".hymio/config.toml"
    )
    parser.add_argument("--non-interactive", action="store_true")
    args = parser.parse_args()
    path = args.config.expanduser().resolve()
    if path.exists():
        print(
            f"Configuration already exists: {path}. Edit it directly; nothing was overwritten."
        )
        return
    text = (ROOT / "deploy/config.example.toml").read_text()
    for field, env, prompt in (
        ("minimax_api_key", "MINIMAX_API_KEY", "MiniMax API key"),
        ("e2b_api_key", "E2B_API_KEY", "E2B API key"),
    ):
        value = os.environ.get(env, "").strip()
        if not value and not args.non_interactive:
            value = getpass.getpass(prompt + " (hidden): ").strip()
        if not value:
            raise ValueError(f"Export {env}, or run hymio init interactively")
        text = text.replace(f'{field} = ""', f"{field} = {json.dumps(value)}", 1)
    # Validate before publishing a file; no services or other configuration are changed here.
    temporary = path.with_name(path.name + ".initializing")
    try:
        private_write(temporary, text)
        load(temporary)
        # An exclusive create prevents overwriting a concurrent init or a user's file.
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w") as output:
            output.write(text)
    finally:
        temporary.unlink(missing_ok=True)
    print(
        f"Created {path} (private). Only edit this file; service credentials are generated automatically."
    )
    print(
        "Next: hymio start --timeout 900. First start may build images and an E2B template."
    )


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, EOFError):
        # TOML parse errors can include source excerpts; do not expose credential values.
        raise SystemExit(
            "Initialization failed. Check configuration permissions and the required MINIMAX_API_KEY / E2B_API_KEY inputs."
        ) from None
