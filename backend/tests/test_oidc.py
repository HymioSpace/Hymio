import json
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from hymio_backend.oidc import Oidc


class OidcTests(unittest.TestCase):
    def test_signed_identity_rejects_wrong_nonce_audience_expiry_and_signature(self):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
        jwk["kid"] = "test-key"
        claims = {
            "iss": "https://identity.example",
            "sub": "person-a",
            "aud": "hymio",
            "iat": int(time.time()),
            "exp": int(time.time()) + 60,
            "nonce": "nonce-a",
        }
        with tempfile.TemporaryDirectory() as folder:
            secret = Path(folder) / "secret"
            secret.write_text("test-only-client-secret")
            provider = Oidc(
                SimpleNamespace(
                    issuer=claims["iss"],
                    client_id="hymio",
                    client_secret_file=secret,
                    callback_url="https://hymio.example/auth/callback",
                )
            )
            signed = jwt.encode(claims, key, algorithm="RS256", headers={"kid": "test-key"})

            def transport(request):
                if request.url.path == "/keys":
                    return httpx.Response(200, json={"keys": [jwk]})
                return httpx.Response(200, json={"id_token": signed})

            provider.http.close()
            provider.http = httpx.Client(transport=httpx.MockTransport(transport))
            provider._metadata = {
                "token_endpoint": "https://identity.example/token",
                "jwks_uri": "https://identity.example/keys",
            }
            flow = {"verifier": "test-verifier", "nonce": "nonce-a"}
            self.assertEqual(provider.exchange("test-code", flow)["sub"], "person-a")
            for change, signing_key in [
                ({"nonce": "other"}, key),
                ({"aud": "other"}, key),
                ({"exp": int(time.time()) - 1}, key),
                ({}, other),
            ]:
                with self.subTest(change=change):
                    signed = jwt.encode(
                        {**claims, **change},
                        signing_key,
                        algorithm="RS256",
                        headers={"kid": "test-key"},
                    )
                    with self.assertRaises((jwt.InvalidTokenError, ValueError)):
                        provider.exchange("test-code", flow)
            provider.http.close()
