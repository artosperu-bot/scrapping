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
    "downloads", "new", "used", "refurbished", "review", "reviews", "with", "for", "from",
    "the", "and", "black", "white", "blue", "red", "green", "gray", "grey", "silver",
    "gold", "azul", "negro", "blanco", "rojo", "wireless", "wired", "headphone",
    "headphones", "headset", "earphones", "audifono", "audifonos", "auriculares", "speaker",
    "smartphone", "laptop", "monitor", "printer", "gaming", "pc", "waterproof", "sports",
    "bluetooth", "usb", "inalambrico", "inalambricos",
}
_BRAND_GENERIC = _GENERIC | {
    "sensor", "cable", "adapter", "charger", "camera", "device", "technology", "audio",
    "model", "series", "serie", "www", "http", "https", "com", "net", "org",
}
_MODEL_DESCRIPTOR_STOP = _GENERIC | {
    "hi", "res", "hires", "on", "over", "ear", "in", "compatible", "compatibility",
    "ip65", "ip67", "ip68", "ip69", "tws", "true", "stereo", "color", "colour",
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
    return str(
        identity.mpn
        or identity.ean
        or identity.upc
        or identity.gtin
        or identity.sku
        or identity.model
        or ""
    ).strip()


def _root(host: str | None) -> str:
    host = str(host or "").lower().removeprefix("www.").split(":", 1)[0]
    parts = [part for part in host.split(".") if part]
    if len(parts) <= 2:
        return host
    if len(parts[-1]) == 2 and parts[-2] in {"com", "co", "net", "org"} and len(parts) >= 3:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def _root_label(host: str | None) -> str:
    root = _root(host)
    return _compact(root.split(".", 1)[0] if root else "")


def _tokenize(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", key_norm(unquote(value or "")))


def stable_model_core(value: str | None, *, raw: str | None = None, brand: str | None = None) -> str:
    """Return a short product-model core without colour/category/marketing tails."""
    text = unquote(str(value or "")).strip()
    if not text:
        return ""
    for removable in (raw, brand):
        token = str(removable or "").strip()
        if token:
            text = re.sub(re.escape(token), " ", text, flags=re.I)

    tokens = re.findall(r"[A-Za-z0-9]+", text)
    core: list[str] = []
    for token in tokens:
        normalized = key_norm(token)
        if not normalized:
            continue
        if core and normalized in _MODEL_DESCRIPTOR_STOP:
            break
        if not core and normalized in _MODEL_DESCRIPTOR_STOP:
            continue
        core.append(token)
        if len(core) >= 5:
            break

    while core and key_norm(core[-1]) in _MODEL_DESCRIPTOR_STOP:
        core.pop()
    candidate = " ".join(core).strip()
    if len(core) < 2 or _compact(candidate) == _compact(raw):
        return ""
    return candidate


def _descriptive_title_signal(title: str) -> bool:
    useful = [token for token in _tokenize(title) if token not in _GENERIC and len(token) >= 2]
    return len(useful) >= 2 and (
        any(any(ch.isdigit() for ch in token) for token in useful) or len(useful) >= 3
    )


def _normalize_provider_candidate(row) -> SearchCandidate | None:
    if isinstance(row, SearchCandidate):
        return row
    if isinstance(row, (tuple, list)) and row:
        url = str(row[0] or "").strip()
        if not url:
            return None
        return SearchCandidate(
            url=url,
            title=str(row[1] or "") if len(row) > 1 else "",
            snippet=str(row[2] or "") if len(row) > 2 else "",
        )
    if isinstance(row, dict):
        url = str(row.get("url") or "").strip()
        if not url:
            return None
        return SearchCandidate(
            url=url,
            title=str(row.get("title") or ""),
            snippet=str(row.get("snippet") or ""),
            score=float(row.get("score") or 0.0),
            likely_official=bool(row.get("likely_official", False)),
        )
    return None


def _candidate_bound_to_raw(candidate: SearchCandidate, raw: str) -> bool:
    target = _compact(raw)
    if not target:
        return False
    if target in _compact(candidate.title) or target in _compact(candidate.url):
        return True
    # Snippets are allowed only as a binding signal. The title still has to carry
    # descriptive product identity so a generic search-result echo cannot win.
    return bool(target in _compact(candidate.snippet) and _descriptive_title_signal(candidate.title))


def _title_tokens(candidate: SearchCandidate, raw: str) -> list[str]:
    text = unquote(str(candidate.title or ""))
    if raw:
        text = re.sub(re.escape(raw), " ", text, flags=re.I)
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
    clean = [token for token in tokens[:6] if token not in _BRAND_GENERIC and len(token) >= 2]
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


def _descriptive_brand_hint(value: str | None, raw: str) -> str | None:
    text = str(value or "").strip()
    if not text or _compact(text) == _compact(raw):
        return None
    for token in _tokenize(text)[:4]:
        if token in _BRAND_GENERIC or any(ch.isdigit() for ch in token):
            continue
        if len(token) >= 2:
            return token
    return None


def _plausible_brand_hint(value: str | None) -> bool:
    tokens = _tokenize(value or "")
    return bool(tokens and len(tokens) <= 3 and all(token not in _BRAND_GENERIC for token in tokens))


def _select_brand(
    candidates: list[SearchCandidate], raw: str, current: str | None
) -> tuple[str | None, int, str | None]:
    domains_by_phrase: dict[str, set[str]] = defaultdict(set)
    display: dict[str, str] = {}
    host_matches: Counter[str] = Counter()
    current_key = _compact(current)

    for candidate in candidates:
        domain = _root(urlparse(candidate.url).hostname)
        root_label = _root_label(domain)
        title_tokens = _title_tokens(candidate, raw)
        for phrase in _brand_ngrams(title_tokens):
            key = _compact(phrase)
            if not key:
                continue
            display.setdefault(key, phrase)
            if domain:
                domains_by_phrase[key].add(domain)
            if root_label and key == root_label:
                host_matches[key] += 1

        # Single-token candidates help a stable brand beat a longer title prefix,
        # but still need cross-domain support unless already trusted as current.
        for token in title_tokens[:6]:
            if token in _BRAND_GENERIC or any(ch.isdigit() for ch in token) or len(token) < 2:
                continue
            key = _compact(token)
            if not key:
                continue
            display.setdefault(key, token)
            if domain:
                domains_by_phrase[key].add(domain)
            if root_label and key == root_label:
                host_matches[key] += 1

    ranked: list[tuple[float, int, int, str]] = []
    for key, domains in domains_by_phrase.items():
        support = len(domains)
        words = display[key].split()
        is_current = bool(
            current_key
            and (key == current_key or current_key.startswith(key) or key.startswith(current_key))
        )
        # Critical anti-retailer rule: hostname coincidence from one domain is not
        # enough to invent a product brand.
        if support < 2 and not is_current:
            continue
        score = support * 10.0
        if is_current:
            score += 12.0
        if support >= 2:
            score += min(host_matches[key], support) * 1.5
            if host_matches[key] and len(words) > 1:
                score += 2.5
        score -= max(0, len(words) - 1) * 1.25
        ranked.append((score, support, -len(words), key))

    if not ranked:
        return current, 0, None
    ranked.sort(reverse=True)
    _score, support, _neg_words, key = ranked[0]
    brand = display.get(key, current or key)

    official_domain = None
    brand_key = _compact(brand)
    for candidate in candidates:
        domain = _root(urlparse(candidate.url).hostname)
        if brand_key and _root_label(domain) == brand_key:
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
            words = tokens[start : start + length]
            if all(word in _GENERIC for word in words):
                continue
            out.append((" ".join(words), start))
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
        if words and all(key_norm(word) in _MODEL_DESCRIPTOR_STOP for word in words):
            continue
        score = support * 10.0
        score += 4.0 if any(any(ch.isdigit() for ch in word) for word in words) else 0.0
        score += max(0, 4 - earliest.get(key, 4)) * 1.5
        score += min(len(words), 4) * 0.6
        score -= max(0, len(words) - 4) * 1.4
        ranked.append((score, support, -abs(len(words) - 3), key))

    if not ranked:
        return None, 0
    ranked.sort(reverse=True)
    _score, support, _preference, key = ranked[0]
    return display[key], support


def refine_code_identity(
    original: ProductIdentity,
    current: ProductIdentity,
    *,
    timeout: int = 7,
    max_queries: int = 2,
) -> IdentityRefinement:
    """Bounded MPN/code refinement using corroborated cross-domain web evidence."""
    raw = _raw(original)
    if not raw:
        return IdentityRefinement(current, None, 0, 0, 0)

    explicit_brand = str(current.brand or current.manufacturer or "").strip()
    descriptive_brand = _descriptive_brand_hint(current.model or current.product_name, raw)
    brand_hint = explicit_brand or descriptive_brand or ""

    queries = [f'"{raw}"']
    if brand_hint:
        queries.append(f'"{raw}" "{brand_hint}"')
    else:
        queries.append(f'"{raw}" product')

    collected: list[SearchCandidate] = []
    seen: set[str] = set()
    for query in queries[: max(1, int(max_queries))]:
        for provider_row in _provider_search(query, max(5, min(int(timeout), 8))):
            candidate = _normalize_provider_candidate(provider_row)
            if candidate is None or candidate.url in seen or not _candidate_bound_to_raw(candidate, raw):
                continue
            seen.add(candidate.url)
            collected.append(candidate)

    brand, brand_support, official_domain = _select_brand(collected, raw, brand_hint or None)
    hint_key = _compact(brand_hint)
    selected_key = _compact(brand)
    aligned = bool(
        not hint_key
        or not selected_key
        or hint_key == selected_key
        or hint_key.startswith(selected_key)
        or selected_key.startswith(hint_key)
    )
    if brand_hint and _plausible_brand_hint(brand_hint) and not aligned:
        brand = brand_hint
        brand_support = 0
        official_domain = None

    model, model_support = _select_model(collected, raw, brand)
    updates: dict[str, str] = {}
    if brand and (_compact(brand) != _compact(current.brand) or not current.brand):
        updates["brand"] = brand
        if not current.manufacturer:
            updates["manufacturer"] = brand

    current_model = str(current.model or current.product_name or "").strip()
    needs_model = bool(
        not current_model
        or _compact(current_model) == _compact(raw)
        or len(current_model) > 70
    )
    stable_current = stable_model_core(current_model, raw=raw, brand=brand or brand_hint)
    if needs_model and stable_current:
        updates["model"] = stable_current
        updates["product_name"] = (
            f"{brand or brand_hint} {stable_current}" if (brand or brand_hint) else stable_current
        ).strip()

    if model and _compact(model) != _compact(raw) and needs_model:
        selected_core = stable_model_core(model, raw=raw, brand=brand or brand_hint) or model
        if not all(token in _MODEL_DESCRIPTOR_STOP for token in _tokenize(selected_core)):
            updates["model"] = selected_core
            updates["product_name"] = (
                f"{brand or brand_hint} {selected_core}" if (brand or brand_hint) else selected_core
            ).strip()

    identity = current.model_copy(update=updates) if updates else current
    return IdentityRefinement(
        identity=identity,
        official_domain_hint=official_domain,
        candidates_used=len(collected),
        brand_support_domains=brand_support,
        model_support_domains=model_support,
    )
