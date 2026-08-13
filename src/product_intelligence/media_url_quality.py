from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Common image-CDN resize/crop parameters. Removing only these parameters keeps
# the exact same asset path/product identity while asking the CDN for the
# unconstrained rendition. Formatting/quality parameters are preserved.
_RESIZE_KEYS = {
    "sw", "sh", "sm", "w", "h", "width", "height",
    "resize", "crop", "fit", "maxw", "maxh", "mw", "mh",
}


def promote_image_url(url: str) -> str:
    """Remove explicit thumbnail-size transforms without changing the asset path.

    This is intentionally host-agnostic: Demandware/SFCC and many image CDNs use
    query parameters to derive thumbnails from the original image. The returned
    URL points to the same path, so it cannot switch to another product; the
    downloaded file is still validated by the physical dimension filter.
    """
    raw = str(url or "").strip()
    if not raw.startswith(("http://", "https://")):
        return raw
    parts = urlsplit(raw)
    pairs = parse_qsl(parts.query, keep_blank_values=True)
    if not pairs:
        return raw
    kept = [(k, v) for k, v in pairs if k.lower() not in _RESIZE_KEYS]
    if len(kept) == len(pairs):
        return raw
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(kept, doseq=True), parts.fragment))
