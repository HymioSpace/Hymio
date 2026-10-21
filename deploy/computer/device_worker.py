"""Controlled device worker; stdout is a JSON result only."""

import json
import sys

from controller import execute

print(json.dumps(execute(json.load(sys.stdin))), flush=True)
