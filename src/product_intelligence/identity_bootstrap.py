from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from urllib.parse import urlparse

from .browser_search import browser_search
from .discovery import MARKETPLACE_HINTS, SearchCandidate, _provider_search
from .html_extract import extract_page
from .models import ProductIdentity
from .normalize import key_norm
from .page_type import classify_page_type
from .source_authority import classify_source_authority
from .source_signals import derive_authority_signals, derive_observed_identity, derive_page_signals
from .web_fetch import fetch_page

_GENERIC_LEADING = {
    "buy", "shop", "official", "product", "products", "specification", "specifications",
    "specs", "manual", "datasheet", "review", "reviews", "new", "the", "a", "an",
    "teardown", "unboxing", "hands", "on", "guide", "of", "for", "with", "by",
}
_CONTEXT_STOPWORDS = {
    "buy", "shop", "official", "product", "products", "specification", "specifications", "specs",
    "manual", "datasheet", "review", "reviews", "new", "the", "a", "an", "for", "with", "from",
    "and", "or", "of", "to", "in", "on", "by", "online", "price", "sale", "amazon", "ebay",
    "walmart", "support", "page", "pdf", "download", "tracking", "history", "http", "https", "www",
    "com", "net", "org", "phone", "smartphone", "laptop", "monitor", "printer", "mouse", "keyboard",
    "cable", "ssd", "drive", "storage", "wireless", "wired", "headphone", "headphones", "router",
    "gaming", "memory", "desktop", "external", "internal", "black", "blue", "device", "technology",
    "data", "best", "download", "manuals", "barcode", "productindetail", "icecat",
}
_NON_PRODUCT_INTENT = {
    "flight", "airline", "airlines", "airport", "arrival", "departure",
    "bill", "legislation", "statute", "court", "lawsuit", "case law",
    "discography", "album", "song", "lyrics", "tracking number",
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
    authority_owned: bool = False
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
        identity.mpn or identity.ean or identity.upc or identity.gtin or identity.sku
        or identity.model or identity.product_name or ""
    ).strip()


def _is_strong_code(value: str) -> bool:
    compact = re.sub(r"[\s-]+", "", value or "")
    return bool(
        compact and " " not in (value or "") and re.search(r"[A-Za-z]", compact)
        and re.search(r"\d", compact) and len(compact) >= 4
    )


def identity_probe_budget() -> tuple[int, int]:
    return 4, 8


def _normalized_tokens(value: str | None) -> list[str]:
    raw = re.findall(r"[a-z]+|\d+", key_norm(value or ""))
    out: list[str] = []
    i = 0
    while i < len(raw):
        token = raw[i]
        if token in {"gen", "generation"} and i + 1 < len(raw) and raw[i + 1].isdigit():
            out.append(f"g{raw[i + 1]}")
            i += 2
            continue
        if token == "g" and i + 1 < len(raw) and raw[i + 1].isdigit():
            out.append(f"g{raw[i + 1]}")
            i += 2
            continue
        if re.fullmatch(r"g\d+", token):
            out.append(token)
            i += 1
            continue
        out.append(token)
        i += 1
    return out


def build_bootstrap_queries(identity: ProductIdentity) -> list[str]:
    raw = _raw_value(identity)
    if not raw:
        return []
    quoted = f'"{raw}"'
    return list(dict.fromkeys([
        quoted,
        f"{quoted} product",
        f"{quoted} specifications",
        f"{quoted} manufacturer",
    ]))


def build_discovery_fallback_queries(raw: str) -> list[str]:
    raw = str(raw or "").strip()
    if not raw:
        return []
    return [raw, f"{raw} product", f"{raw} specifications"]


def build_context_queries(raw: str, terms: list[str]) -> list[str]:
    quoted = f'"{raw}"'
    out: list[str] = []
    for term in terms[:3]:
        term = str(term or "").strip()
        if term:
            out.append(f'{quoted} "{term}"')
    return list(dict.fromkeys(out))


