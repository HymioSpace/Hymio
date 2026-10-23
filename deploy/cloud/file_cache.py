#!/usr/bin/env python3
"""Opt-in THP policy workaround for file-cache thrashing on Linux hosts."""

import argparse
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path("/sys/kernel/mm/transparent_hugepage")
STATE = Path("/var/lib/hymio/file-cache-original.json")
NAME = re.compile(r"hugepages-[0-9]+kB")


def policy(path: Path) -> str:
    match = re.search(r"\[([^]]+)\]", path.read_text())
    if not match:
        raise ValueError(f"Cannot identify selected policy: {path}")
    return match[1]


def control(root: Path, name: str) -> Path:
    return root / name if name in {"enabled", "defrag"} else root / name / "file_enabled"


def apply(root: Path = ROOT, state: Path = STATE) -> None:
    controls = sorted(root.glob("hugepages-*/file_enabled"))
    if not controls:
        print("No file-backed THP controls; no changes needed.")
        return
    targets = {p.parent.name: "never" for p in controls}
    targets.update(enabled="madvise", defrag="never")
    current = {name: policy(control(root, name)) for name in targets}
    if not state.exists():
        state.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation preserves the original values across repeated starts.
        with state.open("x") as output:
            json.dump(current, output, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
    else:
        saved = json.loads(state.read_text())
        if set(saved) != set(targets):
            raise ValueError("Saved controls differ; restore or review backup before applying")
    for name, target in targets.items():
        path = control(root, name)
        path.write_text(target + "\n")
        if policy(path) != target:
            raise RuntimeError(f"Policy did not take effect: {path}")
    print(f"Disabled file-backed THP for {len(controls)} sizes; anonymous THP=madvise, defrag=never; originals: {state}")


def restore(root: Path = ROOT, state: Path = STATE) -> None:
    values = json.loads(state.read_text())
    # Validate everything before changing any controls.
    for name, value in values.items():
        allowed = {"always", "always+exec", "never"}
        if name == "enabled":
            allowed = {"always", "madvise", "never"}
        elif name == "defrag":
            allowed = {"always", "defer", "defer+madvise", "madvise", "never"}
        elif not NAME.fullmatch(name):
            raise ValueError("Invalid saved control name")
        if value not in allowed:
            raise ValueError("Invalid saved file-backed THP policy")
    for name, value in values.items():
        path = control(root, name)
        if not path.exists():
            raise RuntimeError(f"Missing control; keep backup for manual recovery: {path}")
        path.write_text(value + "\n")
        if policy(path) != value:
            raise RuntimeError(f"Policy did not take effect: {path}")
    state.unlink()
    print("Restored original THP policies.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["status", "apply", "restore"])
    args = parser.parse_args()
    if args.action == "status":
        for name in ("enabled", "defrag"):
            if (ROOT / name).exists():
                print(name, policy(ROOT / name))
        for path in sorted(ROOT.glob("hugepages-*/file_enabled")):
            print(path.parent.name, policy(path))
        print("Saved original policies:", STATE if STATE.exists() else "none")
        return
    if os.geteuid() != 0:
        parser.error("apply and restore require root")
    try:
        {"apply": apply, "restore": restore}[args.action]()
    except (OSError, ValueError, RuntimeError) as error:
        sys.exit(str(error))


if __name__ == "__main__":
    main()
