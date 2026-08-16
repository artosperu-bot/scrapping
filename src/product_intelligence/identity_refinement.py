from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from urllib.parse import unquote, urlparse

from .discovery import SearchCandidate, _provider_search
from .models import ProductIdentity
from .normalize import key_norm

_GENERIC = {
    "buy", "shop", "store", "online", "price", "sale", "official", "product", "products",
    "specification", "specifications", "specs", "manual", "datasheet", "support", "download",
    "new", "used", "refurbished", "review", "reviews", "with", "for", "from", "the", "and",
    "black", "white", "blue", "red", "green", "gray", "grey", "silver", "gold", "azul", "negro",
    "blanco", "rojo", "wireless", "wired", "headphone", "headphones", "headset", "earphones",
    "audifono", "audifonos", "auriculares", "speaker", "smartphone", "laptop", "monitor", "printer",
}
_BRAND_GENERIC = _GENERIC | {
    "gaming", "waterproof", "sports", "sensor", "cable", "adapter", "charger", "camera", "device",
    "technology", "audio", "pc", "usb", "bluetooth", "inalambrico", "inalambricos",
}


@dataclass(frozen=True)
class IdentityRefinement:
    identity: ProductIdentity
    official_domain_hint: str | None
    candidates_used: int
    brand_support_domains: int
    model_support_domains: int