def build_deep_queries(identity: ProductIdentity, official_domain_hint: str | None = None) -> list[str]:
    raw = _raw_value(identity)
    if not raw:
        return []
    quoted = f'"{raw}"'
    brand = str(identity.brand or getattr(identity, "manufacturer", None) or "").strip()
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
        queries.append(f'{quoted} "{brand}" filetype:pdf')
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
    raw_compact = _compact(raw)
    title = key_norm(candidate.title or "")
    snippet = key_norm(candidate.snippet or "")
    url_compact = _compact(candidate.url or "")
    return (
        bool(raw_norm and raw_norm in title),
        bool(raw_norm and raw_norm in snippet),
        bool(raw_compact and raw_compact in url_compact),
    )


def _candidate_has_full_raw(candidate: SearchCandidate, raw: str) -> bool:
    raw_compact = _compact(raw)
    combined_text = f"{candidate.title} {candidate.snippet} {candidate.url}"
    combined_compact = _compact(combined_text)
    if raw_compact and raw_compact in combined_compact:
        return True
    raw_tokens = _normalized_tokens(raw)
    if len(raw_tokens) <= 1:
        return False
    candidate_tokens = set(_normalized_tokens(combined_text))
    informative = [t for t in raw_tokens if len(t) >= 2 or any(ch.isdigit() for ch in t)]
    return bool(informative) and all(token in candidate_tokens for token in informative)


def filter_bootstrap_candidates(raw: str, candidates: list[SearchCandidate]) -> list[SearchCandidate]:
    out: list[SearchCandidate] = []
    seen: set[str] = set()
    for candidate in candidates:
        if not candidate.url or candidate.url in seen:
            continue
        host = (urlparse(candidate.url).hostname or "").lower()
        if not host or host == "bing.com" or host.endswith(".bing.com"):
            continue
        if not _candidate_has_full_raw(candidate, raw):
            continue
        seen.add(candidate.url)
        out.append(candidate)
    return out


def derive_context_terms(raw: str, candidates: list[SearchCandidate]) -> list[str]:
    raw_tokens = set(_normalized_tokens(raw))
    raw_compact = _compact(raw)
    host_sets: dict[str, set[str]] = defaultdict(set)
    counts: Counter[str] = Counter()
    labels: dict[str, str] = {}
    for candidate in filter_bootstrap_candidates(raw, candidates):
        host = (urlparse(candidate.url).hostname or "").lower().removeprefix("www.")
        text = f"{candidate.title} {candidate.snippet}"
        for token in re.findall(r"[A-Za-z][A-Za-z0-9+.-]{1,24}", text):
            norm = key_norm(token).strip(".-")
            if not norm or norm in _CONTEXT_STOPWORDS or norm in raw_tokens or _compact(norm) == raw_compact:
                continue
            if norm.isdigit() or len(norm) < 3:
                continue
            labels.setdefault(norm, token.strip(".,:;()[]{}"))
            counts[norm] += 1
            if host:
                host_sets[norm].add(host)
    ranked = sorted(counts, key=lambda term: (len(host_sets[term]), counts[term], len(term)), reverse=True)
    corroborated = [term for term in ranked if len(host_sets[term]) >= 2]
    fallback = [term for term in ranked if counts[term] >= 3 and term not in corroborated]
    return [labels[term] for term in (corroborated + fallback)[:5]]


def _brand_phrase_tokens(value: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9&.+_-]*", value or "")
    while tokens and key_norm(tokens[0]) in _GENERIC_LEADING:
        tokens.pop(0)
    cleaned: list[str] = []
    for token in tokens:
        token = token.strip("-_.")
        norm = key_norm(token)
        if len(token) < 2 or token.isdigit() or norm in _CONTEXT_STOPWORDS:
            break
        cleaned.append(token)
        if len(cleaned) >= 2:
            break
    return cleaned


def _brand_like_second_token(token: str) -> bool:
    token = str(token or "").strip()
    return bool(
        token
        and not any(ch.isdigit() for ch in token)
        and "." not in token
        and key_norm(token) not in _CONTEXT_STOPWORDS
        and re.fullmatch(r"[A-Za-z][A-Za-z&+_-]*", token)
    )


