"""Make Oath extension inputs readable by its non-root container identity."""

import argparse
import os
from pathlib import Path


def public_files(root):
    for folder in (root / "skills", root / "prompts"):
        if not folder.exists():
            continue
        for path in folder.rglob("*"):
            if path.is_file():
                yield path
    tools = root / "tools"
    if tools.exists():
        for path in tools.glob("*.py"):
            yield path


def fix(root, uid, gid):
    directories = [path for path in root.rglob("*") if path.is_dir()]
    for path in (root, *directories):
        path.chmod(path.stat().st_mode | 0o755)
    for path in public_files(root):
        path.chmod(0o644)
    connection = root / "tools/_connection.local"
    if connection.is_file():
        os.chown(connection, uid, gid)
        connection.chmod(0o600)
    return len(directories), len(list(public_files(root)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extensions", type=Path, required=True)
    parser.add_argument("--uid", type=int, default=10001)
    parser.add_argument("--gid", type=int, default=10001)
    parser.add_argument("--fix", action="store_true")
    args = parser.parse_args()
    root = args.extensions.expanduser().resolve()
    if not (root / "skills").is_dir():
        parser.error("extensions directory must contain skills/")
    if not args.fix:
        directories = [root, *(path for path in root.rglob("*") if path.is_dir())]
        blocked = [
            str(path) for path in directories if not path.stat().st_mode & 0o001
        ] + [
            str(path) for path in public_files(root) if not path.stat().st_mode & 0o004
        ]
        if blocked:
            print("Runtime cannot traverse or read:")
            print("\n".join(blocked))
            raise SystemExit(1)
        print("Extension directories and public files are readable.")
        return
    directories, files = fix(root, args.uid, args.gid)
    print(f"Updated {directories} directories and {files} public files for UID {args.uid}.")


if __name__ == "__main__":
    main()
