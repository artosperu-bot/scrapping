from __future__ import annotations

import html as htmlmod
import json
import re
from typing import Any

from bs4 import BeautifulSoup

from .models import Evidence, ProductIdentity
from .structured_extract import flatten_pairs

# Raw-source extraction is intentionally used only AFTER the product page has passed
# the normal identity gate in pipeline.py.  It is the programmatic equivalent of
# opening view-source: and using Ctrl+F, but it never treats a search/query echo as
# product identity.

_GENERIC_KEYS = {
    "id", "url", "href", "src", "class", "style", "type", "name", "value",
    "key", "title", "text", "content", "html", "index", "position", "event",
    "action", "category", "currency", "locale", "language", "country", "site",
}
_TRACKING_HINTS = (
    "analytics", "tracking", "cookie", "consent", "gtm", "google", "facebook",
    "pixel", "session", "csrf", "token", "campaign", "utm_", "checkout", "cart",
)
_LABEL_KEYS = {"label", "displayname", "display_name", "specification", "attribute", "feature", "key", "name"}
_VALUE_KEYS = {"value", "displayvalue", "display_value", "specvalue", "spec_value", "content", "text"}


def _clean_scalar(value: Any) -> str:
    s = htmlmod.unescape(str(value or "")).strip()
    s = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), s)
    s = s.replace("\\/", "/").replace("\\n", " ").replace("\\r", " ").replace("\\t", " ")
    s = re.sub(r"\s+", " ", s).strip(" \t\r\n\"'")
    return s


def _reasonable_label(label: str) -> bool:
    if not (2 <= len(label) <= 100):
        return False
    low = label.lower().strip()
    if low in _GENERIC_KEYS or any(x in low for x in _TRACKING_HINTS):
        return False
    if re.fullmatch(r"[a-f0-9_-]{18,}", low):
        return False
    return bool(re.search(r"[a-zA-ZÀ-ÿ]", label))


def _reasonable_value(value: str) -> bool:
    if not value or len(value) > 500:
        return False
    low = value.lower()
    if low.startswith(("http://", "https://", "data:image/")):
        return False
    if "<script" in low or "function(" in low or "=>" in value:
        return False
    return True


def _emit(out: list[Evidence], seen: set[tuple[str, str]], label: Any, value: Any,
          source_url: str, match_level: str, confidence: float, selector: str) -> None:
    l = _clean_scalar(label)
    v = _clean_scalar(value)
    if not _reasonable_label(l) or not _reasonable_value(v) or l.lower() == v.lower():
        return
    key = (l.lower(), v.lower())
    if key in seen:
        return
    seen.add(key)
    out.append(Evidence(
        attribute=l,
        raw_value=v,
        normalized_value=v,
        source_url=source_url,
        source_type="official_source_html",
        selector=selector,
        match_level=match_level,
        confidence=confidence,
    ))


def _walk_objects(obj: Any):
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from _walk_objects(value)
    elif isinstance(obj, list):
        for value in obj[:200]:
            yield from _walk_objects(value)


def _json_object_pairs(obj: Any, out: list[Evidence], seen: set[tuple[str, str]],
                       source_url: str, match_level: str, confidence: float, selector: str) -> None:
    # First recover explicit {label/name: ..., value: ...} structures.  This is the
    # source-code equivalent of finding a spec label with Ctrl+F and reading its value.
    for d in _walk_objects(obj):
        normalized = {str(k).lower().replace("-", "_"): v for k, v in d.items()}
        label = next((normalized[k] for k in normalized if k.replace("_", "") in _LABEL_KEYS and isinstance(normalized[k], (str, int, float, bool))), None)
        value = next((normalized[k] for k in normalized if k.replace("_", "") in _VALUE_KEYS and isinstance(normalized[k], (str, int, float, bool))), None)
        if label is not None and value is not None:
            _emit(out, seen, label, value, source_url, match_level, min(.96, confidence + .04), selector)

    # Then expose ordinary scalar JSON leaves.  Keeping the full leaf key gives the
    # resolver a chance to match template fields without hard-coding a brand/category.
    for path, value in flatten_pairs(obj, max_depth=7):
        leaf = path.split(".")[-1]
        _emit(out, seen, leaf, value, source_url, match_level, confidence, f"{selector}:{path}")


