from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

MATERIAL_TYPES = {"PRODUCT", "PRODUCT_VARIANT", "DOCUMENT", "SUPPORT_PRODUCT"}


@dataclass(frozen=True)
class PageSignals:
    url: str
    content_type: str = ""
    title: str = ""
    h1: str = ""
    schema_types: tuple[str, ...] = ()
    product_entity_count: int = 0
    product_card_count: int = 0
    specification_block_count: int = 0
    download_link_count: int = 0
    update_signal: bool = False
    legal_signal: bool = False
    account_signal: bool = False
    search_signal: bool = False
    generic_support_signal: bool = False


@dataclass(frozen=True)
class PageTypeAssessment:
    page_type: str
    confidence: float
    reasons: tuple[str, ...]
    material_allowed: bool


def _assessment(page_type: str, confidence: float, *reasons: str) -> PageTypeAssessment:
    return PageTypeAssessment(
        page_type=page_type,
        confidence=max(0.0, min(1.0, confidence)),
        reasons=tuple(reasons),
        material_allowed=page_type in MATERIAL_TYPES,
    )


def classify_page_type(signals: PageSignals) -> PageTypeAssessment:
    """Classify a candidate page before any material product evidence is admitted.

    The classifier is deliberately conservative: ambiguous pages are UNKNOWN and therefore
    non-material. Discovery/navigation may still use them elsewhere in the pipeline.
    """
    url = (signals.url or "").lower()
    path = (urlparse(signals.url or "").path or "").lower()
    ctype = (signals.content_type or "").lower()
    title_h1 = f"{signals.title} {signals.h1}".lower()
    schema = {str(x).lower() for x in signals.schema_types}

    if "application/pdf" in ctype or path.endswith(".pdf"):
        return _assessment("DOCUMENT", 0.99, "PDF_MIME_OR_PATH")

    if signals.legal_signal or any(token in path for token in ("/privacy", "/terms", "/cookies", "/legal")):
        return _assessment("LEGAL", 0.98, "LEGAL_SIGNAL")
    if signals.account_signal or any(token in path for token in ("/account", "/login", "/signin", "/register")):
        return _assessment("ACCOUNT", 0.98, "ACCOUNT_SIGNAL")
    if signals.update_signal or any(token in title_h1 for token in ("software update", "firmware update", "notify update", "release notes")):
        return _assessment("UPDATE", 0.96, "UPDATE_SIGNAL")
    if signals.search_signal or "/search" in path or "search results" in title_h1:
        return _assessment("SEARCH_RESULTS", 0.94, "SEARCH_SIGNAL")

    many_products = signals.product_card_count >= 3 or signals.product_entity_count >= 3
    if "itemlist" in schema or many_products:
        return _assessment("CATEGORY", 0.94 if many_products else 0.88, "MULTI_PRODUCT_OR_ITEMLIST")

    single_product = "product" in schema and signals.product_entity_count <= 1
    has_product_detail = signals.specification_block_count > 0 or signals.download_link_count > 0
    support_path = any(token in path for token in ("/support", "/downloads", "/manual", "/product-support"))

    if signals.generic_support_signal and not (single_product and has_product_detail):
        return _assessment("GENERIC_SUPPORT", 0.90, "GENERIC_SUPPORT_SIGNAL")

    if support_path and single_product and has_product_detail:
        return _assessment("SUPPORT_PRODUCT", 0.91, "SINGLE_PRODUCT_SUPPORT_WITH_DETAILS")

    if single_product and has_product_detail:
        return _assessment("PRODUCT", 0.95, "SINGLE_SCHEMA_PRODUCT_WITH_DETAILS")

    if single_product and (signals.title.strip() or signals.h1.strip()):
        return _assessment("PRODUCT", 0.84, "SINGLE_SCHEMA_PRODUCT")

    # Product-like URL plus explicit detail block is useful, but intentionally lower confidence
    # than structured Product markup.
    if signals.specification_block_count > 0 and any(token in path for token in ("/product", "/products/", "/p/", "/item/")):
        return _assessment("PRODUCT", 0.76, "PRODUCT_PATH_WITH_SPECIFICATIONS")

    return _assessment("UNKNOWN", 0.35, "INSUFFICIENT_PAGE_TYPE_SIGNALS")