def _compact(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", key_norm(value or ""))


def _raw(identity: ProductIdentity) -> str:
    return str(identity.mpn or identity.ean or identity.upc or identity.gtin or identity.sku or identity.model or "").strip()


def _root(host: str | None) -> str:
    host = str(host or "").lower().removeprefix("www.").split(":", 1)[0]
    parts = [part for part in host.split(".") if part]
    if len(parts) <= 2:
        return host
    if len(parts[-1]) == 2 and parts[-2] in {"com", "co", "net", "org"} and len(parts) >= 3:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def _tokenize(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", key_norm(unquote(value or "")))


def _candidate_bound_to_raw(candidate: SearchCandidate, raw: str) -> bool:
    target = _compact(raw)
    return bool(target and (target in _compact(candidate.title) or target in _compact(candidate.url)))


def _title_tokens(candidate: SearchCandidate, raw: str) -> list[str]:
    text = unquote(str(candidate.title or ""))
    if raw:
        text = re.sub(re.escape(raw), " ", text, flags=re.I)
    # Search titles commonly append store/site labels after separators. Keep the
    # product-facing segment with the richest model-like information.
    segments = [segment.strip() for segment in re.split(r"\s+[|–—]\s+", text) if segment.strip()]
    if segments:
        text = max(segments, key=lambda segment: sum(ch.isdigit() for ch in segment) * 3 + len(segment))
    return _tokenize(text)


def _url_tokens(candidate: SearchCandidate, raw: str) -> list[str]:
    path = unquote(urlparse(candidate.url).path or "")
    if raw:
        path = re.sub(re.escape(raw), " ", path, flags=re.I)
    return _tokenize(path.replace("_", " ").replace("-", " "))


def _brand_ngrams(tokens: list[str]) -> list[str]:
    clean = [token for token in tokens[:5] if token not in _BRAND_GENERIC]
    out: list[str] = []
    for length in (1, 2, 3):
        if len(clean) < length:
            continue
        words = clean[:length]
        if any(any(ch.isdigit() for ch in word) for word in words):
            continue
        phrase = " ".join(words).strip()
        if len(_compact(phrase)) >= 2:
            out.append(phrase)
    return out


def _select_brand(candidates: list[SearchCandidate], raw: str, current: str | None) -> tuple[str | None, int, str | None]:
    domains_by_phrase: dict[str, set[str]] = defaultdict(set)
    display: dict[str, str] = {}
    host_matches: Counter[str] = Counter()

    for candidate in candidates:
        domain = _root(urlparse(candidate.url).hostname)
        root_label = _compact(domain.split(".", 1)[0])
        for phrase in _brand_ngrams(_title_tokens(candidate, raw)):
            key = _compact(phrase)
            display.setdefault(key, phrase)
            if domain:
                domains_by_phrase[key].add(domain)
            if root_label and (key == root_label or (len(key) >= 3 and key in root_label)):
                host_matches[key] += 1

    current_key = _compact(current)
    scores: list[tuple[float, int, int, str]] = []
    for key, domains in domains_by_phrase.items():
        if len(domains) < 2 and not host_matches[key]:
            continue
        words = display[key].split()
        score = len(domains) * 10.0 + host_matches[key] * 8.0
        if current_key and (key == current_key or current_key.startswith(key)):
            score += 3.0
        # Prefer the simplest repeatedly corroborated manufacturer label. Multiword
        # brands still win when their compact form matches a host (e.g. NorthStar).
        score -= max(0, len(words) - 1) * 1.25
        if host_matches[key] and len(words) > 1:
            score += 2.0
        scores.append((score, len(domains), -len(words), key))

    if not scores:
        return current, 0, None
    scores.sort(reverse=True)
    _score, support, _neg_words, key = scores[0]
    brand = display[key]

    official_domain = None
    brand_key = _compact(brand)
    for candidate in candidates:
        domain = _root(urlparse(candidate.url).hostname)
        root_label = _compact(domain.split(".", 1)[0])
        if brand_key and root_label and (brand_key == root_label or brand_key in root_label):
            official_domain = domain
            break
    return brand, support, official_domain


def _model_sequences(candidate: SearchCandidate, raw: str, brand: str | None) -> list[list[str]]:
    sequences: list[list[str]] = []
    brand_tokens = set(_tokenize(brand or ""))
    for tokens in (_title_tokens(candidate, raw), _url_tokens(candidate, raw)):
        clean = [token for token in tokens if token not in brand_tokens and token not in _GENERIC]
        if clean:
            sequences.append(clean[:12])
    return sequences


def _model_ngrams(tokens: list[str]) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    n = len(tokens)
    for start in range(min(n, 5)):
        for length in range(2, min(6, n - start) + 1):
            words = tokens[start:start + length]
            if all(word in _GENERIC for word in words):
                continue
            phrase = " ".join(words)
            has_model_marker = any(any(ch.isdigit() for ch in word) for word in words)
            if not has_model_marker and length < 3:
                continue
            out.append((phrase, start))
    return out


def _select_model(candidates: list[SearchCandidate], raw: str, brand: str | None) -> tuple[str | None, int]:
    domains_by_ngram: dict[str, set[str]] = defaultdict(set)
    display: dict[str, str] = {}
    earliest: dict[str, int] = {}

    for candidate in candidates:
        domain = _root(urlparse(candidate.url).hostname)
        for sequence in _model_sequences(candidate, raw, brand):
            for phrase, start in _model_ngrams(sequence):
                key = _compact(phrase)
                if not key or key == _compact(raw):
                    continue
                display.setdefault(key, phrase)
                earliest[key] = min(earliest.get(key, start), start)
                if domain:
                    domains_by_ngram[key].add(domain)

    ranked: list[tuple[float, int, int, str]] = []
    for key, domains in domains_by_ngram.items():
        support = len(domains)
        if support < 2:
            continue
        phrase = display[key]
        words = phrase.split()
        score = support * 10.0
        score += 4.0 if any(any(ch.isdigit() for ch in word) for word in words) else 0.0
        score += max(0, 4 - earliest.get(key, 4)) * 1.5
        score += min(len(words), 4) * 0.6
        # Long marketing descriptions should lose to the stable shared model phrase.
        score -= max(0, len(words) - 4) * 1.4
        ranked.append((score, support, -abs(len(words) - 3), key))

    if not ranked:
        return None, 0
    ranked.sort(reverse=True)
    _score, support, _pref, key = ranked[0]
    return display[key], support


def refine_code_identity(
    original: ProductIdentity,
    current: ProductIdentity,
    *,
    timeout: int = 7,
    max_queries: int = 2,
) -> IdentityRefinement:
    """Refine an incomplete MPN/code identity using cross-domain SERP consensus.

    This is a bounded refinement of the existing bootstrap result, not an independent
    product resolver. It only considers results whose title or URL is materially bound
    to the strong raw identifier, and never trusts query-echo snippets for identity.
    """
    raw = _raw(original)
    if not raw:
        return IdentityRefinement(current, None, 0, 0, 0)

    brand_hint = str(current.brand or current.manufacturer or "").strip()
    queries = [f'"{raw}"']
    if brand_hint:
        queries.append(f'"{raw}" "{brand_hint}"')
    else:
        queries.append(f'"{raw}" product')

    collected: list[SearchCandidate] = []
    seen: set[str] = set()
    for query in queries[: max(1, int(max_queries))]:
        for candidate in _provider_search(query, max(5, min(int(timeout), 8))):
            if candidate.url in seen or not _candidate_bound_to_raw(candidate, raw):
                continue
            seen.add(candidate.url)
            collected.append(candidate)

    brand, brand_support, official_domain = _select_brand(collected, raw, brand_hint or None)
    model, model_support = _select_model(collected, raw, brand)

    updates = {}
    if brand and (_compact(brand) != _compact(current.brand) or not current.brand):
        updates["brand"] = brand
        if not current.manufacturer:
            updates["manufacturer"] = brand
    if model and _compact(model) != _compact(raw):
        updates["model"] = model
        product_name = str(current.product_name or "").strip()
        if not product_name or _compact(product_name) == _compact(raw) or len(product_name) > 100:
            updates["product_name"] = (f"{brand} {model}" if brand else model).strip()

    identity = current.model_copy(update=updates) if updates else current
    return IdentityRefinement(identity, official_domain, len(collected), brand_support, model_support)
