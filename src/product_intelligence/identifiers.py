from __future__ import annotations

import re
from dataclasses import dataclass

from rapidfuzz.fuzz import ratio

GTIN_LENGTHS = {8: "GTIN-8", 12: "GTIN-12", 13: "GTIN-13", 14: "GTIN-14"}
_EMPTY_SENTINELS = {"", "null", "none", "n/a", "na", "unknown", "undefined", "-"}


@dataclass(frozen=True)
class GTINValidation:
    value: str
    valid: bool
    gtin_type: str | None
    reason: str


def clean_identifier_value(value: str | None) -> str | None:
    text = str(value or "").strip()
    if text.casefold() in _EMPTY_SENTINELS:
        return None
    return text or None


def normalize_identifier(value: str | None) -> str:
    clean = clean_identifier_value(value)
    return re.sub(r"[^A-Za-z0-9]+", "", clean or "").upper()


def mpn_aliases(value: str | None) -> list[str]:
    """Return bounded search aliases while preserving the original MPN.

    Case-only aliases are intentionally omitted because normal web search is
    case-insensitive. Separator variants are useful because retailer indexes are
    not consistent about slash, dash and whitespace preservation.
    """
    original = clean_identifier_value(value)
    if not original:
        return []
    chunks = [part for part in re.split(r"[\s/_-]+", original) if part]
    candidates = [original]
    if len(chunks) >= 2:
        candidates.extend(("".join(chunks), "-".join(chunks), " ".join(chunks)))
    compact = normalize_identifier(original)
    if compact:
        candidates.append(compact)
    out: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        clean = str(candidate or "").strip()
        key = clean.casefold()
        if clean and key not in seen:
            seen.add(key)
            out.append(clean)
    return out


def validate_gtin(value: str | None) -> GTINValidation:
    clean = clean_identifier_value(value)
    if not clean:
        return GTINValidation("", False, None, "EMPTY")
    # Only visual separators are allowed. Letters or semantic labels are not GTINs.
    if re.search(r"[^0-9\s-]", clean):
        return GTINValidation(re.sub(r"\D", "", clean), False, None, "NON_NUMERIC")
    raw = re.sub(r"[\s-]+", "", clean)
    if not raw:
        return GTINValidation(raw, False, None, "EMPTY")
    gtin_type = GTIN_LENGTHS.get(len(raw))
    if not gtin_type:
        return GTINValidation(raw, False, None, "UNSUPPORTED_LENGTH")
    body = raw[:-1]
    check = int(raw[-1])
    total = 0
    for index, digit in enumerate(reversed(body)):
        total += int(digit) * (3 if index % 2 == 0 else 1)
    expected = (10 - (total % 10)) % 10
    if expected != check:
        return GTINValidation(raw, False, gtin_type, "CHECKSUM_MISMATCH")
    return GTINValidation(raw, True, gtin_type, "OK")


def is_valid_gtin(value: str | None) -> bool:
    return validate_gtin(value).valid


def canonical_gtin(value: str | None) -> str | None:
    result = validate_gtin(value)
    return result.value if result.valid else None


def _adjacent_transposition(a: str, b: str) -> bool:
    if len(a) != len(b):
        return False
    diff = [index for index, (left, right) in enumerate(zip(a, b)) if left != right]
    return len(diff) == 2 and diff[1] == diff[0] + 1 and a[diff[0]] == b[diff[1]] and a[diff[1]] == b[diff[0]]


def possible_identifier_typo(expected: str | None, candidate: str | None) -> dict | None:
    """Return a warning-only typo candidate; never mutates or confirms identity."""
    a = normalize_identifier(expected)
    b = normalize_identifier(candidate)
    if not a or not b or a == b:
        return None
    if abs(len(a) - len(b)) > 1:
        return None
    similarity = ratio(a, b) / 100
    differences = sum(x != y for x, y in zip(a, b)) + abs(len(a) - len(b))
    plausible = similarity >= .85 or _adjacent_transposition(a, b)
    if not plausible or differences > 2:
        return None
    return {
        "code": "possible_part_number_typo",
        "expected": expected,
        "candidate": candidate,
        "similarity": round(similarity, 4),
        "auto_confirm": False,
    }
