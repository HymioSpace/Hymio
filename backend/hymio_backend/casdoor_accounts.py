"""Casdoor account forms, exchanging credentials for a verified OIDC identity."""
import secrets
from urllib.parse import parse_qs, urlsplit

import httpx
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


class AccountRejected(Exception):
    pass


def obfuscate(password, organization):
    kind = organization.get("passwordObfuscatorType", "")
    if kind in ("", "Plain"):
        return password
    if kind != "AES":
        raise RuntimeError("Unsupported Casdoor password obfuscator")
    key = bytes.fromhex(organization["passwordObfuscatorKey"])
    iv = secrets.token_bytes(16)
    padder = padding.PKCS7(128).padder()
    padded = padder.update(password.encode()) + padder.finalize()
    encryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    return (iv + encryptor.update(padded) + encryptor.finalize()).hex()


class CasdoorAccounts:
    def __init__(self, settings, oidc):
        self.settings = settings
        self.oidc = oidc

    def authenticate(self, action, username, password):
        verifier, nonce, state = (secrets.token_urlsafe(32) for _ in range(3))
        auth = parse_qs(urlsplit(self.oidc.authorize_url(state, verifier, nonce)).query)
        params = {
            "clientId": self.settings.client_id,
            "responseType": "code",
            "redirectUri": self.settings.callback_url,
            "scope": "openid profile",
            "state": state,
            "nonce": nonce,
            "code_challenge": auth["code_challenge"][0],
            "code_challenge_method": "S256",
            "type": "code",
        }
        base = self.settings.issuer.rstrip("/")
        with httpx.Client(timeout=15, follow_redirects=False, trust_env=False) as http:
            response = http.get(base + "/api/get-app-login", params=params)
            response.raise_for_status()
            result = response.json()
            app = result.get("data")
            if result.get("status") != "ok" or not isinstance(app, dict):
                raise RuntimeError("Casdoor application unavailable")
            organization = app.get("organizationObj") or {}
            payload = {
                "application": app["name"],
                "organization": app["organization"],
                "username": username,
                "password": obfuscate(password, organization),
                "type": "code",
                "loginMethod": "password",
                "signinMethod": "Password",
                "autoSignin": False,
                "language": "en",
            }
            if action == "signup":
                payload.update(name=username, confirm=payload["password"])
            response = http.post(
                base + ("/api/signup" if action == "signup" else "/api/login"),
                params=params, json=payload,
            )
            response.raise_for_status()
            result = response.json()
            code = result.get("data")
            if result.get("status") != "ok" or not isinstance(code, str) or "/" in code:
                raise AccountRejected()
        return self.oidc.exchange(code, {"verifier": verifier, "nonce": nonce})
