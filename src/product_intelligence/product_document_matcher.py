from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import re
from urllib.parse import unquote

from .models import ProductIdentity


EXACT_SKU = "EXACT_SKU"
EXACT_MODEL = "EXACT_MODEL"
SIBLING_VARIANT = "SIBLING_VARIANT"
RELATED_FAMILY = "RELATED_FAMILY"
UNRELATED = "UNRELATED"
UNKNOWN = "UNKNOWN"

_ACCEPTED_RELATIONSHIPS = {EXACT_SKU, EXACT_MODEL}

_GENERIC_MODEL_WORDS = {
    "model",
    "series",
    "product",
    "headphone",
    "headphones",
    "earphone",
    "earphones",
    "monitor",
    "printer",
    "laptop",
    "phone",
    "smartphone",
    "tablet",
    "technical",
    "specification",
    "specifications",
    "spec",
    "sheet",
    "manual",
    "guide",
    "user",
    "datasheet",
}

# Generic semantic dimensions. These are deliberately product-agnostic and are
# only one conflict signal; they are not used as a universal product taxonomy.
_CONNECTIVITY_TERMS = {
    "wireless": {"wireless", "bluetooth"},
    "wired": {"wired"},
}
_INTERFACE_TERMS = {
    "usb-c": {"usb-c", "usb c", "usbc", "type-c", "type c"},
    "3.5mm": {"3.5mm", "3.5 mm", "35mm", "aux"},
}


