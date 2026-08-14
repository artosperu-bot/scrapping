from __future__ import annotations

from typing import Callable

import requests


class OCRSpaceClient:
    """Small OCR.space adapter. Network is only used when extract() is invoked."""

    endpoint = "https://api.ocr.space/parse/image"

    def __init__(self, api_key_getter: Callable[[], str | None], session=None):
        self.api_key_getter = api_key_getter
        self.session = session or requests

    def extract(self, image_bytes: bytes, *, language: str = "eng", timeout: int = 20) -> str:
        key = (self.api_key_getter() or "").strip()
        if not key:
            return ""
        response = self.session.post(
            self.endpoint,
            headers={"apikey": key},
            files={"file": ("page.png", image_bytes, "image/png")},
            data={"language": language or "eng", "isOverlayRequired": "false"},
            timeout=int(timeout),
        )
        response.raise_for_status()
        payload = response.json()
        if bool(payload.get("IsErroredOnProcessing")):
            return ""
        chunks = []
        for row in payload.get("ParsedResults") or []:
            text = str((row or {}).get("ParsedText") or "").strip()
            if text:
                chunks.append(text)
        return "\n".join(chunks).strip()
