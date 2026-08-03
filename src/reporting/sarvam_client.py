"""Sarvam Chat Completions transport for the Phase 2 museum report."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional


class SarvamError(RuntimeError):
    pass


class SarvamAuthError(SarvamError):
    pass


class SarvamRateLimitError(SarvamError):
    def __init__(self, message: str, retry_after_seconds: Optional[float] = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class SarvamSchemaError(SarvamError):
    pass


class SarvamServerError(SarvamError):
    pass


@dataclass
class SarvamResponse:
    body: dict
    actual_model: str
    raw_text: str
    content: str = ""


def _retry_after(value: Optional[str]) -> Optional[float]:
    try:
        return float(value) if value else None
    except ValueError:
        return None


def chat(
    *,
    api_key: str,
    model: str,
    system_prompt: str,
    user_payload: dict,
    timeout_seconds: float = 60.0,
    base_url: str = "https://api.sarvam.ai/v1/chat/completions",
    response_schema: Optional[dict] = None,
) -> SarvamResponse:
    if not api_key:
        raise SarvamAuthError("SARVAM_API_KEY is empty")
    schema_instruction = ""
    if response_schema is not None:
        schema_instruction = "\n\nYour response must match this JSON Schema exactly:\n" + json.dumps(
            response_schema, ensure_ascii=False
        )
    request = urllib.request.Request(
        base_url,
        data=json.dumps(
            {
                "model": model,
                "temperature": 0.0,
                "reasoning_effort": None,
                "max_tokens": 4096,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system_prompt + schema_instruction},
                    {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
                ],
            },
            ensure_ascii=False,
        ).encode("utf-8"),
        method="POST",
        headers={
            "api-subscription-key": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8")
            status = response.status
    except urllib.error.HTTPError as error:
        try:
            detail = error.read().decode("utf-8").strip()
        except OSError:
            detail = ""
        suffix = f": {detail[:500]}" if detail else ""
        if error.code in (401, 403):
            raise SarvamAuthError(f"Sarvam authentication failed: HTTP {error.code}{suffix}") from error
        if error.code == 429:
            raise SarvamRateLimitError(
                "Sarvam rate-limited the request", retry_after_seconds=_retry_after(error.headers.get("Retry-After"))
            ) from error
        if 500 <= error.code < 600:
            raise SarvamServerError(f"Sarvam server error: HTTP {error.code}{suffix}") from error
        raise SarvamError(f"Sarvam HTTP {error.code}: {error.reason}{suffix}") from error
    except urllib.error.URLError as error:
        raise SarvamServerError(f"Sarvam network error: {error.reason}") from error
    if status >= 400:
        raise SarvamError(f"Sarvam HTTP {status}: {raw[:200]}")
    try:
        parsed = json.loads(raw)
        content = parsed["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as error:
        raise SarvamSchemaError("Sarvam response is missing chat content") from error
    if not isinstance(content, str) or not content.strip():
        raise SarvamSchemaError("Sarvam response has empty chat content")
    try:
        body = json.loads(content)
    except json.JSONDecodeError as error:
        raise SarvamSchemaError("Sarvam did not return a JSON object in content") from error
    if not isinstance(body, dict):
        raise SarvamSchemaError("Sarvam content is not a JSON object")
    return SarvamResponse(body=body, actual_model=str(parsed.get("model") or model), raw_text=raw, content=content)


def get_api_key(env: Optional[dict] = None) -> str:
    return (env if env is not None else os.environ).get("SARVAM_API_KEY", "").strip()
