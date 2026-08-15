from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

from .discovery import MARKETPLACE_HINTS, SearchCandidate, _provider_search
from .html_extract import extract_page
from .models import ProductIdentity
from .normalize import key_norm
from .page_type import classify_page_type
from .source_signals import derive_observed_identity, derive_page_signals
from .web_fetch import fetch_page

_GENERIC_LEADING = {
    "buy", "shop", "official", "product", "products", "specification", "specifications",
    "specs", "manual", "datasheet", "review", "reviews", "new", "the", "a", "an",
}
_EXPLICIT_BRAND = re.compile(
    r"(?:brand|manufacturer|marca|fabricante)\s*[:\-]\s*([A-Za-z0-9][A-Za-z0-9&.+_-]*(?:\s+[A-Za-z0-9][A-Za-z0-9&.+_-]*){0,2})",
    re.I,
)


@dataclass
class PageIdentitySignal:
    url: str
    brand: str | None = None
    model: str | None = None
    product_name: str | None = None
    manufacturer: str | None = None
    exact_raw_match: bool = False
    strong_identifier_match: bool = False
    material: bool = False
    structured_brand: bool = False
    source_kind: str = "html"
    reason: str = ""


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
    page_probes_attempted: int = 0
    page_probes_succeeded: int = 0
    page_signals: list[dict] = field(default_factory=list)
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
    return raw_norm in title, raw_norm in snippet, _compact(raw) in _compact(candidate.url or "")


def _clean_brand_phrase(value: str) -> str | None:
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9&.+_-]*", value or "")
    while tokens and key_norm(tokens[0]) in _GENERIC_LEADING:
        tokens.pop(0)
    if not tokens:
        return None
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
        suffix = title[match.end():].strip(" |:-–—•")
        if prefix:
            segment = re.split(r"[|:–—•]", prefix)[-1].strip()
            tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9&.+_-]*", segment)
            if tokens:
                brand = _clean_brand_phrase(tokens[-1] if not _is_strong_code(raw) else tokens[0])
                if brand:
                    out.append((brand, 3.0, "brand_before_raw_in_title"))
        if suffix:
            segment = re.split(r"[|:–—•]", suffix)[0].strip()
            brand = _clean_brand_phrase(segment)
            if brand and key_norm(brand) not in _GENERIC_LEADING:
                out.append((brand, 1.6, "brand_after_raw_in_title"))
    elif _is_strong_code(raw) and (snippet_match or url_match):
        segment = re.split(r"[|:–—•-]", title)[0].strip()
        brand = _clean_brand_phrase(segment)
        if brand:
            out.append((brand, 2.0, "leading_title_brand"))

    return out


def _rank_brand_scores(identity: ProductIdentity, candidates: list[SearchCandidate], page_signals: list[PageIdentitySignal] | None = None):
    raw = _raw_value(identity)
    scores: dict[str, float] = {}
    labels: dict[str, str] = {}
    hosts_by_brand: dict[str, set[str]] = {}
    official_hosts: dict[str, tuple[float, str]] = {}
    model_by_brand: dict[str, list[tuple[float, str]]] = {}

    def add(brand: str | None, score: float, host: str, *, model: str | None = None, official_hint: bool = False):
        brand = str(brand or "").strip()
        key = _compact(brand)
        if not key or len(key) < 2:
            return
        labels.setdefault(key, brand)
        prior_hosts = hosts_by_brand.setdefault(key, set())
        if host and prior_hosts and host not in prior_hosts:
            score += 2.0
        if any(marker in host for marker in MARKETPLACE_HINTS):
            score -= 2.0
        scores[key] = scores.get(key, 0.0) + score
        if host:
            prior_hosts.add(host)
        if model:
            model_by_brand.setdefault(key, []).append((score, model))
        if official_hint and host and not any(marker in host for marker in MARKETPLACE_HINTS):
            current = official_hosts.get(key)
            if current is None or score > current[0]:
                official_hosts[key] = (score, host)

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
            host_compact = _compact(host.split(".")[0] if host else "")
            score = base_match + evidence_score
            if host_compact and key and key in host_compact:
                score += 1.5
            hay = key_norm(f"{candidate.title} {candidate.snippet}")
            if "official" in hay or "manufacturer" in hay or "fabricante" in hay:
                score += 0.8
            add(brand, score, host, official_hint=bool(host_compact and key and key in host_compact))

    for signal in page_signals or []:
        if not signal.material or not signal.exact_raw_match:
            continue
        host = (urlparse(signal.url or "").hostname or "").lower().removeprefix("www.")
        brand = signal.brand or signal.manufacturer
        if not brand:
            continue
        key = _compact(brand)
        host_compact = _compact(host.split(".")[0] if host else "")
        score = 7.0 if signal.structured_brand else 4.5
        if signal.strong_identifier_match:
            score += 3.0
        if signal.model and _compact(raw) in _compact(signal.model):
            score += 1.5
        if signal.product_name and _compact(raw) in _compact(signal.product_name):
            score += 1.5
        official_hint = bool(host_compact and key and key in host_compact and signal.structured_brand)
        if official_hint:
            score += 1.5
        add(brand, score, host, model=signal.model or signal.product_name, official_hint=official_hint)

    return scores, labels, hosts_by_brand, official_hosts, model_by_brand