def _clean_brand_phrase(value: str, *, multiword: bool = False) -> str | None:
    tokens = _brand_phrase_tokens(value)
    if not tokens:
        return None
    if multiword and len(tokens) >= 2 and _brand_like_second_token(tokens[1]):
        return " ".join(tokens[:2])
    return tokens[0]


def _non_product_intent(candidate: SearchCandidate) -> bool:
    hay = key_norm(f"{candidate.title} {candidate.snippet}")
    return any(marker in hay for marker in _NON_PRODUCT_INTENT)


def _marketplace_host(host: str) -> bool:
    host = str(host or "").lower()
    return any(marker in host for marker in MARKETPLACE_HINTS)


def _label_matches_host(label: str, host: str) -> bool:
    label_key = _compact(label)
    host_key = _compact((host or "").removeprefix("www."))
    return bool(len(label_key) >= 3 and label_key in host_key)


def _add_prefix_evidence(out: list[tuple[str, float, str]], prefix: str, source: str, single_score: float, multi_score: float):
    prefix = str(prefix or "").strip(" |:-–—•();,.")
    if not prefix:
        return
    segment = re.split(r"[|:–—•;,]", prefix)[-1].strip()
    brand = _clean_brand_phrase(segment)
    if brand:
        out.append((brand, single_score, f"brand_before_raw_in_{source}"))
    multi = _clean_brand_phrase(segment, multiword=True)
    if multi and multi != brand:
        out.append((multi, multi_score, f"multiword_brand_before_raw_in_{source}"))


def _brand_evidence(candidate: SearchCandidate, raw: str) -> list[tuple[str, float, str]]:
    title = str(candidate.title or "").strip()
    snippet = str(candidate.snippet or "").strip()
    host = (urlparse(candidate.url or "").hostname or "").lower().removeprefix("www.")
    title_match, snippet_match, url_match = _candidate_text_matches_raw(candidate, raw)
    if not (title_match or snippet_match or url_match or _candidate_has_full_raw(candidate, raw)):
        return []

    out: list[tuple[str, float, str]] = []
    for match in _EXPLICIT_BRAND.finditer(f"{title} {snippet}"):
        brand = _clean_brand_phrase(match.group(1), multiword=True)
        if brand:
            out.append((brand, 5.5, "explicit_brand_label"))

    if _marketplace_host(host) or _non_product_intent(candidate):
        return out

    raw_pattern = re.compile(re.escape(raw), re.I)
    title_raw = raw_pattern.search(title)
    if title_raw:
        _add_prefix_evidence(out, title[:title_raw.start()], "title", 3.5, 3.8)
    elif _is_strong_code(raw) and (snippet_match or url_match or _candidate_has_full_raw(candidate, raw)):
        segment = re.split(r"[|:–—•]", title)[0].strip()
        brand = _clean_brand_phrase(segment)
        if brand:
            out.append((brand, 1.7, "leading_title_brand"))
        multi = _clean_brand_phrase(segment, multiword=True)
        if multi and multi != brand:
            out.append((multi, 1.9, "leading_multiword_title_brand"))

    snippet_raw = raw_pattern.search(snippet)
    if snippet_raw:
        _add_prefix_evidence(out, snippet[:snippet_raw.start()], "snippet", 3.0, 3.3)

    return out


