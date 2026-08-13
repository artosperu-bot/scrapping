from __future__ import annotations

import re
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from .discovery import search_web
from .media_discovery import discover_media
from .media_downloader import download_media_item, write_media_metadata
from .media_url_quality import promote_image_url
from .models import ProductIdentity
from .web_fetch import fetch_page

MediaEventCallback = Callable[[dict], None]


def _norm(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def _page_matches_identity(html: str, url: str, identity: ProductIdentity) -> bool:
    hay = _norm(f"{url} {html[:500000]}")
    strong = [identity.mpn, identity.ean, identity.upc, identity.gtin]
    for value in strong:
        needle = _norm(value)
        if needle and needle in hay:
            return True

    brand = _norm(identity.brand)
    descriptive = identity.model or identity.product_name
    model_tokens = [
        _norm(token)
        for token in re.split(r"[^A-Za-z0-9]+", descriptive or "")
        if len(token) >= 3
    ]
    model_hits = sum(1 for token in model_tokens if token and token in hay)
    model_ok = bool(model_tokens) and model_hits >= max(1, len(model_tokens) - 1)
    brand_ok = not brand or brand in hay
    return model_ok and brand_ok


def _is_official_product_page(url: str, identity: ProductIdentity, discovery_source: str) -> bool:
    """Identify manufacturer/brand PDPs without a hardcoded domain allowlist."""
    if discovery_source == "official_search":
        return True
    host = _norm(urlparse(url).hostname or "")
    brand = _norm(identity.brand or identity.manufacturer)
    return bool(brand and len(brand) >= 2 and brand in host)


def _candidate_urls(identity: ProductIdentity, manual_urls: list[str], auto_search: bool, max_pages: int) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    seen: set[str] = set()

    for url in manual_urls:
        value = str(url or "").strip()
        if value.startswith(("http://", "https://")) and value not in seen:
            seen.add(value)
            out.append((value, "manual"))

    if auto_search:
        for candidate in search_web(identity, limit=max_pages):
            value = str(getattr(candidate, "url", "") or "").strip()
            if not value or value in seen:
                continue
            seen.add(value)
            source = "official_search" if getattr(candidate, "likely_official", False) else "web_search"
            out.append((value, source))
    return out[:max_pages]


def _looks_like_official_catalog_asset(row: dict) -> bool:
    """Recognize product-catalog assets from validated manufacturer PDPs.

    Some Salesforce Commerce Cloud/Demandware storefronts expose product gallery
    images through master-catalog URLs without useful DOM gallery classes or alt
    text. This deliberately does not match generic CDN/page assets.
    """
    hay = " ".join(
        str(row.get(key) or "")
        for key in ("url", "source", "alt")
    ).lower()
    return bool(
        re.search(
            r"sites[-_/ ]mastercatalog|sites[-_/ ]master[-_/ ]catalog|demandware\.static.*master|/mastercatalog/|/master[-_/]catalog/",
            hay,
            re.I,
        )
    )


def _eligible_media(row: dict, *, official_page: bool = False) -> bool:
    """Apply stricter confidence off-site while preserving validated official galleries."""
    media_type = str(row.get("media_type") or "").lower()
    if media_type not in {"image", "video"}:
        return False
    if row.get("conflict_reasons"):
        return False
    role = str(row.get("role") or "")
    if role in {"page_asset", "related_product"}:
        return False
    scope = str(row.get("scope") or "")
    if scope not in {"EXACT_VARIANT", "EXACT_PRODUCT", "PRODUCT_FAMILY"}:
        return False
    confidence = float(row.get("confidence") or 0.0)

    if official_page and role in {"product_gallery", "product_video"}:
        return confidence >= 0.84

    if (
        official_page
        and media_type == "image"
        and role == "unknown_image"
        and _looks_like_official_catalog_asset(row)
    ):
        return confidence >= 0.84

    return confidence >= 0.95


def run_media_product(
    identity: ProductIdentity,
    output_root: str | Path,
    manual_urls: list[str] | None = None,
    *,
    auto_search: bool = True,
    max_pages: int = 8,
    on_event: MediaEventCallback | None = None,
) -> list[dict]:
    def emit(event_type: str, **payload):
        if on_event:
            on_event({"type": event_type, "identity": identity.model_dump(), **payload})

    manual_urls = list(manual_urls or [])
    urls = _candidate_urls(identity, manual_urls, auto_search, max_pages)
    results: list[dict] = []
    seen_media_urls: set[str] = set()
    relaxed_identity = identity.model_copy(update={"color": None})

    emit("status", message=f"Fuentes candidatas: {len(urls)}")
    for page_url, discovery_source in urls:
        try:
            emit("page", url=page_url, source=discovery_source, status="fetching")
            fetched = fetch_page(
                page_url,
                timeout=30,
                browser_fallback=True,
                prefer_browser=True,
                activate_lazy_media=True,
            )
            final_url = str(getattr(fetched, "final_url", None) or page_url)
            html = str(getattr(fetched, "html", "") or "")
            if not _page_matches_identity(html, final_url, relaxed_identity):
                emit("page", url=final_url, source=discovery_source, status="rejected_identity")
                continue

            official_page = _is_official_product_page(final_url, relaxed_identity, discovery_source)
            emit("page", url=final_url, source=discovery_source, status="validated", official_page=official_page)
            discovered = discover_media(
                html,
                final_url,
                relaxed_identity,
                network_resources=list(getattr(fetched, "network_resources", []) or []),
                page_is_validated=True,
            )
            for item in discovered:
                original_url = str(item.get("url") or "").strip()
                if not original_url:
                    continue
                if not _eligible_media(item, official_page=official_page):
                    emit(
                        "media_filtered",
                        url=original_url,
                        role=item.get("role"),
                        scope=item.get("scope"),
                        confidence=item.get("confidence"),
                        source=item.get("source"),
                    )
                    continue

                media_url = promote_image_url(original_url) if str(item.get("media_type") or "").lower() == "image" else original_url
                if not media_url or media_url in seen_media_urls:
                    continue
                seen_media_urls.add(media_url)
                enriched = {
                    **item,
                    "url": media_url,
                    "original_media_url": original_url if media_url != original_url else None,
                    "page_url": final_url,
                    "page_discovery_source": discovery_source,
                    "official_page": official_page,
                    "fetch_method": getattr(fetched, "method", None),
                }
                saved = download_media_item(enriched, identity, output_root)
                if saved.get("downloaded") or saved.get("metadata_only"):
                    results.append(saved)
                    emit("media", item=saved)
                else:
                    emit(
                        "media_rejected",
                        url=media_url,
                        reason=str(saved.get("reason") or "not_saved"),
                        item=saved,
                    )
        except Exception as exc:
            emit("error", url=page_url, error=f"{type(exc).__name__}: {exc}")

    write_media_metadata(output_root, identity, results)
    emit(
        "done",
        downloaded=sum(1 for row in results if row.get("downloaded")),
        metadata_only=sum(1 for row in results if row.get("metadata_only")),
        total=len(results),
    )
    return results
