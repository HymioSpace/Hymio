"""Seed a private, dedicated Casdoor instance using its supported init-data contract."""

import json
from urllib.parse import urlencode
from urllib.request import urlopen

from bootstrap_config import private_write


def seed(credentials):
    items = [
        {"name": name, "visible": visible, "required": required, "rule": rule}
        for name, visible, required, rule in (
            ("ID", False, True, "Random"),
            ("Username", True, True, "None"),
            ("Display name", True, True, "None"),
            ("Password", True, True, "None"),
            ("Confirm password", True, True, "None"),
            ("Email", False, False, "No verification"),
            ("Phone", False, False, "No verification"),
            ("Agreement", False, False, "None"),
        )
    ]
    return {
        "organizations": [
            {
                "owner": "admin",
                "name": "hymio",
                "displayName": "Hymio",
                "passwordType": "bcrypt",
                "passwordOptions": ["AtLeast8"],
                "defaultTokenFormat": "JWT",
                "languages": ["en", "zh"],
                "isProfilePublic": False,
            }
        ],
        "applications": [
            {
                "owner": "admin",
                "name": "hymio",
                "displayName": "Hymio",
                "organization": "hymio",
                "cert": "hymio-signing",
                "enablePassword": True,
                "enableSignUp": True,
                "clientId": credentials["client_id"],
                "clientSecret": credentials["client_secret"],
                "signinMethods": [
                    {"name": "Password", "displayName": "Password", "rule": "All"}
                ],
                "signupItems": items,
                "grantTypes": ["authorization_code"],
                "redirectUris": ["http://localhost:8080/auth/callback"],
                "tokenFormat": "JWT-Standard",
                "expireInHours": 1,
            }
        ],
        "certs": [
            {
                "owner": "admin",
                "name": "hymio-signing",
                "displayName": "Hymio signing",
                "scope": "JWT",
                "type": "x509",
                "cryptoAlgorithm": "RS256",
                "bitSize": 2048,
                "expireInYears": 10,
            }
        ],
    }


def compose(runtime, settings, credentials):
    private_write(runtime / "casdoor-seed.json", json.dumps(seed(credentials)))
    spec = {
        "services": {
            "casdoor-permissions": {
                "image": "busybox:1.37.0",
                "command": [
                    "sh",
                    "-c",
                    "cp /seed.json /data/init_data.json && chown -R 1000:1000 /data && chmod 600 /data/init_data.json",
                ],
                "volumes": [
                    "casdoor-data:/data",
                    {
                        "type": "bind",
                        "source": str(runtime / "casdoor-seed.json"),
                        "target": "/seed.json",
                        "read_only": True,
                    },
                ],
            },
            "casdoor": {
                "image": "casbin/casdoor:4.20.0",
                "restart": "unless-stopped",
                "depends_on": {
                    "casdoor-permissions": {
                        "condition": "service_completed_successfully"
                    }
                },
                "ports": [f"127.0.0.1:{settings['casdoor_port']}:8000"],
                "environment": {
                    "driverName": "sqlite",
                    "dataSourceName": "file:/data/casdoor.db?cache=shared",
                    "dbName": "casdoor",
                    "origin": f"http://localhost:{settings['casdoor_port']}",
                    "initDataFile": "/data/init_data.json",
                    "initDataNewOnly": "true",
                    "initAdminPassword": credentials["admin_password"],
                },
                "volumes": ["casdoor-data:/data"],
            },
        },
        "volumes": {"casdoor-data": {}},
    }
    target = runtime / "casdoor-compose.json"
    private_write(target, json.dumps(spec))
    return target


def verify(issuer, credentials):
    params = urlencode(
        {
            "clientId": credentials["client_id"],
            "responseType": "code",
            "redirectUri": "http://localhost:8080/auth/callback",
            "scope": "openid profile",
            "type": "code",
            "state": "bootstrap-check",
            "nonce": "bootstrap-check",
            "code_challenge": "bootstrap-check",
            "code_challenge_method": "S256",
        }
    )
    with urlopen(issuer + "/api/get-app-login?" + params, timeout=10) as response:
        result = json.load(response)
    app = result.get("data") or {}
    if (
        result.get("status") != "ok"
        or app.get("organization") != "hymio"
        or app.get("clientId") != credentials["client_id"]
    ):
        raise RuntimeError(
            "Casdoor initialization did not produce the expected Hymio application; inspect its private runtime, do not delete the volume"
        )
