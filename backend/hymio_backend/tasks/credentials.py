"""Short-lived service delivery credentials for the existing remote-auth contract."""

import base64
import hashlib
import hmac
import json
import time

from ..session_store import Unauthorized

PREFIX = "hymio-service."


def issue(settings, user_id):
    payload = (
        base64.urlsafe_b64encode(
            json.dumps(
                {"user_id": user_id, "exp": time.time() + 60, "aud": "oath"}, separators=(",", ":")
            ).encode()
        )
        .decode()
        .rstrip("=")
    )
    key = settings.service_token_file.read_bytes().strip()
    signature = hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()
    return PREFIX + payload + "." + signature


def verify(settings, credential):
    try:
        payload, signature = credential.removeprefix(PREFIX).split(".")
        expected = hmac.new(
            settings.service_token_file.read_bytes().strip(), payload.encode(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise Unauthorized()
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        if data["aud"] != "oath" or not time.time() < data["exp"] < time.time() + 120:
            raise Unauthorized()
        return {"user_id": data["user_id"], "expires_at": data["exp"]}
    except (ValueError, KeyError, TypeError):
        raise Unauthorized() from None
