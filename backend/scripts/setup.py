"""Create private Hymio settings after registering its Casdoor application."""

import argparse
import getpass
import json
import secrets
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--issuer", default="http://localhost:8000")
parser.add_argument("--client-id", required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
config = root / "hymio.toml"
if config.exists():
    raise SystemExit("hymio.toml already exists")
secret = getpass.getpass("Enter Casdoor client secret > ").strip()
if not secret:
    raise SystemExit("Client secret required")
private = root / "private"
private.mkdir(mode=0o700, exist_ok=True)
private.chmod(0o700)
if any((private / name).exists() for name in ("casdoor-client-secret", "oath-auth-token")):
    raise SystemExit("Private credential files already exist")
for name, value in [
    ("casdoor-client-secret", secret),
    ("oath-auth-token", secrets.token_urlsafe(48)),
]:
    path = private / name
    if path.exists():
        raise SystemExit(f"{name} already exists")
    path.write_text(value + "\n")
    path.chmod(0o600)
text = (
    (root / "hymio.example.toml")
    .read_text()
    .replace('"REPLACE_WITH_CASDOOR_CLIENT_ID"', json.dumps(args.client_id))
    .replace('"http://localhost:8000"', json.dumps(args.issuer))
)
config.write_text(text)
config.chmod(0o600)
print("Created backend/hymio.toml and private credential files.")
