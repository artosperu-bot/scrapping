from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

from .discovery import MARKETPLACE_HINTS, SearchCandidate, search_raw
from .models import ProductIdentity
from .normalize import key_norm

_GENERIC_LEADING = {
    "buy", "shop", "official", "product", "products", "specification", "specifications",
    "specs", "manual", "datasheet", "review", "reviews", "new", "the", "a", "an",
}
_EXPLICIT_BRAND = re.compile(
    r"(?:brand|manufacturer|marca|fabricante)\s*[:\-]\s*([A-Za-z0-9][A-Za-z0-9&.+_-]*(?:\s+[A-Za-z0-9][A-Za-z0-9&.+_-]*){0,2})",
    re.I,
)


@dataclass
class IdentityBootstrapResult:
    identity: ProductIdentity
    status: str
    confidence: float = 0.0
    reason: str = ""
    official_domain_hint: str | None = None
    raw_input: str = ""
    queries_executed: list[str] = field(default_factory=list)
    search_results_found: int = 0
    candidate_urls: list[str] = field(default_factory=list)
    brand_scores: dict[str, float] = field(default_factory=dict)
    brand_hosts: dict[str, int] = field(default_factory=dict)
    hardcoded: bool = False


def _compact(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", key_norm(value or ""))


def _raw_value(identity: ProductIdentity) -> str:
    return str(
        identity.mpn
        or identity.ean
        or identity.upc
        or identity.gtin
        or identity.sku
        or identity.model
        or identity.product_name
        or ""
    ).strip()


def _is_strong_code(value: str) -> bool:
    compact = re.sub(r"[\s-]+", "", value or "")
    return bool(
        compact
        and " " not in (value or "")
        and re.search(r"[A-Za-z]", compact)
        and re.search(r"\d", compact)
        and len(compact) >= 4
    )


def build_bootstrap_queries(identity: ProductIdentity) -> list[str]:
    raw = _raw_value(identity)
    if not raw:
        return []
    quoted = f'"{raw}"'
    queries = [quoted, f"{quoted} product", f"{quoted} specifications"]
    if _is_strong_code(raw):
        queries.append(f"{quoted} manufacturer")
    return list(dict.fromkeys(queries))


def build_deep_queries(identity: ProductIdentity, official_domain_hint: str | None = None) -> list[str]:
    raw = _raw_value(identity)
    if not raw:
        return []
    quoted = f'"{raw}"'
    brand = str(identity.brand or identity.manufacturer or "").strip()
    brand_part = f' "{brand}"' if brand else ""
    base = f"{quoted}{brand_part}"
    queries = [
        base,
        f"{base} specifications",
        f"{base} technical specifications",
        f"{base} datasheet",
        f"{base} manual",
        f"{base} pdf",
        f"{quoted} filetype:pdf",
    ]
    if brand:
        queries.append(f"{quoted} \"{brand}\" filetype:pdf")
    if official_domain_hint:
        host = official_domain_hint.strip().lower().removeprefix("www.")
        queries.extend([
            f"site:{host} {quoted}",
            f"site:{host} {quoted} specifications",
            f"site:{host} {quoted} pdf",
        ])
    return list(dict.fromkeys(q.strip() for q in queries if q.strip()))


def _candidate_text_matches_raw(candidate: SearchCandidate, raw: str) -> tuple[bool, bool, bool]:
    raw_norm = key_norm(raw)
    title = key_norm(candidate.title or "")
    snippet = key_norm(candidate.snippet or "")
    url = key_norm(candidate.url or "")
    return raw_norm in title, raw_norm in snippet, _compact(raw) in _compact(url)


def _clean_brand_phrase(value: str) -> str | None:
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9&.+_-]*", value or "")
    while tokens and key_norm(tokens[0]) in _GENERIC_LEADING:
        tokens.pop(0)
    if not tokens:
        return None
    # Brand resolution is intentionally conservative. A single leading token is
    # much less likely to absorb a product family/model into the brand value.
    token = tokens[0].strip("-_.")
    if len(token) < 2 or token.isdigit():
        return None
    return token


def _brand_evidence(candidate: SearchCandidate, raw: str) -> list[tuple[str, float, str]]:
    title = str(candidate.title or "").strip()
    snippet = str(candidate.snippet or "").strip()
    title_match, snippet_match, url_match = _candidate_text_matches_raw(candidate, raw)
    if not (title_match or snippet_match or url_match):
        return []

    out: list[tuple[str, float, str]] = []
    combined = f"{title} {snippet}"
    for match in _EXPLICIT_BRAND.finditer(combined):
        brand = _clean_brand_phrase(match.group(1))
        if brand:
            out.append((brand, 4.0, "explicit_brand_label"))

    raw_pattern = re.compile(re.escape(raw), re.I)
    match = raw_pattern.search(title)
    if match:
        prefix = title[: match.start()].strip(" |:-–—•")
        if prefix:
            segment = re.split(r"[|:–—•]", prefix)[-1].strip()
            tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9&.+_-]*", segment)
            if tokens:
                brand = _clean_brand_phrase(tokens[-1] if not _is_strong_code(raw) else tokens[0])
                if brand:
                    out.append((brand, 3.0, "brand_with_raw_in_title"))
    elif _is_strong_code(raw) and (snippet_match or url_match):
        segment = re.split(r"[|:–—•-]", title)[0].strip()
        brand = _clean_brand_phrase(segment)
        if brand:
            out.append((brand, 2.0, "leading_title_brand"))

    return out


