from __future__ import annotations

import json
from typing import Any, Callable, Protocol

import requests


class MistralTransport(Protocol):
    def generate(self, payload: dict[str, Any], *, model: str, timeout: int) -> str:
        ...


class MistralClient:
    """Minimal authenticated Mistral chat-completion transport.

    Credentials are resolved lazily from the supplied getter, so no API key is
    copied into settings, snapshots, prompts, logs, or audit events. Network is
    used only when generate() is invoked by the optional description narrator.
    """

    endpoint = "https://api.mistral.ai/v1/chat/completions"

    def __init__(self, api_key_getter: Callable[[], str | None], session=None):
        self.api_key_getter = api_key_getter
        self.session = session or requests

    @staticmethod
    def _message_content(payload: dict[str, Any]) -> str:
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _extract_text(response_payload: dict[str, Any]) -> str:
        choices = response_payload.get("choices") or []
        if not choices:
            return ""
        message = (choices[0] or {}).get("message") or {}
        content = message.get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            chunks: list[str] = []
            for item in content:
                if not isinstance(item, dict):
                    continue
                text = item.get("text")
                if text not in (None, ""):
                    chunks.append(str(text).strip())
            return "\n".join(chunk for chunk in chunks if chunk).strip()
        return ""

    def generate(self, payload: dict[str, Any], *, model: str, timeout: int) -> str:
        key = (self.api_key_getter() or "").strip()
        if not key:
            raise RuntimeError("Mistral credential not configured")

        response = self.session.post(
            self.endpoint,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model or "mistral-small-latest",
                "messages": [
                    {
                        "role": "user",
                        "content": self._message_content(payload),
                    }
                ],
                "temperature": 0,
            },
            timeout=int(timeout),
        )
        response.raise_for_status()
        text = self._extract_text(response.json())
        if not text:
            raise RuntimeError("Mistral returned an empty response")
        return text
