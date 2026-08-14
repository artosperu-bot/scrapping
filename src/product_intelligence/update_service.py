from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

REPO = "artosperu-bot/scrapping"
LATEST_RELEASE_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
ZIP_NAME = "ProductIntelligence-Windows.zip"
SHA_NAME = "ProductIntelligence-Windows.sha256"


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    zip_url: str
    sha256_url: str
    notes: str
    page_url: str


def _parts(version: str) -> tuple[int, int, int]:
    clean = str(version or "").strip().lower().lstrip("v")
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", clean)
    if not match:
        raise ValueError(f"Invalid version: {version}")
    return tuple(int(x) for x in match.groups())


def is_newer_version(candidate: str, current: str) -> bool:
    return _parts(candidate) > _parts(current)


class UpdateService:
    def __init__(self, *, current_version: str, session=None, timeout: int = 20):
        self.current_version = current_version
        self.session = session or requests
        self.timeout = int(timeout)

    def check_latest(self) -> ReleaseInfo | None:
        response = self.session.get(
            LATEST_RELEASE_URL,
            timeout=self.timeout,
            headers={"Accept": "application/vnd.github+json", "User-Agent": "ProductIntelligence-Updater"},
        )
        response.raise_for_status()
        payload: dict[str, Any] = response.json() or {}
        if payload.get("draft") or payload.get("prerelease"):
            return None
        version = str(payload.get("tag_name") or "").lstrip("v")
        try:
            if not is_newer_version(version, self.current_version):
                return None
        except ValueError:
            return None
        assets = {str(a.get("name")): str(a.get("browser_download_url")) for a in payload.get("assets") or []}
        if not assets.get(ZIP_NAME) or not assets.get(SHA_NAME):
            return None
        return ReleaseInfo(
            version=version,
            zip_url=assets[ZIP_NAME],
            sha256_url=assets[SHA_NAME],
            notes=str(payload.get("body") or ""),
            page_url=str(payload.get("html_url") or ""),
        )

    def download_verified(self, release: ReleaseInfo, destination_dir: Path) -> Path:
        destination_dir = Path(destination_dir)
        destination_dir.mkdir(parents=True, exist_ok=True)
        zip_response = self.session.get(release.zip_url, timeout=self.timeout)
        zip_response.raise_for_status()
        sha_response = self.session.get(release.sha256_url, timeout=self.timeout)
        sha_response.raise_for_status()
        data = bytes(zip_response.content)
        expected = str(sha_response.text or "").strip().split()[0].lower()
        actual = hashlib.sha256(data).hexdigest().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", expected) or expected != actual:
            raise ValueError("SHA256 verification failed")
        path = destination_dir / ZIP_NAME
        path.write_bytes(data)
        return path
