import base64
import hashlib
from urllib.parse import urlencode

import httpx
import jwt


class Oidc:
    def __init__(self, settings):
        self.settings = settings
        self.http = httpx.Client(timeout=10, follow_redirects=False, trust_env=False)
        self._metadata = None

    def metadata(self):
        if self._metadata is None:
            response = self.http.get(
                self.settings.issuer.rstrip("/") + "/.well-known/openid-configuration"
            )
            response.raise_for_status()
            data = response.json()
            if data["issuer"] != self.settings.issuer:
                raise ValueError("OIDC issuer mismatch")
            self._metadata = data
        return self._metadata

    def authorize_url(self, state, verifier, nonce):
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .decode()
            .rstrip("=")
        )
        return (
            self.metadata()["authorization_endpoint"]
            + "?"
            + urlencode(
                {
                    "client_id": self.settings.client_id,
                    "redirect_uri": self.settings.callback_url,
                    "response_type": "code",
                    "scope": "openid profile",
                    "state": state,
                    "nonce": nonce,
                    "code_challenge": challenge,
                    "code_challenge_method": "S256",
                }
            )
        )

    def exchange(self, code, flow):
        metadata = self.metadata()
        response = self.http.post(
            metadata["token_endpoint"],
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": self.settings.client_id,
                "client_secret": self.settings.client_secret_file.read_text().strip(),
                "redirect_uri": self.settings.callback_url,
                "code_verifier": flow["verifier"],
            },
        )
        response.raise_for_status()
        raw = response.json()["id_token"]
        keys = self.http.get(metadata["jwks_uri"])
        keys.raise_for_status()
        key_set = jwt.PyJWKSet.from_dict(keys.json())
        kid = jwt.get_unverified_header(raw).get("kid")
        candidates = [key for key in key_set.keys if kid is None or key.key_id == kid]
        if len(candidates) != 1:
            raise ValueError("Invalid OIDC signing key")
        claims = jwt.decode(
            raw,
            candidates[0].key,
            algorithms=["RS256", "ES256"],
            audience=self.settings.client_id,
            issuer=self.settings.issuer,
            options={"require": ["exp", "iat", "iss", "sub", "aud", "nonce"]},
        )
        if claims["nonce"] != flow["nonce"]:
            raise ValueError("OIDC nonce mismatch")
        if (
            isinstance(claims["aud"], list)
            and len(claims["aud"]) > 1
            and claims.get("azp") != self.settings.client_id
        ):
            raise ValueError("OIDC authorized party mismatch")
        return claims