def resolve_identity_from_candidates(identity: ProductIdentity, candidates: list[SearchCandidate]) -> IdentityBootstrapResult:
    raw = _raw_value(identity)
    if not raw:
        return IdentityBootstrapResult(identity=identity.model_copy(deep=True), status="IDENTITY_UNRESOLVED", reason="NO_RAW_IDENTITY")
    if identity.brand:
        return IdentityBootstrapResult(
            identity=identity.model_copy(deep=True),
            status="RESOLVED",
            confidence=1.0,
            reason="BRAND_PROVIDED",
            raw_input=raw,
        )

    scores: dict[str, float] = {}
    labels: dict[str, str] = {}
    hosts_by_brand: dict[str, set[str]] = {}
    official_hosts: dict[str, tuple[float, str]] = {}

    for candidate in candidates:
        host = (urlparse(candidate.url or "").hostname or "").lower().removeprefix("www.")
        title_match, snippet_match, url_match = _candidate_text_matches_raw(candidate, raw)
        if not (title_match or snippet_match or url_match):
            continue
        base_match = 2.0 if title_match else 1.0
        if snippet_match:
            base_match += 0.5
        if url_match:
            base_match += 0.5
        for brand, evidence_score, _reason in _brand_evidence(candidate, raw):
            key = _compact(brand)
            if not key:
                continue
            labels.setdefault(key, brand)
            prior_hosts = hosts_by_brand.setdefault(key, set())
            independent_bonus = 2.0 if host and prior_hosts and host not in prior_hosts else 0.0
            score = base_match + evidence_score + independent_bonus
            host_compact = _compact(host.split(".")[0] if host else "")
            if host_compact and key in host_compact:
                score += 2.0
            hay = key_norm(f"{candidate.title} {candidate.snippet}")
            if "official" in hay or "manufacturer" in hay or "fabricante" in hay:
                score += 1.0
            if any(marker in host for marker in MARKETPLACE_HINTS):
                score -= 2.0
            scores[key] = scores.get(key, 0.0) + score
            if host:
                prior_hosts.add(host)
            if host and host_compact and key in host_compact and not any(marker in host for marker in MARKETPLACE_HINTS):
                current = official_hosts.get(key)
                if current is None or score > current[0]:
                    official_hosts[key] = (score, host)

    if not scores:
        return IdentityBootstrapResult(
            identity=identity.model_copy(deep=True),
            status="IDENTITY_UNRESOLVED",
            reason="INSUFFICIENT_EVIDENCE",
            raw_input=raw,
            search_results_found=len(candidates),
            candidate_urls=[c.url for c in candidates],
        )

    ranked = sorted(scores.items(), key=lambda row: row[1], reverse=True)
    best_key, best_score = ranked[0]
    runner_score = ranked[1][1] if len(ranked) > 1 else 0.0
    host_count = len(hosts_by_brand.get(best_key, set()))
    margin = best_score - runner_score
    resolved = best_score >= 8.0 and (margin >= 3.0 or (host_count >= 2 and best_score >= runner_score * 1.35))
    if not resolved:
        return IdentityBootstrapResult(
            identity=identity.model_copy(deep=True),
            status="IDENTITY_UNRESOLVED",
            confidence=min(0.74, best_score / max(1.0, best_score + runner_score + 2.0)),
            reason="AMBIGUOUS_BRAND" if len(ranked) > 1 and margin < 3.0 else "INSUFFICIENT_EVIDENCE",
            raw_input=raw,
            search_results_found=len(candidates),
            candidate_urls=[c.url for c in candidates],
            brand_scores={labels[k]: round(v, 3) for k, v in scores.items()},
            brand_hosts={labels[k]: len(hosts_by_brand.get(k, set())) for k in scores},
        )

    learned = identity.model_copy(deep=True)
    learned.brand = labels[best_key]
    if not _is_strong_code(raw) and not learned.model:
        learned.model = raw
    confidence = min(0.99, 0.72 + min(best_score, 18.0) * 0.012 + min(host_count, 3) * 0.025)
    return IdentityBootstrapResult(
        identity=learned,
        status="RESOLVED",
        confidence=confidence,
        reason="CROSS_SOURCE_BRAND_RESOLUTION",
        official_domain_hint=official_hosts.get(best_key, (0.0, None))[1],
        raw_input=raw,
        search_results_found=len(candidates),
        candidate_urls=[c.url for c in candidates],
        brand_scores={labels[k]: round(v, 3) for k, v in scores.items()},
        brand_hosts={labels[k]: len(hosts_by_brand.get(k, set())) for k in scores},
        hardcoded=False,
    )


def bootstrap_identity(identity: ProductIdentity, *, limit_per_query: int = 18, timeout: int = 8) -> IdentityBootstrapResult:
    queries = build_bootstrap_queries(identity)
    collected: list[SearchCandidate] = []
    seen_urls: set[str] = set()
    result = IdentityBootstrapResult(identity=identity.model_copy(deep=True), status="IDENTITY_UNRESOLVED", reason="NO_SEARCH_RESULTS")

    for query in queries:
        rows = search_raw(query, limit=limit_per_query, timeout=timeout)
        for row in rows:
            if row.url in seen_urls:
                continue
            seen_urls.add(row.url)
            collected.append(row)
        result = resolve_identity_from_candidates(identity, collected)
        result.queries_executed = list(queries[: queries.index(query) + 1])
        result.search_results_found = len(collected)
        result.candidate_urls = [c.url for c in collected]
        if result.status == "RESOLVED" and len(result.brand_hosts.get(result.identity.brand or "", 0) if False else []) > 1:
            break
        # The resolver already requires either a decisive score margin or independent
        # sources, so a resolved result is safe to use as an early-success bootstrap.
        if result.status == "RESOLVED":
            break

    return result