def _rank_brand_scores(identity: ProductIdentity, candidates: list[SearchCandidate], page_signals: list[PageIdentitySignal] | None = None):
    raw = _raw_value(identity)
    filtered = filter_bootstrap_candidates(raw, candidates)
    labels: dict[str, str] = {}
    hosts_by_brand: dict[str, set[str]] = {}
    official_hosts: dict[str, tuple[float, str]] = {}
    model_by_brand: dict[str, list[tuple[float, str]]] = {}
    host_contribs: dict[str, dict[str, float]] = defaultdict(dict)
    explicit_keys: set[str] = set()

    def add(brand: str | None, score: float, host: str, *, model: str | None = None, official_hint: bool = False, explicit: bool = False):
        brand = str(brand or "").strip()
        key = _compact(brand)
        if not key or len(key) < 2:
            return
        labels.setdefault(key, brand)
        host_key = host or f"unknown:{key}"
        if _marketplace_host(host):
            score -= 2.5
        host_contribs[key][host_key] = max(host_contribs[key].get(host_key, float("-inf")), score)
        if host:
            hosts_by_brand.setdefault(key, set()).add(host)
        if explicit:
            explicit_keys.add(key)
        if model:
            model_by_brand.setdefault(key, []).append((score, model))
        if official_hint and host and not _marketplace_host(host):
            current = official_hosts.get(key)
            if current is None or score > current[0]:
                official_hosts[key] = (score, host)

    for candidate in filtered:
        host = (urlparse(candidate.url).hostname or "").lower().removeprefix("www.")
        title_match, snippet_match, url_match = _candidate_text_matches_raw(candidate, raw)
        base = 2.0 if title_match else 1.0
        if snippet_match:
            base += 0.5
        if url_match:
            base += 0.5
        for brand, evidence_score, reason in _brand_evidence(candidate, raw):
            hay = key_norm(f"{candidate.title} {candidate.snippet}")
            score = base + evidence_score + (0.8 if any(x in hay for x in ("official", "manufacturer", "fabricante")) else 0.0)
            is_explicit = reason == "explicit_brand_label"
            if not is_explicit and _label_matches_host(brand, host):
                score = min(score, 2.0)
            add(brand, score, host, explicit=is_explicit)

    for signal in page_signals or []:
        if not signal.material or not signal.exact_raw_match:
            continue
        host = (urlparse(signal.url or "").hostname or "").lower().removeprefix("www.")
        brand = signal.brand or signal.manufacturer
        if not brand:
            continue
        score = 7.0 if signal.structured_brand else 4.5
        if signal.strong_identifier_match:
            score += 3.0
        if signal.model and _candidate_has_full_raw(SearchCandidate(signal.url, signal.model, ""), raw):
            score += 1.5
        if signal.product_name and _candidate_has_full_raw(SearchCandidate(signal.url, signal.product_name, ""), raw):
            score += 1.5
        if signal.authority_owned:
            score += 2.5
        add(
            brand,
            score,
            host,
            model=signal.model or signal.product_name,
            official_hint=bool(signal.authority_owned and signal.structured_brand),
            explicit=bool(signal.structured_brand),
        )

    scores = {
        key: round(sum(max(0.0, value) for value in contributions.values()), 6)
        for key, contributions in host_contribs.items()
    }

    for long_key in list(scores):
        words = str(labels.get(long_key) or "").split()
        if len(words) != 2 or not _brand_like_second_token(words[1]):
            continue
        short_key = _compact(words[0])
        long_hosts = hosts_by_brand.get(long_key, set())
        short_hosts = hosts_by_brand.get(short_key, set())
        if (
            short_key in scores
            and short_key != long_key
            and len(long_hosts) >= 2
            and short_hosts
            and short_hosts.issubset(long_hosts)
            and (long_key in explicit_keys or scores[long_key] >= scores[short_key] + 1.0)
        ):
            scores.pop(short_key, None)

    return scores, labels, hosts_by_brand, official_hosts, model_by_brand


