import base64
import logging
import re
import time
from contextvars import ContextVar
from urllib.parse import quote

import httpx

_log = logging.getLogger(__name__)
operation_context = ContextVar("media_operation_context", default={})


class ModelUnavailable(Exception):
    def __init__(self, message, *, code="media_unavailable"):
        super().__init__(message)
        self.code = code


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
        started = time.monotonic()
        credential_ms = None
        stage = "credential"
        try:
            key = self.key()
            credential_ms = round((time.monotonic() - started) * 1000, 3)
            stage = "provider"
            with httpx.Client(timeout=110, trust_env=False, follow_redirects=False) as client:
                response = client.post(
                    self.settings.media_api_base.rstrip("/") + path,
                    headers={"Authorization": "Bearer " + key},
                    json=payload,
                )
                response.raise_for_status()
                result = response.json()
            if not isinstance(result, dict) or not isinstance(result.get("base_resp", {}), dict):
                raise ModelUnavailable("Invalid media provider response", code="invalid_response")
            if result.get("base_resp", {}).get("status_code", 0) != 0:
                raise ModelUnavailable(
                    "Provider rejected the request; check model access or balance",
                    code="provider_rejected",
                )
            return result
        except ModelUnavailable:
            raise
        except httpx.HTTPStatusError as error:
            raise ModelUnavailable(
                "Media " + stage + " returned HTTP " + str(error.response.status_code),
                code=stage + "_http_" + str(error.response.status_code),
            ) from error
        except httpx.TimeoutException as error:
            raise ModelUnavailable(
                "Media " + stage + " timed out", code=stage + "_timeout"
            ) from error
        except (httpx.HTTPError, OSError, ValueError, KeyError) as error:
            raise ModelUnavailable(
                "Media model unavailable; do not automatically retry",
                code=stage + "_transport_or_response",
            ) from error
        finally:
            _log.info(
                "Media provider call finished",
                extra={
                    **operation_context.get(),
                    "media_operation": path,
                    "media_model": payload.get("model"),
                    "credential_ms": credential_ms,
                    "duration_ms": round((time.monotonic() - started) * 1000, 3),
                },
            )

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
                **(
                    {"thinking": {"type": "disabled"}}
                    if self.settings.vision_model == "MiniMax-M3"
                    else {}
                ),
            },
        )
        try:
            choice = response["choices"][0]
            content = choice["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise ModelUnavailable(
                "Provider returned malformed analysis", code="invalid_analysis_response"
            ) from error
        _log.info(
            "Media analysis response",
            extra={
                **operation_context.get(),
                "media_model": self.settings.vision_model,
                "finish_reason": choice.get("finish_reason"),
                "completion_tokens": (response.get("usage") or {}).get("completion_tokens"),
            },
        )
        if choice.get("finish_reason") == "length":
            raise ModelUnavailable(
                "Image analysis exceeded the output budget; no complete result was returned",
                code="analysis_output_limit",
            )
        if not isinstance(content, str):
            raise ModelUnavailable("Provider returned no textual analysis", code="empty_analysis")
        analysis = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
        if not analysis:
            raise ModelUnavailable(
                "Provider returned empty analysis; do not retry automatically",
                code="empty_analysis",
            )
        return analysis

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