def source_evidence(html: str, source_url: str, expected: ProductIdentity,
                    match_level: str, base_confidence: float = .90) -> list[Evidence]:
    """Mine a validated page's raw HTML/source for hidden specification pairs.

    Safety/quality rules:
    - caller must already have validated the product identity;
    - source query parameters are never used as identity proof;
    - scripts are parsed as JSON where possible, then conservative label/value regexes
      are applied to the raw source;
    - duplicates and obvious tracking/navigation values are discarded.
    """
    if not html:
        return []

    out: list[Evidence] = []
    seen: set[tuple[str, str]] = set()
    soup = BeautifulSoup(html, "lxml")

    # 1) Any JSON-bearing script, not just JSON-LD/extruct-supported metadata.
    for idx, script in enumerate(soup.find_all("script")):
        raw = (script.string or script.get_text("", strip=False) or "").strip()
        if not raw or len(raw) > 2_500_000:
            continue
        stype = (script.get("type") or "").lower()
        candidates: list[str] = []
        if "json" in stype or raw[:1] in "[{":
            candidates.append(raw)
        # Common storefront pattern: window.__STATE__ = {...};
        m = re.search(r"(?:window\.)?[A-Za-z0-9_$.[\]-]+\s*=\s*([\[{].*[\]}])\s*;?\s*$", raw, re.S)
        if m and len(m.group(1)) <= 2_500_000:
            candidates.append(m.group(1))
        for candidate in candidates[:2]:
            try:
                obj = json.loads(candidate)
            except Exception:
                continue
            _json_object_pairs(obj, out, seen, source_url, match_level, base_confidence, f"source:script[{idx}]")

    # 2) data-* attributes frequently carry values that are not rendered as text.
    for tag in soup.find_all(True):
        attrs = getattr(tag, "attrs", {}) or {}
        data_items = [(k[5:], v) for k, v in attrs.items() if str(k).lower().startswith("data-")]
        if len(data_items) < 1:
            continue
        label = None
        value = None
        for k, v in data_items:
            nk = str(k).lower().replace("-", "_")
            scalar = v if isinstance(v, (str, int, float, bool)) else None
            if scalar is None:
                continue
            if nk.replace("_", "") in _LABEL_KEYS:
                label = scalar
            elif nk.replace("_", "") in _VALUE_KEYS:
                value = scalar
        if label is not None and value is not None:
            _emit(out, seen, label, value, source_url, match_level, base_confidence - .04, "source:data-attrs")

    # 3) Conservative JSON-like label/value objects even when the surrounding script
    # is not valid JSON (single snippets inside large JS bundles/config blocks).
    decoded = htmlmod.unescape(html)
    pair_patterns = [
        re.compile(r'["\'](?:label|displayName|display_name|specification|attribute|feature)["\']\s*:\s*["\']([^"\']{2,100})["\']\s*,.{0,600}?["\'](?:value|displayValue|display_value|specValue|spec_value)["\']\s*:\s*["\']([^"\']{1,500})["\']', re.I | re.S),
        re.compile(r'["\'](?:value|displayValue|display_value|specValue|spec_value)["\']\s*:\s*["\']([^"\']{1,500})["\']\s*,.{0,600}?["\'](?:label|displayName|display_name|specification|attribute|feature)["\']\s*:\s*["\']([^"\']{2,100})["\']', re.I | re.S),
    ]
    for pidx, pattern in enumerate(pair_patterns):
        for match in pattern.finditer(decoded):
            if pidx == 0:
                label, value = match.group(1), match.group(2)
            else:
                value, label = match.group(1), match.group(2)
            _emit(out, seen, label, value, source_url, match_level, base_confidence - .06, f"source:regex[{pidx}]")
            if len(out) >= 1200:
                break

    return out[:1200]
