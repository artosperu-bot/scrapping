from __future__ import annotations

import re
from dataclasses import dataclass
from html import unescape

from .normalize import key_norm


EXTRACTION_ORDER = [
    "structured_data",      # JSON-LD / microdata / OpenGraph / embedded product metadata
    "embedded_state",       # source HTML / hidden JSON / data-* already delivered with the page
    "static_html",          # tables, definition lists and visible static text
    "rendered_dom",         # Playwright only when static delivery is insufficient
    "same_site_json",       # XHR/fetch captured from the validated same-site product page
    "official_pdf",         # manuals, datasheets and official support PDFs
    "text_fallback",        # conservative free-text extraction
]


@dataclass(frozen=True)
class BrowserDecision:
    needed: bool
    reason: str
    target_hits: int
    target_total: int


def extraction_plan() -> list[str]:
    return list(EXTRACTION_ORDER)


def _plain_html_text(html: str) -> str:
    text = re.sub(r"<script\b[^>]*>.*?</script>", " ", html or "", flags=re.I | re.S)
    text = re.sub(r"<style\b[^>]*>.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return key_norm(unescape(re.sub(r"\s+", " ", text)))


def _target_phrase(value: str) -> str:
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(value or ""))
    return key_norm(value.replace("_", " ").replace("-", " "))


def browser_decision(html: str, target_semantics: list[str] | None, media_slots: int = 0) -> BrowserDecision:
    """Decide whether rendering JS is worth the extra cost.

    Static delivery is preferred. Chromium is requested only when the workbook asks for a
    gallery or when too few requested attribute labels are observable in the static page.
    The heuristic is deliberately generic: it consumes the template's arbitrary semantics
    instead of category-specific attribute names.
    """
    targets = [p for p in (_target_phrase(x) for x in (target_semantics or [])) if len(p) >= 3]
    text = _plain_html_text(html)
    hits = sum(1 for target in targets if target in text)

    if int(media_slots or 0) > 1:
        return BrowserDecision(True, "gallery_requested", hits, len(targets))
    if not targets:
        return BrowserDecision(False, "no_dynamic_need_detected", hits, 0)

    # If the static page visibly exposes at least 40% of requested labels (minimum 3 for a
    # larger contract), continue without Chromium. Otherwise a rendered pass may reveal
    # accordion/specification content populated by JavaScript.
    required_hits = min(len(targets), max(2, int(round(len(targets) * 0.40))))
    if hits < required_hits:
        return BrowserDecision(True, "static_target_coverage_low", hits, len(targets))
    return BrowserDecision(False, "static_target_coverage_sufficient", hits, len(targets))
