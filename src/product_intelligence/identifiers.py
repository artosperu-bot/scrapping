from __future__ import annotations

import re
from dataclasses import dataclass

from rapidfuzz.fuzz import ratio

GTIN_LENGTHS = {8: "GTIN-8", 12: "GTIN-12", 13: "GTIN-13", 14: "GTIN-14"}


@dataclass(frozen=True)
class GTINValidation:
    value: str
    valid: bool
    gtin_type: str | None
    reason: str


def normalize_identifier(value: str | None) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "", str(value or "")).upper()


def validate_gtin(value: str | None) -> GTINValidation:
    raw = re.sub(r"\D", "", str(value or ""))
    if not raw:
        return GTINValidation(raw, False, None, "EMPTY")
    gtin_type = GTIN_LENGTHS.get(len(raw))
    if not gtin_type:
        return GTINValidation(raw, False, None, "UNSUPPORTED_LENGTH")
    body = raw[:-1]
    check = int(raw[-1])
    total = 0
    # GS1: starting from the rightmost body digit, weights alternate 3,1.
    for index, digit in enumerate(reversed(body)):
        total += int(digit) * (3 if index % 2 == 0 else 1)
    expected = (10 - (total % 10)) % 10
    if expected != check:
        return GTINValidation(raw, False, gtin_type, "CHECKSUM_MISMATCH")
    return GTINValidation(raw, True, gtin_type, "OK")


def is_valid_gtin(value: str | None) -> bool:
    return validate_gtin(value).valid


def possible_identifier_typo(expected: str | None, candidate: str | None) -> dict | None:
    """Return a warning-only typo candidate; never mutates or confirms identity."""
    a = normalize_identifier(expected)
    b = normalize_identifier(candidate)
    if not a or not b or a == b:
        return None
    if abs(len(a) - len(b)) > 1:
        return None
    similarity = ratio(a, b) / 100
    # Strong enough to surface for review, not strong enough to silently replace.
    if similarity < .88:
        return None
    differences = sum(x != y for x, y in zip(a, b)) + abs(len(a) - len(b))
    if differences > 2:
        return None
    return {
        "code": "possible_part_number_typo",
        "expected": expected,
        "candidate": candidate,
        "similarity": round(similarity, 4),
        "auto_confirm": False,
    }