def _finalize_resolution(identity: ProductIdentity, candidates: list[SearchCandidate], page_signals: list[PageIdentitySignal] | None = None) -> IdentityBootstrapResult:
    raw = _raw_value(identity)
    if not raw:
        return IdentityBootstrapResult(identity=identity.model_copy(deep=True), status="IDENTITY_UNRESOLVED", reason="NO_RAW_IDENTITY")
    if identity.brand:
        return IdentityBootstrapResult(identity=identity.model_copy(deep=True), status="RESOLVED", confidence=1.0, reason="BRAND_PROVIDED", raw_input=raw)

    scores, labels, hosts_by_brand, official_hosts, model_by_brand = _rank_brand_scores(identity, candidates, page_signals)
    if not scores:
        return IdentityBootstrapResult(
            identity=identity.model_copy(deep=True), status="IDENTITY_UNRESOLVED", reason="INSUFFICIENT_EVIDENCE",
            raw_input=raw, search_results_found=len(candidates), candidate_urls=[c.url for c in candidates],
        )

    ranked = sorted(scores.items(), key=lambda row: row[1], reverse=True)
    best_key, best_score = ranked[0]
    runner_score = ranked[1][1] if len(ranked) > 1 else 0.0
    host_count = len(hosts_by_brand.get(best_key, set()))
    margin = best_score - runner_score
    has_page_evidence = any(_compact(s.brand or s.manufacturer) == best_key and s.material and s.exact_raw_match for s in (page_signals or []))
    decisive_single_page = has_page_evidence and best_score >= 10.0 and margin >= 3.0
    decisive_cross_source = host_count >= 2 and best_score >= 11.0 and (margin >= 3.0 or best_score >= max(1.0, runner_score) * 1.35)
    decisive_serp = not page_signals and best_score >= 8.0 and (margin >= 3.0 or (host_count >= 2 and best_score >= max(1.0, runner_score) * 1.35))
    resolved = decisive_single_page or decisive_cross_source or decisive_serp

    if not resolved:
        return IdentityBootstrapResult(
            identity=identity.model_copy(deep=True), status="IDENTITY_UNRESOLVED",
            confidence=min(0.74, best_score / max(1.0, best_score + runner_score + 2.0)),
            reason="AMBIGUOUS_BRAND" if len(ranked) > 1 and margin < 3.0 else "INSUFFICIENT_EVIDENCE",
            raw_input=raw, search_results_found=len(candidates), candidate_urls=[c.url for c in candidates],
            brand_scores={labels[k]: round(v, 3) for k, v in scores.items()},
            brand_hosts={labels[k]: len(hosts_by_brand.get(k, set())) for k in scores},
        )

    learned = identity.model_copy(deep=True)
    learned.brand = labels[best_key]
    if not learned.model:
        observed_models = sorted(model_by_brand.get(best_key, []), reverse=True)
        observed_model = observed_models[0][1] if observed_models else None
        if observed_model and _compact(raw) in _compact(observed_model):
            learned.model = raw if not _is_strong_code(raw) else observed_model
        elif not _is_strong_code(raw):
            learned.model = raw

    confidence = min(0.99, 0.74 + min(best_score, 20.0) * 0.011 + min(host_count, 3) * 0.025)
    return IdentityBootstrapResult(
        identity=learned, status="RESOLVED", confidence=confidence,
        reason="PAGE_BACKED_IDENTITY_RESOLUTION" if has_page_evidence else "CROSS_SOURCE_BRAND_RESOLUTION",
        official_domain_hint=official_hosts.get(best_key, (0.0, None))[1], raw_input=raw,
        search_results_found=len(candidates), candidate_urls=[c.url for c in candidates],
        brand_scores={labels[k]: round(v, 3) for k, v in scores.items()},
        brand_hosts={labels[k]: len(hosts_by_brand.get(k, set())) for k in scores}, hardcoded=False,
    )


