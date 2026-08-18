from __future__ import annotations

from dataclasses import dataclass
import re
from pathlib import Path
from urllib.parse import unquote, urlparse


EXACT_RELATIONSHIPS = {"EXACT_SKU", "EXACT_MODEL"}

_LANGUAGE_ALIASES = {
    "ES": {"es", "spa", "spanish", "espanol", "español", "castellano"},
    "EN": {"en", "eng", "english"},
    "DE": {"de", "deu", "ger", "german", "deutsch"},
    "NL": {"nl", "nld", "dut", "dutch", "nederlands"},
    "DA": {"da", "dan", "danish", "dansk"},
    "FR": {"fr", "fra", "fre", "french", "francais", "français"},
    "IT": {"it", "ita", "italian", "italiano"},
    "PT": {"pt", "por", "portuguese", "portugues", "português"},
    "PT-BR": {"ptbr", "pt-br", "pt_br", "brazilianportuguese", "portuguesbrasil", "portuguêsbrasil"},
    "JA": {"ja", "jpn", "japanese"},
    "KO": {"ko", "kor", "korean"},
    "ZH": {"zh", "zho", "chi", "chinese"},
}
_LANGUAGE_PREFERENCE = ("ES", "EN", "PT-BR", "PT", "FR", "DE", "IT", "NL", "DA", "JA", "KO", "ZH")


def _fold(value: str | None) -> str:
    text = unquote(str(value or "")).casefold()
    replacements = str.maketrans({"á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ü": "u", "ñ": "n", "ç": "c"})
    return text.translate(replacements)


def _tokens(value: str | None) -> list[str]:
    return [token for token in re.split(r"[^a-z0-9]+", _fold(value)) if token]


def _language_lookup() -> dict[str, str]:
    lookup: dict[str, str] = {}
    for canonical, aliases in _LANGUAGE_ALIASES.items():
        for alias in aliases:
            lookup[re.sub(r"[^a-z0-9]", "", _fold(alias))] = canonical
    return lookup


_LANGUAGE_LOOKUP = _language_lookup()


def detect_document_language(title: str | None, url: str | None = None) -> str | None:
    """Infer document language from filename/title/path tokens only.

    Language metadata affects grouping/preference, never product identity.
    """
    candidates: list[str] = []
    raw_title = str(title or "")
    if raw_title:
        candidates.extend(_tokens(Path(raw_title).stem))
    parsed = urlparse(str(url or ""))
    if parsed.path:
        path = unquote(parsed.path)
        candidates.extend(_tokens(Path(path).stem))
        candidates.extend(_tokens("/".join(Path(path).parts[-4:-1])))

    # Compound PT-BR should win before the generic PT token.
    compact_sources = [re.sub(r"[^a-z0-9]", "", _fold(raw_title)), re.sub(r"[^a-z0-9]", "", _fold(parsed.path))]
    if any("ptbr" in source for source in compact_sources):
        return "PT-BR"

    for token in reversed(candidates):
        canonical = _LANGUAGE_LOOKUP.get(re.sub(r"[^a-z0-9]", "", token))
        if canonical:
            return canonical
    return None


def _strip_language_tokens(value: str | None) -> str:
    tokens = _tokens(Path(str(value or "")).stem)
    cleaned: list[str] = []
    for token in tokens:
        compact = re.sub(r"[^a-z0-9]", "", token)
        if compact in _LANGUAGE_LOOKUP:
            continue
        if compact == "ptbr":
            continue
        cleaned.append(token)
    return " ".join(cleaned)


def _canonical_text(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", _fold(value))


def canonical_document_title(title: str | None, url: str | None = None) -> str:
    source = str(title or "").strip()
    if not source:
        source = Path(unquote(urlparse(str(url or "")).path)).name
    cleaned = _strip_language_tokens(source)
    return re.sub(r"\s+", " ", cleaned).strip()


@dataclass(frozen=True)
class DocumentVariant:
    url: str
    title: str = ""
    product_key: str = ""
    document_type: str = "UNKNOWN"
    relationship: str = "UNKNOWN"
    language: str | None = None

    def normalized(self) -> "DocumentVariant":
        language = self.language or detect_document_language(self.title, self.url)
        return DocumentVariant(
            url=self.url,
            title=self.title,
            product_key=self.product_key,
            document_type=self.document_type,
            relationship=self.relationship,
            language=language,
        )


@dataclass(frozen=True)
class CanonicalDocumentGroup:
    canonical_key: str
    product_key: str
    document_type: str
    canonical_title: str
    variants: tuple[DocumentVariant, ...]
    preferred: DocumentVariant

    @property
    def unique_document_count(self) -> int:
        return 1

    @property
    def language_variant_count(self) -> int:
        return len(self.variants)


def _preference_rank(variant: DocumentVariant) -> tuple[int, str]:
    language = variant.language
    if language in _LANGUAGE_PREFERENCE:
        return (_LANGUAGE_PREFERENCE.index(language), variant.url)
    return (len(_LANGUAGE_PREFERENCE) + (1 if language is None else 0), variant.url)


def _group_key(variant: DocumentVariant) -> tuple[str, str, str]:
    normalized = variant.normalized()
    product = _canonical_text(normalized.product_key)
    doc_type = _canonical_text(normalized.document_type or "UNKNOWN") or "unknown"
    title = _canonical_text(canonical_document_title(normalized.title, normalized.url))

    # The product key and explicit document type are load-bearing. Removing the
    # product words from the title lets localized filenames with slightly
    # different separator conventions still collapse safely inside the same
    # exact product + document type boundary.
    if product and title.startswith(product):
        title = title[len(product):]
    return product, doc_type, title or "document"


def group_document_variants(variants: list[DocumentVariant] | tuple[DocumentVariant, ...]) -> tuple[CanonicalDocumentGroup, ...]:
    buckets: dict[tuple[str, str, str], list[DocumentVariant]] = {}
    for raw in variants:
        variant = raw.normalized()
        if str(variant.relationship or "").upper() not in EXACT_RELATIONSHIPS:
            continue
        key = _group_key(variant)
        buckets.setdefault(key, []).append(variant)

    groups: list[CanonicalDocumentGroup] = []
    for key, items in buckets.items():
        ordered = tuple(sorted(items, key=_preference_rank))
        product, doc_type, _title_key = key
        preferred = ordered[0]
        canonical_title = canonical_document_title(preferred.title, preferred.url)
        groups.append(
            CanonicalDocumentGroup(
                canonical_key="|".join(key),
                product_key=preferred.product_key or product,
                document_type=preferred.document_type or doc_type,
                canonical_title=canonical_title,
                variants=ordered,
                preferred=preferred,
            )
        )
    groups.sort(key=lambda group: group.canonical_key)
    return tuple(groups)


def canonical_coverage_count(variants: list[DocumentVariant] | tuple[DocumentVariant, ...]) -> int:
    """Coverage is the number of unique exact documents, not language copies."""
    return len(group_document_variants(variants))
