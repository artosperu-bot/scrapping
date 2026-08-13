from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlparse

import requests
from PIL import Image

from .models import ProductIdentity

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36"

_IMAGE_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/avif": ".avif",
    "image/gif": ".gif",
    "image/bmp": ".bmp",
    "image/tiff": ".tiff",
}
_VIDEO_EXTENSIONS = {
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "video/quicktime": ".mov",
}

MIN_IMAGE_WIDTH = 300
MIN_IMAGE_HEIGHT = 300
MIN_IMAGE_AREA = 120_000


def safe_product_key(identity: ProductIdentity) -> str:
    raw = next(
        (
            str(v).strip()
            for v in [identity.mpn, identity.ean, identity.upc, identity.gtin, identity.model, identity.product_name]
            if v and str(v).strip()
        ),
        "producto",
    )
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", raw).strip("._-")
    return cleaned[:120] or "producto"


def _target_dir(output_root: str | Path, identity: ProductIdentity, media_type: str) -> Path:
    bucket = "videos" if media_type == "video" else "fotos"
    path = Path(output_root) / "multimedia" / bucket / safe_product_key(identity)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _next_filename(directory: Path, extension: str) -> Path:
    nums = []
    for child in directory.iterdir():
        if not child.is_file():
            continue
        match = re.match(r"^(\d{2,})\.", child.name)
        if match:
            nums.append(int(match.group(1)))
    return directory / f"{(max(nums) + 1) if nums else 1:02d}{extension}"


def _extension_for(content_type: str, url: str, media_type: str) -> str | None:
    ctype = (content_type or "").split(";", 1)[0].strip().lower()
    table = _VIDEO_EXTENSIONS if media_type == "video" else _IMAGE_EXTENSIONS
    if ctype in table:
        return table[ctype]
    suffix = Path(urlparse(url).path).suffix.lower()
    allowed = set(table.values())
    if suffix == ".jpeg":
        suffix = ".jpg"
    return suffix if suffix in allowed else None


def _image_dimensions(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        image.load()
        return int(image.width), int(image.height)


def download_media_item(
    item: dict,
    identity: ProductIdentity,
    output_root: str | Path,
    *,
    session: requests.Session | None = None,
    timeout: int = 30,
) -> dict:
    result = dict(item)
    url = str(item.get("url") or "").strip()
    media_type = str(item.get("media_type") or "").lower()
    result.setdefault("downloaded", False)
    result.setdefault("metadata_only", False)

    if media_type not in {"image", "video"} or not url.startswith(("http://", "https://")):
        result["reason"] = "unsupported_media"
        return result

    provider = str(item.get("provider") or "").lower()
    if media_type == "video" and (provider in {"youtube", "vimeo"} or url.lower().endswith(".m3u8")):
        result["metadata_only"] = True
        result["reason"] = "hosted_video" if provider else "stream_playlist"
        return result

    client = session or requests.Session()
    temp_path: Path | None = None
    try:
        response = client.get(
            url,
            stream=True,
            timeout=timeout,
            allow_redirects=True,
            headers={"User-Agent": UA, "Accept": "image/avif,image/webp,image/*,video/*,*/*;q=0.5"},
        )
        response.raise_for_status()
        content_type = str(response.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
        expected_prefix = "video/" if media_type == "video" else "image/"
        if not content_type.startswith(expected_prefix):
            result.update({"content_type": content_type, "reason": "unexpected_content_type"})
            return result
        extension = _extension_for(content_type, url, media_type)
        if not extension:
            result.update({"content_type": content_type, "reason": "unsupported_content_type"})
            return result

        directory = _target_dir(output_root, identity, media_type)
        final_path = _next_filename(directory, extension)
        temp_path = final_path.with_suffix(final_path.suffix + ".part")
        digest = hashlib.sha256()
        total = 0
        with temp_path.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=65536):
                if not chunk:
                    continue
                handle.write(chunk)
                digest.update(chunk)
                total += len(chunk)
        if total == 0:
            temp_path.unlink(missing_ok=True)
            result["reason"] = "empty_response"
            return result

        dimensions: dict[str, int] = {}
        if media_type == "image":
            try:
                width, height = _image_dimensions(temp_path)
            except Exception as exc:
                temp_path.unlink(missing_ok=True)
                result.update({
                    "content_type": content_type,
                    "bytes": total,
                    "reason": "invalid_image",
                    "error": str(exc),
                })
                return result
            pixel_area = width * height
            dimensions = {"width": width, "height": height, "pixel_area": pixel_area}
            result.update(dimensions)
            if width < MIN_IMAGE_WIDTH or height < MIN_IMAGE_HEIGHT or pixel_area < MIN_IMAGE_AREA:
                temp_path.unlink(missing_ok=True)
                result.update({
                    "content_type": content_type,
                    "bytes": total,
                    "sha256": digest.hexdigest(),
                    "reason": "image_too_small",
                })
                return result

        temp_path.replace(final_path)
        result.update(
            {
                "downloaded": True,
                "metadata_only": False,
                "local_path": str(final_path),
                "content_type": content_type,
                "bytes": total,
                "sha256": digest.hexdigest(),
                **dimensions,
            }
        )
        return result
    except Exception as exc:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        result["reason"] = f"download_error:{type(exc).__name__}"
        result["error"] = str(exc)
        return result


def _dedupe_results(results: list[dict]) -> list[dict]:
    out: list[dict] = []
    seen_hashes: set[str] = set()
    seen_urls: set[str] = set()
    for row in results:
        sha = str(row.get("sha256") or "").strip()
        url = str(row.get("url") or "").strip()
        if sha and sha in seen_hashes:
            continue
        if not sha and url and url in seen_urls:
            continue
        if sha:
            seen_hashes.add(sha)
        if url:
            seen_urls.add(url)
        out.append(row)
    return out


def write_media_metadata(output_root: str | Path, identity: ProductIdentity, results: list[dict]) -> None:
    identity_dict = identity.model_dump()
    for media_type in ("image", "video"):
        rows = _dedupe_results([dict(x) for x in results if str(x.get("media_type") or "").lower() == media_type])
        directory = _target_dir(output_root, identity, media_type)
        payload = {
            "product": identity_dict,
            "media_type": media_type,
            "items": rows,
        }
        (directory / "metadata.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