def _finalize_resolution(identity: ProductIdentity, candidates: list[SearchCandidate], page_signals: list[PageIdentitySignal] | None = None) -> IdentityBootstrapResult:
    raw = _raw_value(identity)
    if not raw:
        return IdentityBootstrapResult(identity=identity.model_copy(deep=True), status="IDENTITY_UNRESOLVED", reason="NO_RAW_IDENTITY")
    if identity.brand:
        return IdentityBootstrapResult(identity=identity.model_copy(deep=True), status="RESOLVED", confidence=1.0, reason="BRAND_PROVIDED", raw_input=raw)

    filtered = filter_bootstrap_candidates(raw, candidates)
    scores, labels, hosts_by_brand, official_hosts, model_by_brand = _rank_brand_scores(identity, filtered, page_signals)
    if not scores:
        return IdentityBootstrapResult(
            identity=identity.model_copy(deep=True), status="IDENTITY_UNRESOLVED", reason="INSUFFICIENT_EVIDENCE",
            raw_input=raw, search_results_found=len(filtered), candidate_urls=[c.url for c in filtered],
        )

    ranked = sorted(scores.items(), key=lambda row: row[1], reverse=True)
    best_key, best_score = ranked[0]
    runner_key = ranked[1][0] if len(ranked) > 1 else None
    runner_score = ranked[1][1] if len(ranked) > 1 else 0.0
    host_count = len(hosts_by_brand.get(best_key, set()))
    runner_host_count = len(hosts_by_brand.get(runner_key, set())) if runner_key else 0
    margin = best_score - runner_score
    matching_page = [
        s for s in (page_signals or [])
        if _compact(s.brand or s.manufacturer) == best_key and s.material and s.exact_raw_match
    ]
    has_page = bool(matching_page)
    page_authority = any(s.authority_owned for s in matching_page)

    decisive_page = has_page and best_score >= 9.0 and margin >= 2.5
    decisive_cross_source = host_count >= 2 and best_score >= 8.5 and (
        margin >= 2.5 or best_score >= max(1.0, runner_score) * 1.35
    )
    decisive_host_diversity = host_count >= 3 and runner_host_count <= 1 and best_score >= 7.5 and best_score > runner_score
    decisive_dominance = best_score >= 18.0 and margin >= 9.0 and best_score >= max(1.0, runner_score) * 1.7
    decisive_serp = not page_signals and host_count >= 2 and best_score >= 8.5 and margin >= 2.5
    resolved = decisive_page or decisive_cross_source or decisive_host_diversity or decisive_dominance or decisive_serp

    if not resolved:
        return IdentityBootstrapResult(
            identity=identity.model_copy(deep=True), status="IDENTITY_UNRESOLVED",
            confidence=min(0.74, best_score / max(1.0, best_score + runner_score + 2.0)),
            reason="AMBIGUOUS_BRAND" if len(ranked) > 1 and margin < 2.5 else "INSUFFICIENT_EVIDENCE",
            raw_input=raw, search_results_found=len(filtered), candidate_urls=[c.url for c in filtered],
            brand_scores={labels[k]: round(v, 3) for k, v in scores.items()},
            brand_hosts={labels[k]: len(hosts_by_brand.get(k, set())) for k in scores},
        )

    learned = identity.model_copy(deep=True)
    learned.brand = labels[best_key]
    if not learned.model:
        observed_models = sorted(model_by_brand.get(best_key, []), reverse=True)
        observed_model = observed_models[0][1] if observed_models else None
        if observed_model and _candidate_has_full_raw(SearchCandidate("https://model.invalid", observed_model, ""), raw):
            learned.model = raw if not _is_strong_code(raw) else observed_model
        elif not _is_strong_code(raw):
            learned.model = raw

    confidence = min(0.99, 0.74 + min(best_score, 20.0) * 0.011 + min(host_count, 3) * 0.025 + (0.03 if page_authority else 0.0))
    return IdentityBootstrapResult(
        identity=learned,
        status="RESOLVED",
        confidence=confidence,
        reason="PAGE_BACKED_IDENTITY_RESOLUTION" if has_page else "CROSS_SOURCE_BRAND_RESOLUTION",
        official_domain_hint=official_hosts.get(best_key, (0.0, None))[1],
        raw_input=raw,
        search_results_found=len(filtered),
        candidate_urls=[c.url for c in filtered],
        brand_scores={labels[k]: round(v, 3) for k, v in scores.items()},
        brand_hosts={labels[k]: len(hosts_by_brand.get(k, set())) for k in scores},
        hardcoded=False,
    )


def resolve_identity_from_candidates(identity: ProductIdentity, candidates: list[SearchCandidate]) -> IdentityBootstrapResult:
    return _finalize_resolution(identity, candidates, None)