def _norm(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", unquote(str(value or "")).lower())


def _words(value: str | None) -> tuple[str, ...]:
    return tuple(re.findall(r"[a-z0-9]+", unquote(str(value or "")).lower()))


def _word_set(value: str | None) -> set[str]:
    return set(_words(value))


def _phrase_present(value: str | None, haystack: str) -> bool:
    """Match a phrase after punctuation/spacing normalization, not as a substring.

    This deliberately prevents `JBL` from matching a token such as `JBL03` and
    permits model spellings that only differ by separators (ABC-123 / ABC 123).
    """
    needle = _words(value)
    if not needle:
        return False
    words = _words(haystack)
    if len(needle) == 1:
        return needle[0] in words
    width = len(needle)
    return any(words[i : i + width] == needle for i in range(0, len(words) - width + 1))


def _identifier_pattern(identifier: str) -> re.Pattern[str] | None:
    chars = [ch for ch in str(identifier or "") if ch.isalnum()]
    if not chars:
        return None
    body = r"[\s\-_.:/]*".join(re.escape(ch) for ch in chars)
    return re.compile(rf"(?<![A-Za-z0-9]){body}(?![A-Za-z0-9])", re.IGNORECASE)


def _identifier_present(identifier: str, haystack: str) -> bool:
    pattern = _identifier_pattern(identifier)
    return bool(pattern and pattern.search(unquote(haystack)))


def _model_code_candidates(value: str | None) -> set[str]:
    candidates: set[str] = set()
    for raw in re.findall(r"[A-Za-z0-9]+(?:[-_/][A-Za-z0-9]+)*", unquote(str(value or ""))):
        compact = _norm(raw)
        if len(compact) < 3:
            continue
        if any(ch.isalpha() for ch in compact) and any(ch.isdigit() for ch in compact):
            candidates.add(compact)
    return candidates


def _alpha_signature(value: str) -> str:
    return re.sub(r"\d", "", value)


def _similar_model_code(target: str, candidate: str) -> bool:
    if target == candidate:
        return False
    if _alpha_signature(target) and _alpha_signature(target) == _alpha_signature(candidate):
        return True
    return SequenceMatcher(None, target, candidate).ratio() >= 0.78


def _generation_values(value: str | None) -> set[str]:
    text = unquote(str(value or "")).lower()
    found = set(re.findall(r"\bgen(?:eration)?\s*[-:]?\s*(\d{1,2})\b", text))
    return found


def _semantic_values(value: str | None, groups: dict[str, set[str]]) -> set[str]:
    text = unquote(str(value or "")).lower()
    words = _word_set(text)
    found: set[str] = set()
    for canonical, aliases in groups.items():
        for alias in aliases:
            if " " in alias or "-" in alias or "." in alias:
                if _norm(alias) and _norm(alias) in _norm(text):
                    found.add(canonical)
                    break
            elif alias in words:
                found.add(canonical)
                break
    return found


def _model_tokens(value: str | None) -> set[str]:
    return {token for token in _word_set(value) if token not in _GENERIC_MODEL_WORDS and len(token) >= 2}


def _family_overlap(model: str | None, document_text: str) -> tuple[int, float]:
    requested = _model_tokens(model)
    observed = _model_tokens(document_text)
    if not requested or not observed:
        return 0, 0.0
    shared = requested & observed
    return len(shared), len(shared) / max(1, len(requested))


@dataclass(frozen=True)
class ProductFingerprint:
    identifiers: tuple[tuple[str, str], ...] = ()
    brand: str | None = None
    manufacturer: str | None = None
    canonical_model: str | None = None
    family: str | None = None
    generation: str | None = None
    functional_variant: str | None = None
    connectivity: str | None = None
    interface: str | None = None
    capacity: str | None = None
    region: str | None = None
    color: str | None = None
    aliases: tuple[str, ...] = ()
    confidence: float = 0.0

    @classmethod
    def from_identity(cls, identity: ProductIdentity) -> "ProductFingerprint":
        identifiers = tuple(
            (kind.upper(), str(value))
            for kind in ("mpn", "sku", "ean", "upc", "gtin")
            if (value := getattr(identity, kind, None))
        )
        model = identity.model or identity.product_name
        variant = identity.variant
        generations = _generation_values(" ".join(filter(None, [model, variant])))
        connectivity = _semantic_values(" ".join(filter(None, [model, variant])), _CONNECTIVITY_TERMS)
        interface = _semantic_values(" ".join(filter(None, [model, variant])), _INTERFACE_TERMS)
        return cls(
            identifiers=identifiers,
            brand=identity.brand,
            manufacturer=identity.manufacturer,
            canonical_model=model,
            generation=next(iter(generations), None),
            functional_variant=variant,
            connectivity=next(iter(connectivity), None),
            interface=next(iter(interface), None),
            capacity=identity.capacity,
            region=identity.region,
            color=identity.color,
            confidence=float(identity.confidence or 0.0),
        )


@dataclass(frozen=True)
class DocumentFingerprint:
    url: str
    source_domain: str | None = None
    source_page: str | None = None
    manufacturer: str | None = None
    brand: str | None = None
    document_title: str | None = None
    detected_product_name: str | None = None
    detected_model: str | None = None
    detected_identifiers: tuple[str, ...] = ()
    family: str | None = None
    variant_terms: tuple[str, ...] = ()
    document_type: str | None = None
    language: str | None = None
    provenance: str | None = None
    text: str = ""

    @classmethod
    def from_evidence(
        cls,
        *,
        url: str,
        title: str | None = None,
        text: str | None = None,
        source_page: str | None = None,
        provenance: str | None = None,
    ) -> "DocumentFingerprint":
        return cls(
            url=url,
            document_title=title,
            text=text or "",
            source_page=source_page,
            provenance=provenance,
        )

    @property
    def combined_text(self) -> str:
        return "\n".join(
            part
            for part in (self.document_title, self.detected_product_name, self.detected_model, self.text, self.url)
            if part
        )

    @property
    def content_text(self) -> str:
        return "\n".join(part for part in (self.document_title, self.detected_product_name, self.detected_model, self.text) if part)


@dataclass(frozen=True)
class ProductDocumentMatch:
    relationship: str
    confidence: float
    positive_evidence: tuple[str, ...] = ()
    negative_evidence: tuple[str, ...] = ()
    hard_conflicts: tuple[str, ...] = ()
    reason: str = ""
    document_scope: str = "NONE"

    @property
    def accepted(self) -> bool:
        return self.relationship in _ACCEPTED_RELATIONSHIPS and not self.hard_conflicts


class ProductDocumentMatcher:
    """Fail-closed ProductFingerprint ↔ DocumentFingerprint matcher.

    Similarity can establish candidate relatedness, but it can never erase a
    discriminating contradiction. Exact identifiers and exact functional model
    evidence are the only accepting relationships.
    """

    def match(self, product: ProductFingerprint, document: DocumentFingerprint) -> ProductDocumentMatch:
        combined = document.combined_text
        content = document.content_text
        positives: list[str] = []
        negatives: list[str] = []
        conflicts: list[str] = []

        brand_in_content = _phrase_present(product.brand, content) if product.brand else False
        model_in_content = _phrase_present(product.canonical_model, content) if product.canonical_model else False
        model_in_combined = _phrase_present(product.canonical_model, combined) if product.canonical_model else False

        exact_identifiers: list[tuple[str, str]] = []
        identifiers_in_content: list[tuple[str, str]] = []
        for kind, value in product.identifiers:
            if _identifier_present(value, combined):
                exact_identifiers.append((kind, value))
            if _identifier_present(value, content):
                identifiers_in_content.append((kind, value))

        if product.generation:
            doc_generations = _generation_values(content)
            if doc_generations and product.generation not in doc_generations:
                conflicts.append(
                    f"generation mismatch: target Gen {product.generation} != document Gen {','.join(sorted(doc_generations))}"
                )

        target_conn = _semantic_values(" ".join(filter(None, [product.canonical_model, product.functional_variant])), _CONNECTIVITY_TERMS)
        doc_conn = _semantic_values(content, _CONNECTIVITY_TERMS)
        if "wireless" in target_conn and "wired" in doc_conn and "wireless" not in doc_conn:
            conflicts.append("connectivity mismatch: target Wireless != document Wired")
        elif "wired" in target_conn and "wireless" in doc_conn and "wired" not in doc_conn:
            conflicts.append("connectivity mismatch: target Wired != document Wireless")

        target_interface = _semantic_values(" ".join(filter(None, [product.canonical_model, product.functional_variant])), _INTERFACE_TERMS)
        doc_interface = _semantic_values(content, _INTERFACE_TERMS)
        if target_interface and doc_interface and target_interface.isdisjoint(doc_interface):
            # Interface alone can be a feature rather than a variant. Treat it as
            # a hard conflict only when the target explicitly carries an interface
            # variant and the document lacks the exact full model.
            explicit_target_interface = bool(_semantic_values(product.functional_variant, _INTERFACE_TERMS))
            if explicit_target_interface and not model_in_content:
                conflicts.append(
                    f"interface mismatch: target {','.join(sorted(target_interface))} != document {','.join(sorted(doc_interface))}"
                )

        target_codes = _model_code_candidates(product.canonical_model)
        document_codes = _model_code_candidates(content)
        for target_code in sorted(target_codes):
            if target_code in document_codes:
                continue
            sibling_codes = sorted(code for code in document_codes if _similar_model_code(target_code, code))
            if sibling_codes:
                conflicts.append(
                    f"model code mismatch: target {target_code} != document {','.join(sibling_codes)}"
                )
                break

        shared_count, overlap = _family_overlap(product.canonical_model, content)
        related_signal = shared_count >= 2 or overlap >= 0.50

        # Contradiction > similarity. Even an exact identifier becomes fail-closed
        # if the same document simultaneously carries a discriminating conflict;
        # this commonly indicates a multi-product/corrupt document.
        if conflicts:
            relationship = SIBLING_VARIANT if (related_signal or brand_in_content or model_in_combined or exact_identifiers) else UNRELATED
            return ProductDocumentMatch(
                relationship=relationship,
                confidence=0.99,
                positive_evidence=tuple(positives),
                negative_evidence=tuple(negatives),
                hard_conflicts=tuple(conflicts),
                reason="HARD_CONFLICT",
                document_scope="NONE",
            )

        if exact_identifiers:
            positives.extend(f"exact {kind}: {value}" for kind, value in exact_identifiers)
            # A known brand must be bound by document content/model, not merely by
            # an identifier that happened to appear in a URL or unrelated text.
            if product.brand and not (brand_in_content or model_in_content):
                negatives.append("exact identifier lacks brand/model binding in document content")
                return ProductDocumentMatch(
                    relationship=UNKNOWN,
                    confidence=0.55,
                    positive_evidence=tuple(positives),
                    negative_evidence=tuple(negatives),
                    reason="STRONG_IDENTIFIER_WITHOUT_BRAND_BINDING",
                    document_scope="NONE",
                )
            return ProductDocumentMatch(
                relationship=EXACT_SKU,
                confidence=0.99,
                positive_evidence=tuple(positives),
                reason="EXACT_IDENTIFIER",
                document_scope="SKU",
            )

        if model_in_content:
            positives.append(f"exact functional model: {product.canonical_model}")
            if product.brand and brand_in_content:
                positives.append(f"brand: {product.brand}")
            return ProductDocumentMatch(
                relationship=EXACT_MODEL,
                confidence=0.96 if brand_in_content else 0.92,
                positive_evidence=tuple(positives),
                reason="EXACT_FUNCTIONAL_MODEL",
                document_scope="MODEL",
            )

        if related_signal:
            positives.append(f"model-family overlap: {shared_count} tokens ({overlap:.2f})")
            missing_discriminators = _model_tokens(product.canonical_model) - _model_tokens(content)
            if missing_discriminators:
                negatives.append("missing target discriminators: " + ", ".join(sorted(missing_discriminators)))
            return ProductDocumentMatch(
                relationship=RELATED_FAMILY,
                confidence=min(0.80, 0.45 + overlap * 0.35),
                positive_evidence=tuple(positives),
                negative_evidence=tuple(negatives),
                reason="FAMILY_OVERLAP_WITHOUT_EXACT_MODEL",
                document_scope="NONE",
            )

        if product.brand and brand_in_content:
            positives.append(f"brand only: {product.brand}")
            return ProductDocumentMatch(
                relationship=UNKNOWN,
                confidence=0.35,
                positive_evidence=tuple(positives),
                reason="BRAND_ONLY",
                document_scope="NONE",
            )

        return ProductDocumentMatch(
            relationship=UNRELATED if product.brand or product.canonical_model or product.identifiers else UNKNOWN,
            confidence=0.90 if (product.brand or product.canonical_model or product.identifiers) else 0.20,
            negative_evidence=("no exact identifier/model evidence",),
            reason="NO_PRODUCT_BINDING",
            document_scope="NONE",
        )
