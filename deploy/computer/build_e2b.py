"""Build the E2B Desktop template. API key is read from a private file."""

import argparse
from pathlib import Path

from e2b import Template

parser = argparse.ArgumentParser()
parser.add_argument("--key-file", type=Path, required=True)
parser.add_argument("--name", default="hymio-desktop")
parser.add_argument(
    "--ensure", action="store_true", help="Build only if the template alias is absent"
)
args = parser.parse_args()
key = args.key_file.read_text().strip()
if args.ensure and Template.exists(args.name, api_key=key):
    print("E2B template available: " + args.name)
    raise SystemExit(0)
template = (
    Template()
    .from_template("desktop")
    .run_cmd(
        "apt-get update && apt-get install -y python3-venv libreoffice-calc fonts-noto-cjk "
        "&& python3 -m venv /opt/hymio "
        "&& /opt/hymio/bin/pip install playwright==1.55.0",
        user="root",
    )
)
Template.build(template, alias=args.name, api_key=key)
