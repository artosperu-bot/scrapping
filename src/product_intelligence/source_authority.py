from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse
import re

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


@dataclass(frozen=True)
class AuthoritySignals:
    url: str
    requested_brand: str | None = None
    organization_names: tuple[str, ...] = ()
    canonical_host: str | None = None
    same_origin_product_links: int = 0
    brand_owned_footer: bool = False
    explicit_manufacturer_name: str | None = None
    support_signal: bool = False
    marketplace_signal: bool = False
    retailer_signal: bool = False
    technical_database_signal: bool = False


@dataclass(frozen=True)
class AuthorityAssessment:
    source_class: str
    confidence: float
    reasons: tuple[str, ...]


def _authority_norm(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def _authority_host(value: str | None) -> str:
    raw = str(value or "")
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    return (parsed.hostname or "").lower().removeprefix("www.")


def classify_source_authority(signals: AuthoritySignals) -> AuthorityAssessment:
    """Classify site authority from independent ownership signals.

    A brand token in a hostname is deliberately never enough to prove manufacturer ownership.
    """
    host = _authority_host(signals.url)
    canonical = _authority_host(signals.canonical_host)
    brand = _authority_norm(signals.requested_brand)
    orgs = {_authority_norm(x) for x in signals.organization_names if _authority_norm(x)}
    explicit = _authority_norm(signals.explicit_manufacturer_name)

    if signals.marketplace_signal:
        return AuthorityAssessment("marketplace", 0.95, ("MARKETPLACE_SIGNAL",))
    if signals.technical_database_signal:
        return AuthorityAssessment("technical_database", 0.88, ("TECHNICAL_DATABASE_SIGNAL",))
    if signals.retailer_signal:
        return AuthorityAssessment("retailer", 0.86, ("RETAILER_SIGNAL",))

    org_matches_brand = bool(brand and brand in orgs)
    explicit_matches_brand = bool(brand and explicit and explicit == brand)
    canonical_same_origin = bool(canonical and host and canonical == host)
    product_ecosystem = signals.same_origin_product_links >= 3

    independent = sum(1 for flag in (
        org_matches_brand,
        explicit_matches_brand,
        canonical_same_origin,
        product_ecosystem,
        signals.brand_owned_footer,
    ) if flag)

    if independent >= 3 and (org_matches_brand or explicit_matches_brand):
        klass = "manufacturer_support" if signals.support_signal else "manufacturer"
        return AuthorityAssessment(
            klass,
            min(0.99, 0.72 + independent * 0.05),
            ("MULTIPLE_INDEPENDENT_BRAND_OWNERSHIP_SIGNALS", f"SIGNAL_COUNT:{independent}"),
        )

    if signals.support_signal and independent >= 2 and (org_matches_brand or explicit_matches_brand):
        return AuthorityAssessment("manufacturer_support", 0.78, ("SUPPORT_WITH_CORROBORATED_BRAND_OWNERSHIP",))

    if brand and brand in _authority_norm(host):
        return AuthorityAssessment("unknown", 0.35, ("BRAND_TOKEN_IN_HOST_ONLY",))

    return AuthorityAssessment("third_party", 0.50, ("NO_MANUFACTURER_OWNERSHIP_PROOF",))
