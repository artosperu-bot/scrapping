from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit

from .models import ProductIdentity
from .price_models import PriceOffer


def _norm(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def _tokens(value: str | None) -> list[str]:
    return [t.lower() for t in re.findall(r"[A-Za-z]+|\d+", value or "") if len(t) > 1]


def _model_generation_conflict(identity: ProductIdentity, evidence: dict) -> bool:
    expected_model = identity.model or identity.product_name or ""
    observed = " ".join(
        str(evidence.get(key) or "")
        for key in ("model", "title", "product_name")
        if evidence.get(key)
    )
    expected_numbers = {t for t in _tokens(expected_model) if t.isdigit()}
    observed_numbers = {t for t in _tokens(observed) if t.isdigit()}
    return bool(expected_numbers and observed_numbers and not expected_numbers.issubset(observed_numbers))


def score_offer_identity(identity: ProductIdentity, evidence: dict) -> tuple[float, str, list[str]]:
    conflicts: list[str] = []
    expected_mpn = _norm(identity.mpn)
    got_mpn = _norm(str(evidence.get("mpn") or evidence.get("part_number") or ""))
    if expected_mpn and got_mpn:
        if expected_mpn == got_mpn:
            if _model_generation_conflict(identity, evidence):
                return 0.0, "CONFLICT", ["model_generation_conflict"]
            return 1.0, "EXACT_MPN", []
        conflicts.append("mpn_conflict")
        return 0.0, "CONFLICT", conflicts

    expected_ids = {_norm(v) for v in (identity.ean, identity.upc, identity.gtin) if v}
    got_ids = {_norm(str(evidence.get(k) or "")) for k in ("ean", "upc", "gtin") if evidence.get(k)}
    if expected_ids and got_ids:
        if expected_ids & got_ids:
            if _model_generation_conflict(identity, evidence):
                return 0.0, "CONFLICT", ["model_generation_conflict"]
            return 0.98, "EXACT_GTIN", []
        conflicts.append("gtin_conflict")
        return 0.0, "CONFLICT", conflicts

    brand_expected = _norm(identity.brand)
    brand_got = _norm(str(evidence.get("brand") or ""))
    if brand_expected and brand_got and brand_expected != brand_got:
        return 0.0, "CONFLICT", ["brand_conflict"]

    expected_model = identity.model or identity.product_name or ""
    got_model = str(evidence.get("model") or evidence.get("title") or evidence.get("product_name") or "")
    exp_tokens = _tokens(expected_model)
    got_tokens = _tokens(got_model)
    if not exp_tokens or not got_tokens:
        return 0.0, "UNVERIFIED", []

    exp_numbers = {t for t in exp_tokens if t.isdigit()}
    got_numbers = {t for t in got_tokens if t.isdigit()}
    if exp_numbers and got_numbers and not exp_numbers.issubset(got_numbers):
        return 0.35, "CONFLICT", ["model_generation_conflict"]

    hits = sum(1 for t in exp_tokens if t in got_tokens)
    ratio = hits / max(1, len(exp_tokens))
    if ratio >= 0.85 and (not brand_expected or brand_expected == brand_got or brand_expected in _norm(got_model)):
        return 0.90, "BRAND_MODEL", []
    if ratio >= 0.65:
        return 0.75, "PROBABLE_MODEL", []
    return 0.40, "UNVERIFIED", []


def _canonical_url(url: str) -> str:
    p = urlsplit(url)
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/"), "", ""))


_PERU_CHANNELS = {
    "plazavea",
    "oechsle",
    "mercadolibre",
    "falabella",
    "ripley",
    "sodimac",
    "jblper",
}

_PERU_RETAIL_HOSTS = {
    "perudataconsult.net",
    "bigmarketperu.com",
}
_PERU_PATH_HOSTS = {
    "panacompu.com",
}


def is_peru_offer(row: PriceOffer) -> bool:
    """Return True only for offers evidenced as belonging to the Peru market."""
    channel = _norm(row.channel)
    if channel in _PERU_CHANNELS:
        return True
    parsed = urlsplit(row.url)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    path = (parsed.path or "").lower()
    if host.endswith(".pe") or host.endswith(".com.pe"):
        return True
    if host in _PERU_RETAIL_HOSTS and str(row.currency or "").upper() == "PEN":
        return True
    if host in _PERU_PATH_HOSTS and (path.startswith("/peru/") or path == "/peru") and str(row.currency or "").upper() == "PEN":
        return True
    return False


def _market_rank(row: PriceOffer) -> int:
    return 0 if is_peru_offer(row) else 1


def _seller_key(value: str | None) -> str:
    key = _norm(value)
    for suffix in ("perusac", "perueirl", "perusrl", "sac", "eirl", "srl"):
        if key.endswith(suffix) and len(key) > len(suffix) + 2:
            return key[:-len(suffix)]
    return key


def competitor_key(row: PriceOffer) -> str:
    tax_id = _norm(row.seller_tax_id)
    if tax_id:
        return f"tax:{tax_id}"
    for value in (row.seller_legal_name, row.seller_display_name):
        key = _seller_key(value)
        if key:
            return f"seller:{key}"
    channel = _seller_key(row.channel)
    if channel:
        return f"channel:{channel}"
    return f"url:{_canonical_url(row.url)}"


def dedupe_offers(offers: list[PriceOffer]) -> list[PriceOffer]:
    best: dict[tuple, PriceOffer] = {}
    for row in offers:
        key = (
            _norm(row.channel),
            _norm(row.seller_display_name),
            _norm(row.part_number or row.model),
            row.publication_id or row.sku or _canonical_url(row.url),
        )
        current = best.get(key)
        if current is None or row.confidence > current.confidence or (
            row.confidence == current.confidence and row.source_type == "api" and current.source_type != "api"
        ):
            best[key] = row

    return sorted(
        best.values(),
        key=lambda x: (_market_rank(x), -x.confidence, str(x.currency or "").upper(), x.selling_price, x.channel.lower()),
    )
