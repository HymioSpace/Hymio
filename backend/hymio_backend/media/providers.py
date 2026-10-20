import base64
import re
from urllib.parse import quote

import httpx


class ModelUnavailable(Exception):
    pass


class MiniMaxMedia:
    def __init__(self, settings):
        self.settings = settings

    def key(self):
        config = self.settings
        if (
            not config.media_credential
            or not config.vault_role_id_file
            or not config.vault_secret_id_file
        ):
            raise ModelUnavailable("Media model credential is not configured")
        if not re.fullmatch(r"[A-Za-z0-9_/-]+", config.media_credential):
            raise ModelUnavailable("Invalid credential alias")
        with httpx.Client(timeout=5, trust_env=False) as client:
            auth = client.post(
                config.vault_url.rstrip("/") + "/v1/auth/approle/login",
                json={
                    "role_id": config.vault_role_id_file.read_text().strip(),
                    "secret_id": config.vault_secret_id_file.read_text().strip(),
                },
            )
            auth.raise_for_status()
            response = client.get(
                config.vault_url.rstrip("/")
                + "/v1/oath/data/"
                + quote(config.media_credential, safe="/"),
                headers={"X-Vault-Token": auth.json()["auth"]["client_token"]},
            )
            response.raise_for_status()
            return response.json()["data"]["data"]["value"]

    def call(self, path, payload):
        try:
            key = self.key()
            with httpx.Client(timeout=110, trust_env=False, follow_redirects=False) as client:
                response = client.post(
                    self.settings.media_api_base.rstrip("/") + path,
                    headers={"Authorization": "Bearer " + key},
                    json=payload,
                )
                response.raise_for_status()
                result = response.json()
            if result.get("base_resp", {}).get("status_code", 0) != 0:
                raise ModelUnavailable(
                    "Provider rejected the request; check model access or balance"
                )
            return result
        except ModelUnavailable:
            raise
        except (httpx.HTTPError, OSError, ValueError, KeyError) as error:
            raise ModelUnavailable("Media model unavailable; do not automatically retry") from error

    @staticmethod
    def image(row):
        return "data:" + row["mime"] + ";base64," + base64.b64encode(row["content"]).decode()

    def understand(self, rows, question):
        content = [{"type": "text", "text": question}]
        content += [{"type": "image_url", "image_url": {"url": self.image(row)}} for row in rows]
        response = self.call(
            "/chat/completions",
            {
                "model": self.settings.vision_model,
                "messages": [{"role": "user", "content": content}],
                "max_tokens": 4096,
                "stream": False,
            },
        )
        content = response["choices"][0]["message"]["content"]
        if not isinstance(content, str):
            raise ModelUnavailable("Provider returned no textual analysis")
        return re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()

    def transcribe(self, row):
        try:
            key = self.key()
            with httpx.Client(timeout=110, trust_env=False) as client:
                response = client.post(
                    self.settings.media_api_base.rstrip("/") + "/speech_to_text",
                    headers={"Authorization": "Bearer " + key},
                    data={"model": "asr-1.0", "response_format": "json"},
                    files={"file": (row["name"], row["content"], row["mime"])},
                )
                response.raise_for_status()
                return response.json()["text"][:160000]
        except (httpx.HTTPError, KeyError, ValueError, OSError) as error:
            raise ModelUnavailable("Audio transcription unavailable; do not retry") from error

    def generate(self, prompt, ratio, reference=None):
        payload = {
            "model": "image-01",
            "prompt": prompt,
            "aspect_ratio": ratio,
            "n": 1,
            "response_format": "base64",
        }
        if reference:
            payload["subject_reference"] = [
                {"type": "character", "image_file": self.image(reference)}
            ]
        result = self.call("/image_generation", payload)
        values = result.get("data", {}).get("image_base64", [])
        if not values:
            raise ModelUnavailable("Provider returned no image")
        return base64.b64decode(values[0].split(",")[-1], validate=True)
