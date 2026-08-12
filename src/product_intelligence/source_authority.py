from __future__ import annotations

from .models import Evidence
from .normalize import key_norm

# Source authority is about fitness for a fact, not about product/category hardcoding.
# Unknown attributes fall back to the generic hierarchy.
FIELD_SOURCE_ORDER: dict[str, tuple[str, ...]] = {
    "gtin": ("manufacturer", "official_pdf", "structured_catalog", "distributor", "secondary", "marketplace"),
    "ean": ("manufacturer", "official_pdf", "structured_catalog", "distributor", "secondary", "marketplace"),
    "upc": ("manufacturer", "official_pdf", "structured_catalog", "distributor", "secondary", "marketplace"),
    "bluetooth": ("manufacturer", "official_pdf", "regulatory", "technical_catalog", "secondary", "marketplace"),
    "battery_life": ("manufacturer", "official_pdf", "technical_catalog", "secondary", "marketplace"),
    "package_width": ("official_pdf", "manufacturer", "distributor", "secondary", "marketplace"),
    "package_length": ("official_pdf", "manufacturer", "distributor", "secondary", "marketplace"),
    "package_height": ("official_pdf", "manufacturer", "distributor", "secondary", "marketplace"),
    "package_weight": ("official_pdf", "manufacturer", "distributor", "secondary", "marketplace"),
    "warranty": ("manufacturer", "official_pdf", "distributor", "secondary", "marketplace"),
}

GENERIC_ORDER = ("manufacturer", "official_pdf", "regulatory", "structured_catalog", "distributor", "secondary", "marketplace", "unknown")

SOURCE_CAPS = {
    "manufacturer": 1.00,
    "official_pdf": .98,
    "regulatory": .96,
    "structured_catalog": .93,
    "distributor": .92,
    "secondary": .84,
    "marketplace": .80,
    "unknown": .68,
}


def source_family(ev: Evidence) -> str:
    source_type = key_norm(ev.source_type or "")
    url = key_norm(ev.source_url or "")
    if "official pdf" in source_type:
        return "official_pdf"
    if "manufacturer" in source_type or "official" in source_type:
        return "manufacturer"
    if "regulatory" in source_type or "certification" in source_type:
        return "regulatory"
    if "catalog" in source_type and "structured" in source_type:
        return "structured_catalog"
    if "distributor" in source_type:
        return "distributor"
    if "marketplace" in source_type or any(x in url for x in ["falabella", "amazon", "ebay", "mercadolibre", "ripley"]):
        return "marketplace"
    if "secondary" in source_type:
        return "secondary"
    return "unknown"


def authority_rank(canonical: str, ev: Evidence) -> int:
    family = source_family(ev)
    order = FIELD_SOURCE_ORDER.get(canonical, GENERIC_ORDER)
    try:
        return len(order) - order.index(family)
    except ValueError:
        return 0


def authority_cap(canonical: str, ev: Evidence) -> float:
    return SOURCE_CAPS.get(source_family(ev), SOURCE_CAPS["unknown"])


def effective_quality(canonical: str, ev: Evidence, base_quality: float) -> tuple[int, float]:
    """Return (authority priority, capped quality) without manufacturing confidence."""
    cap = authority_cap(canonical, ev)
    return authority_rank(canonical, ev), min(float(base_quality or 0), cap)