def resolve_identity_with_page_signals(identity: ProductIdentity, candidates: list[SearchCandidate], page_signals: list[PageIdentitySignal]) -> IdentityBootstrapResult:
    result = _finalize_resolution(identity, candidates, page_signals)
    result.page_probes_attempted = len(page_signals)
    result.page_probes_succeeded = sum(1 for s in page_signals if s.material and s.exact_raw_match)
    result.page_signals = [
        {
            "url": s.url,
            "brand": s.brand,
            "manufacturer": s.manufacturer,
            "model": s.model,
            "product_name": s.product_name,
            "exact_raw_match": s.exact_raw_match,
            "strong_identifier_match": s.strong_identifier_match,
            "material": s.material,
            "structured_brand": s.structured_brand,
            "authority_owned": s.authority_owned,
            "reason": s.reason,
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
            if target == _compact(str(value or "")):
                return True
    return False


def _probe_candidate_page(identity: ProductIdentity, candidate: SearchCandidate) -> PageIdentitySignal:
    raw = _raw_value(identity)
    _max_probes, probe_timeout = identity_probe_budget()
    try:
        fetched = fetch_page(candidate.url, timeout=probe_timeout, browser_fallback=False)
        if int(fetched.status_code or 0) >= 400 or not fetched.html:
            return PageIdentitySignal(url=candidate.url, reason=f"HTTP_{fetched.status_code}")
        page = extract_page(fetched.html, fetched.final_url, [raw] if raw else [])
        observed = derive_observed_identity(identity, page)
        page_assessment = classify_page_type(derive_page_signals(fetched.html, fetched.final_url, page))
        page_text = str(page.get("text") or "")
        exact_raw = _candidate_has_full_raw(SearchCandidate(fetched.final_url, page_text[:4000], ""), raw)
        strong_match = False
        if _is_strong_code(raw):
            observed_ids = [*observed.mpns, *observed.gtins, *observed.eans, *observed.upcs]
            strong_match = any(_compact(raw) == _compact(x) for x in observed_ids) or exact_raw
        brand = observed.brand
        authority_owned = False
        if brand and exact_raw:
            branded_expected = identity.model_copy(deep=True)
            branded_expected.brand = brand
            authority = classify_source_authority(
                derive_authority_signals(branded_expected, fetched.html, fetched.final_url, page)
            )
            authority_owned = authority.source_class in {"manufacturer", "manufacturer_support"}
        return PageIdentitySignal(
            url=fetched.final_url or candidate.url,
            brand=brand,
            model=observed.model,
            product_name=observed.product_name,
            exact_raw_match=exact_raw,
            strong_identifier_match=strong_match,
            material=bool(page_assessment.material_allowed),
            structured_brand=_structured_brand_present(page, brand),
            authority_owned=authority_owned,
            reason="OK" if page_assessment.material_allowed else f"PAGE_TYPE_{page_assessment.page_type}",
        )
    except Exception as exc:
        return PageIdentitySignal(url=candidate.url, reason=f"{type(exc).__name__}")


def _candidate_probe_rank(candidate: SearchCandidate, raw: str) -> tuple:
    title_match, snippet_match, url_match = _candidate_text_matches_raw(candidate, raw)
    host = (urlparse(candidate.url or "").hostname or "").lower()
    marketplace = _marketplace_host(host)
    technical = any(token in key_norm(f"{candidate.title} {candidate.snippet} {candidate.url}") for token in (
        "specification", "specifications", "datasheet", "manual", "support", "product",
    ))
    return (0 if title_match else 1, 0 if url_match else 1, 0 if technical else 1, 1 if marketplace else 0, 0 if snippet_match else 1)


def _probe_top_candidates(identity: ProductIdentity, candidates: list[SearchCandidate], *, max_probes: int | None = None) -> list[PageIdentitySignal]:
    raw = _raw_value(identity)
    budget_probes, _timeout = identity_probe_budget()
    max_probes = budget_probes if max_probes is None else max(0, min(max_probes, budget_probes))
    if max_probes <= 0:
        return []
    ordered = sorted(filter_bootstrap_candidates(raw, candidates), key=lambda c: _candidate_probe_rank(c, raw))
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


def _search_raw(query: str, raw: str, *, limit: int = 18, timeout: int = 8) -> list[SearchCandidate]:
    static = [SearchCandidate(url=u, title=t, snippet=s) for u, t, s in _provider_search(query, timeout)]
    filtered = filter_bootstrap_candidates(raw, static)
    if len(filtered) >= min(4, limit):
        return filtered[:limit]
    try:
        browser_rows = browser_search(query, timeout=max(5, min(timeout, 8)), limit=max(8, limit))
    except Exception:
        browser_rows = []
    browser_candidates = [SearchCandidate(url=u, title=t, snippet=s) for u, t, s in browser_rows]
    combined = filter_bootstrap_candidates(raw, [*filtered, *browser_candidates])
    return combined[:limit]


def _annotate_result(result: IdentityBootstrapResult, executed: list[str], collected: list[SearchCandidate], page_signals: list[PageIdentitySignal]):
    result.queries_executed = list(executed)
    result.search_results_found = len(collected)
    result.candidate_urls = [c.url for c in collected]
    result.page_probes_attempted = len(page_signals)
    result.page_probes_succeeded = sum(1 for s in page_signals if s.material and s.exact_raw_match)
    result.page_signals = [
        {
            "url": s.url,
            "brand": s.brand,
            "manufacturer": s.manufacturer,
            "model": s.model,
            "product_name": s.product_name,
            "exact_raw_match": s.exact_raw_match,
            "strong_identifier_match": s.strong_identifier_match,
            "material": s.material,
            "structured_brand": s.structured_brand,
            "authority_owned": s.authority_owned,
            "reason": s.reason,
        }
        for s in page_signals
    ]
    return result


def bootstrap_identity(identity: ProductIdentity, *, limit_per_query: int = 18, timeout: int = 8) -> IdentityBootstrapResult:
    raw = _raw_value(identity)
    base_queries = build_bootstrap_queries(identity)
    if not raw or not base_queries:
        return IdentityBootstrapResult(identity=identity.model_copy(deep=True), status="IDENTITY_UNRESOLVED", reason="NO_RAW_IDENTITY")

    collected: list[SearchCandidate] = []
    seen_urls: set[str] = set()
    executed: list[str] = []
    page_signals: list[PageIdentitySignal] = []
    probed_urls: set[str] = set()
    probe_limit, _probe_timeout = identity_probe_budget()

    def search_and_add(query: str):
        if not query or query in executed:
            return
        executed.append(query)
        for row in _search_raw(query, raw, limit=limit_per_query, timeout=timeout):
            if row.url not in seen_urls:
                seen_urls.add(row.url)
                collected.append(row)

    search_and_add(base_queries[0])

    if not collected:
        for query in build_discovery_fallback_queries(raw)[:2]:
            search_and_add(query)
            if collected:
                break

    result = resolve_identity_from_candidates(identity, collected)

    if result.status != "RESOLVED":
        for query in build_context_queries(raw, derive_context_terms(raw, collected))[:2]:
            search_and_add(query)
        result = resolve_identity_from_candidates(identity, collected)

    fresh_pool = [c for c in collected if c.url not in probed_urls]
    fresh_signals = _probe_top_candidates(identity, fresh_pool, max_probes=probe_limit)
    page_signals.extend(fresh_signals)
    for signal in fresh_signals:
        probed_urls.add(signal.url)
    if page_signals:
        page_result = resolve_identity_with_page_signals(identity, collected, page_signals)
        if page_result.status == "RESOLVED" or result.status != "RESOLVED":
            result = page_result

    if result.status != "RESOLVED":
        for query in base_queries[1:]:
            search_and_add(query)
            serp_result = resolve_identity_from_candidates(identity, collected)
            if serp_result.status == "RESOLVED":
                result = serp_result
                break
            if len(page_signals) < probe_limit:
                fresh_pool = [c for c in collected if c.url not in probed_urls]
                new_signals = _probe_top_candidates(identity, fresh_pool, max_probes=probe_limit - len(page_signals))
                page_signals.extend(new_signals)
                for signal in new_signals:
                    probed_urls.add(signal.url)
                if page_signals:
                    result = resolve_identity_with_page_signals(identity, collected, page_signals)
                    if result.status == "RESOLVED":
                        break
            else:
                result = serp_result

    return _annotate_result(result, executed, collected, page_signals)
