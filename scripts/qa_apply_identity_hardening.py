from pathlib import Path

path = Path('src/product_intelligence/identity_bootstrap.py')
text = path.read_text(encoding='utf-8')

old = '''def _brand_candidate_quality(brand: str | None, raw: str) -> bool:
    brand = str(brand or "").strip()
    if not brand:
        return False
    norm = key_norm(brand)
    compact = _compact(brand)
    if not compact or len(compact) < 2 or compact == _compact(raw):
        return False
    if norm in _GENERIC_BRAND_WORDS or norm in _CONTEXT_STOPWORDS:
        return False
    if _looks_like_sibling_identifier(brand, raw):
        return False
    if re.fullmatch(r"\\d+(?:w|kw|gb|tb|hz|mhz|ghz|mp|mah)?", norm, re.I):
        return False
    words = norm.split()
    if words and (words[0] in _GENERIC_BRAND_WORDS or words[-1] in _GENERIC_BRAND_WORDS):
        return False
    return True
'''
new = '''def _brand_candidate_quality(brand: str | None, raw: str) -> bool:
    brand = str(brand or "").strip()
    if not brand:
        return False
    norm = key_norm(brand)
    compact = _compact(brand)
    if not compact or len(compact) < 2 or compact == _compact(raw):
        return False
    generic_keys = {_compact(value) for value in (*_GENERIC_BRAND_WORDS, *_CONTEXT_STOPWORDS)}
    if compact in generic_keys:
        return False
    if _looks_like_sibling_identifier(brand, raw):
        return False
    if re.fullmatch(r"\\d+(?:w|kw|gb|tb|hz|mhz|ghz|mp|mah)?", norm, re.I):
        return False
    words = re.findall(r"[A-Za-z0-9&+_-]+", brand)
    if words and (_compact(words[0]) in generic_keys or _compact(words[-1]) in generic_keys):
        return False
    return True
'''
assert old in text, 'brand quality block not found'
text = text.replace(old, new, 1)

old = '''    provisional: list[tuple[SearchCandidate, str, float, str, str, str, float, bool]] = []
    nonself_roots: dict[str, set[str]] = defaultdict(set)
    context_roots: set[str] = set()
'''
new = '''    provisional: list[tuple[SearchCandidate, str, float, str, str, str, float, bool]] = []
    nonself_roots: dict[str, set[str]] = defaultdict(set)
    context_roots: set[str] = set()
    cross_domain_seed: dict[str, dict[str, tuple[str, float]]] = defaultdict(dict)
'''
assert old in text, 'rank init block not found'
text = text.replace(old, new, 1)

old = '''        for brand, evidence_score, reason in _brand_evidence(candidate, raw):
            if not _brand_candidate_quality(brand, raw):
                continue
            key = _compact(brand)
            self_like = _label_matches_host(brand, host)
            if not self_like and root and role not in {"SOCIAL", "MARKETPLACE", "NON_PRODUCT_NOISE"}:
                nonself_roots[key].add(root)
            hay = key_norm(f"{candidate.title} {candidate.snippet}")
            score = base + evidence_score + (0.8 if any(x in hay for x in ("official", "manufacturer", "fabricante")) else 0.0)
            provisional.append((candidate, brand, score, reason, host, role, context, self_like))
'''
new = '''        evidence_rows = _brand_evidence(candidate, raw)
        for brand, evidence_score, reason in evidence_rows:
            if not _brand_candidate_quality(brand, raw):
                continue
            key = _compact(brand)
            self_like = _label_matches_host(brand, host)
            if root and role not in {"SOCIAL", "NON_PRODUCT_NOISE"}:
                seed_score = base + evidence_score
                current_seed = cross_domain_seed[key].get(root)
                if current_seed is None or seed_score > current_seed[1]:
                    cross_domain_seed[key][root] = (brand, seed_score)
            if not self_like and root and role not in {"SOCIAL", "MARKETPLACE", "NON_PRODUCT_NOISE"}:
                nonself_roots[key].add(root)
            hay = key_norm(f"{candidate.title} {candidate.snippet}")
            score = base + evidence_score + (0.8 if any(x in hay for x in ("official", "manufacturer", "fabricante")) else 0.0)
            provisional.append((candidate, brand, score, reason, host, role, context, self_like))
'''
assert old in text, 'candidate evidence block not found'
text = text.replace(old, new, 1)

old = '''    coherent_context = len(context_roots) >= 2
'''
new = '''    # Discovery evidence from independent domains may seed a brand candidate even when
    # individual pages are retailers/marketplaces. This is never manufacturer proof:
    # it only prevents the strict role filter from deleting a repeatedly observed
    # leading brand before page/content validation gets a chance to verify it.
    for key, root_rows in cross_domain_seed.items():
        if len(root_rows) < 2:
            continue
        for root, (brand, seed_score) in root_rows.items():
            add(brand, max(2.0, min(seed_score, 6.0)), root)

    coherent_context = len(context_roots) >= 2
'''
assert old in text, 'coherent context marker not found'
text = text.replace(old, new, 1)

old = '''    scores = {
        key: round(sum(max(0.0, value) for value in contributions.values()), 6)
        for key, contributions in host_contribs.items()
    }

    for long_key in list(scores):
'''
new = '''    scores = {
        key: round(sum(max(0.0, value) for value in contributions.values()), 6)
        for key, contributions in host_contribs.items()
    }

    # Exact page-backed identity is stronger than SERP family/product-line wording.
    # A single trusted structured/owned page, or the same strong-ID brand observed on
    # two independent material pages, receives a bounded bonus. Hostname similarity
    # alone never qualifies for this path.
    trusted_page_keys: set[str] = set()
    strong_page_roots: dict[str, set[str]] = defaultdict(set)
    for signal in page_signals or []:
        if not signal.material or not signal.exact_raw_match:
            continue
        brand = signal.brand or signal.manufacturer
        if not _brand_candidate_quality(brand, raw):
            continue
        key = _compact(brand)
        root = _registrable_domain(urlparse(signal.url or "").hostname)
        if signal.strong_identifier_match and root:
            strong_page_roots[key].add(root)
        if signal.structured_brand or signal.authority_owned:
            trusted_page_keys.add(key)
    for key in list(scores):
        if key in trusted_page_keys or len(strong_page_roots.get(key, set())) >= 2:
            scores[key] = round(scores[key] + 6.0, 6)

    for long_key in list(scores):
'''
assert old in text, 'scores block not found'
text = text.replace(old, new, 1)

old = '''        if long_key not in explicit_keys and len(short_hosts) >= 2 and same_evidence_cluster:
            scores.pop(long_key, None)
            continue
'''
new = '''        if long_key not in explicit_keys and len(short_hosts) >= 2 and same_evidence_cluster:
            # Do not truncate a genuinely corroborated two-word brand merely because
            # its first token is also present. Prefer the short form only when it has
            # broader independent-host support or the long phrase is materially weaker.
            short_has_broader_support = len(short_hosts) > len(long_hosts)
            long_is_materially_weaker = scores[long_key] < scores[short_key] * 0.90
            if short_has_broader_support or long_is_materially_weaker:
                scores.pop(long_key, None)
            else:
                scores.pop(short_key, None)
            continue
'''
assert old in text, 'long-short collapse block not found'
text = text.replace(old, new, 1)

path.write_text(text, encoding='utf-8')
print('IDENTITY_HARDENING_APPLIED')