def resolve_identity_from_candidates(identity: ProductIdentity, candidates: list[SearchCandidate]) -> IdentityBootstrapResult:
    return _finalize_resolution(identity, candidates, None)


def resolve_identity_with_page_signals(
    identity: ProductIdentity,
    candidates: list[SearchCandidate],
    page_signals: list[PageIdentitySignal],
) -> IdentityBootstrapResult:
    result = _finalize_resolution(identity, candidates, page_signals)
    result.page_probes_attempted = len(page_signals)
    result.page_probes_succeeded = sum(1 for s in page_signals if s.material and s.exact_raw_match)
    result.page_signals = [
        {
            "url": s.url, "brand": s.brand, "manufacturer": s.manufacturer, "model": s.model,
            "product_name": s.product_name, "exact_raw_match": s.exact_raw_match,
            "strong_identifier_match": s.strong_identifier_match, "material": s.material,
            "structured_brand": s.structured_brand, "reason": s.reason,
        }
        for s in page_signals
    ]
    return result


def _walk_dicts(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_dicts(child)


def _structured_brand_present(page: dict, brand: str | None) -> bool:
    target = _compact(brand)
    if not target:
        return False
    for obj in list(_walk_dicts(page.get("jsonld", []))) + list(_walk_dicts(page.get("embedded", {}))):
        for key in ("brand", "manufacturer"):
            value = obj.get(key) if isinstance(obj, dict) else None
            if isinstance(value, dict):
                value = value.get("name")
            if target and target == _compact(str(value or "")):
                return True
    return False


def _probe_candidate_page(identity: ProductIdentity, candidate: SearchCandidate) -> PageIdentitySignal:
    raw = _raw_value(identity)
    try:
        fetched = fetch_page(candidate.url, browser_fallback=False)
        if int(fetched.status_code or 0) >= 400 or not fetched.html:
            return PageIdentitySignal(url=candidate.url, reason=f"HTTP_{fetched.status_code}")
        page = extract_page(fetched.html, fetched.final_url, [raw] if raw else [])
        observed = derive_observed_identity(identity, page)
        assessment = classify_page_type(derive_page_signals(fetched.html, fetched.final_url, page))
        page_text = str(page.get("text") or "")
        exact_raw = bool(_compact(raw) and _compact(raw) in _compact(page_text))
        strong_match = False
        if _is_strong_code(raw):
            observed_ids = [*observed.mpns, *observed.gtins, *observed.eans, *observed.upcs]
            strong_match = any(_compact(raw) == _compact(x) for x in observed_ids) or exact_raw
        brand = observed.brand
        return PageIdentitySignal(
            url=fetched.final_url or candidate.url,
            brand=brand,
            model=observed.model,
            product_name=observed.product_name,
            exact_raw_match=exact_raw,
            strong_identifier_match=strong_match,
            material=bool(assessment.material_allowed),
            structured_brand=_structured_brand_present(page, brand),
            reason="OK" if assessment.material_allowed else f"PAGE_TYPE_{assessment.page_type}",
        )
    except Exception as exc:
        return PageIdentitySignal(url=candidate.url, reason=f"{type(exc).__name__}")


def _candidate_probe_rank(candidate: SearchCandidate, raw: str) -> tuple:
    title_match, snippet_match, url_match = _candidate_text_matches_raw(candidate, raw)
    host = (urlparse(candidate.url or "").hostname or "").lower()
    marketplace = any(marker in host for marker in MARKETPLACE_HINTS)
    technical = any(token in key_norm(f"{candidate.title} {candidate.snippet} {candidate.url}") for token in (
        "specification", "specifications", "datasheet", "manual", "support", "product",
    ))
    return (
        0 if title_match else 1,
        0 if url_match else 1,
        0 if technical else 1,
        1 if marketplace else 0,
        0 if snippet_match else 1,
    )


def _probe_top_candidates(identity: ProductIdentity, candidates: list[SearchCandidate], *, max_probes: int = 6) -> list[PageIdentitySignal]:
    raw = _raw_value(identity)
    ordered = sorted(candidates, key=lambda c: _candidate_probe_rank(c, raw))
    signals: list[PageIdentitySignal] = []
    seen_hosts: set[str] = set()
    deferred: list[SearchCandidate] = []
    for candidate in ordered:
        host = (urlparse(candidate.url or "").hostname or "").lower().removeprefix("www.")
        if host in seen_hosts:
            deferred.append(candidate)
            continue
        seen_hosts.add(host)
        signals.append(_probe_candidate_page(identity, candidate))
        if len(signals) >= max_probes:
            return signals
    for candidate in deferred:
        signals.append(_probe_candidate_page(identity, candidate))
        if len(signals) >= max_probes:
            break
    return signals


def _search_raw(query: str, *, limit: int = 18, timeout: int = 8) -> list[SearchCandidate]:
    rows = _provider_search(query, timeout)
    out: list[SearchCandidate] = []
    seen: set[str] = set()
    for url, title, snippet in rows:
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(SearchCandidate(url=url, title=title, snippet=snippet))
        if len(out) >= limit:
            break
    return out


def bootstrap_identity(identity: ProductIdentity, *, limit_per_query: int = 18, timeout: int = 8) -> IdentityBootstrapResult:
    queries = build_bootstrap_queries(identity)
    collected: list[SearchCandidate] = []
    seen_urls: set[str] = set()
    result = IdentityBootstrapResult(identity=identity.model_copy(deep=True), status="IDENTITY_UNRESOLVED", reason="NO_SEARCH_RESULTS")
    probed_urls: set[str] = set()
    page_signals: list[PageIdentitySignal] = []

    # High-value bootstrap queries first. The fourth manufacturer query is only used
    # when the first three still cannot resolve identity.
    for index, query in enumerate(queries):
        rows = _search_raw(query, limit=limit_per_query, timeout=timeout)
        for row in rows:
            if row.url in seen_urls:
                continue
            seen_urls.add(row.url)
            collected.append(row)

        serp_result = resolve_identity_from_candidates(identity, collected)
        if serp_result.status == "RESOLVED":
            result = serp_result
        else:
            fresh_probe_pool = [c for c in collected if c.url not in probed_urls]
            fresh_signals = _probe_top_candidates(identity, fresh_probe_pool, max_probes=max(0, 6 - len(page_signals)))
            for signal in fresh_signals:
                probed_urls.add(signal.url)
            page_signals.extend(fresh_signals)
            result = resolve_identity_with_page_signals(identity, collected, page_signals)

        result.queries_executed = queries[: index + 1]
        result.search_results_found = len(collected)
        result.candidate_urls = [c.url for c in collected]
        result.page_probes_attempted = len(page_signals)
        result.page_probes_succeeded = sum(1 for s in page_signals if s.material and s.exact_raw_match)
        result.page_signals = [
            {
                "url": s.url, "brand": s.brand, "manufacturer": s.manufacturer, "model": s.model,
                "product_name": s.product_name, "exact_raw_match": s.exact_raw_match,
                "strong_identifier_match": s.strong_identifier_match, "material": s.material,
                "structured_brand": s.structured_brand, "reason": s.reason,
            }
            for s in page_signals
        ]
        if result.status == "RESOLVED":
            break
        if len(page_signals) >= 6 and index >= 2:
            break

    return result
