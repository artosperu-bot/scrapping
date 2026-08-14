from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Protocol, Sequence


_DENY_ATTR = re.compile(
    r"price|precio|stock|inventory|inventario|seller|vendedor|merchant|tienda|raw\s*ocr|ocr\s*raw|conflict|rechaz",
    re.I,
)
_DENY_TEXT = re.compile(
    r"\b(precio|price|stock|inventario|inventory|vendedor|seller|vendido\s+por|s\/\.?\s*\d|usd\s*\d|\$\s*\d)",
    re.I,
)
_NUMBER_RE = re.compile(r"(?<![\w])\d+(?:[.,]\d+)?(?:\s*(?:mm|cm|m|g|kg|mah|wh|hz|khz|mhz|ghz|w|v|a|mp|gb|tb|mb|%))?", re.I)
_RISKY_CLAIM_PATTERNS = (
    re.compile(r"\b(?:titanio|titanium|aluminio|aluminum|acero|steel|carbono|carbon\s*fiber|fibra\s*de\s*carbono)\b", re.I),
    re.compile(r"\b(?:certificaci[oó]n|certified|certification|mil-std|ip\s*\d{2}|ipx\s*\d)\b", re.I),
    re.compile(r"\b(?:compatible|compatibilidad|compatibility)\b", re.I),
    re.compile(r"\b(?:nfc|5g|wifi\s*6|wi-fi\s*6|bluetooth|c[aá]mara\s*t[eé]rmica|thermal\s*camera|visi[oó]n\s*nocturna|night\s*vision)\b", re.I),
)


class NarratorClient(Protocol):
    def generate(self, payload: dict[str, Any], *, model: str, timeout: int) -> str:
        ...


@dataclass(frozen=True)
class GuardResult:
    accepted: bool
    reason: str = ""


def _identity_value(identity: Any, name: str) -> str:
    value = getattr(identity, name, None)
    return str(value).strip() if value not in (None, "") else ""


def _iter_evidence(rec: Any):
    for ev in list(getattr(rec, "evidence", None) or []):
        if bool(getattr(ev, "rejected", False)):
            continue
        attr = str(getattr(ev, "attribute", "") or "").strip()
        if not attr or _DENY_ATTR.search(attr):
            continue
        value = getattr(ev, "normalized_value", None)
        if value in (None, ""):
            value = getattr(ev, "raw_value", None)
        if value in (None, ""):
            continue
        text = str(value).strip()
        if not text or _DENY_TEXT.search(text):
            continue
        confidence = float(getattr(ev, "confidence", 0.0) or 0.0)
        if confidence < 0.60:
            continue
        yield attr, text


def build_safe_facts(rec: Any, *, limit: int = 24) -> list[str]:
    """Return only validated, non-commercial facts suitable for narration."""
    facts: list[str] = []
    seen: set[str] = set()
    for attr, value in _iter_evidence(rec):
        item = f"{attr}: {value}"
        key = re.sub(r"\s+", " ", item).strip().casefold()
        if key in seen:
            continue
        seen.add(key)
        facts.append(item[:300])
        if len(facts) >= limit:
            break
    return facts


def build_payload(rec: Any, facts: Sequence[str]) -> dict[str, Any]:
    identity = getattr(rec, "identity", None)
    return {
        "identity": {
            "brand": _identity_value(identity, "brand"),
            "model": _identity_value(identity, "model"),
            "mpn": _identity_value(identity, "mpn"),
            "product_name": _identity_value(identity, "product_name"),
        },
        "facts": list(facts),
        "instructions": (
            "Redacta una descripción comercial natural en español usando SOLO identity y facts. "
            "No inventes especificaciones, compatibilidad, materiales, certificaciones, beneficios, "
            "precio, stock ni vendedor. Conserva exactamente marca, modelo y MPN si los mencionas."
        ),
    }


def _normalized_numbers(text: str) -> set[str]:
    return {re.sub(r"\s+", "", m.group(0).lower()).replace(",", ".") for m in _NUMBER_RE.finditer(text or "")}


def _unsupported_risky_claim(text: str, allowed_text: str) -> bool:
    for pattern in _RISKY_CLAIM_PATTERNS:
        generated = {m.group(0).casefold() for m in pattern.finditer(text)}
        if not generated:
            continue
        allowed = {m.group(0).casefold() for m in pattern.finditer(allowed_text)}
        if generated - allowed:
            return True
    return False


class DescriptionGuard:
    def validate(self, description: str, rec: Any, facts: Sequence[str]) -> GuardResult:
        text = str(description or "").strip()
        if not text:
            return GuardResult(False, "EMPTY_DESCRIPTION")
        if _DENY_TEXT.search(text):
            return GuardResult(False, "COMMERCIAL_STATE_CLAIM")

        identity = getattr(rec, "identity", None)
        lower = text.casefold()
        for field in ("brand", "model"):
            expected = _identity_value(identity, field)
            if expected and expected.casefold() not in lower:
                return GuardResult(False, f"IDENTITY_{field.upper()}_ALTERED_OR_MISSING")
        expected_mpn = _identity_value(identity, "mpn")
        if expected_mpn and re.search(r"\bmpn\b", text, re.I) and expected_mpn.casefold() not in lower:
            return GuardResult(False, "IDENTITY_MPN_ALTERED")

        allowed_text = " ".join(
            [
                _identity_value(identity, "brand"),
                _identity_value(identity, "model"),
                _identity_value(identity, "mpn"),
                _identity_value(identity, "product_name"),
                *list(facts),
            ]
        )
        allowed_numbers = _normalized_numbers(allowed_text)
        new_numbers = _normalized_numbers(text) - allowed_numbers
        if new_numbers:
            return GuardResult(False, "UNSUPPORTED_NUMBER_OR_UNIT")
        if _unsupported_risky_claim(text, allowed_text):
            return GuardResult(False, "UNSUPPORTED_TECHNICAL_CLAIM")
        return GuardResult(True, "GROUNDED")


class DescriptionNarrator:
    def __init__(
        self,
        *,
        client: NarratorClient,
        enabled: bool = True,
        model: str = "mistral-small-latest",
        timeout: int = 20,
        guard: DescriptionGuard | None = None,
        audit: Callable[[str, dict[str, Any]], None] | None = None,
    ):
        self.client = client
        self.enabled = bool(enabled)
        self.model = model or "mistral-small-latest"
        self.timeout = int(timeout)
        self.guard = guard or DescriptionGuard()
        self.audit = audit

    def _emit(self, event: str, **data: Any) -> None:
        if self.audit:
            safe = {k: v for k, v in data.items() if k.lower() not in {"api_key", "authorization", "token", "secret"}}
            self.audit(event, safe)

    def describe(self, rec: Any, *, fallback: Callable[[Any], Any]) -> Any:
        if not self.enabled:
            self._emit("MISTRAL_DESCRIPTION_FALLBACK", reason="DISABLED")
            return fallback(rec)
        facts = build_safe_facts(rec)
        if not facts:
            self._emit("MISTRAL_DESCRIPTION_FALLBACK", reason="NO_SAFE_FACTS")
            return fallback(rec)
        payload = build_payload(rec, facts)
        self._emit("MISTRAL_DESCRIPTION_REQUESTED", model=self.model)
        try:
            generated = self.client.generate(payload, model=self.model, timeout=self.timeout)
        except Exception as exc:
            self._emit("MISTRAL_DESCRIPTION_FALLBACK", reason=type(exc).__name__)
            return fallback(rec)
        verdict = self.guard.validate(generated, rec, facts)
        if not verdict.accepted:
            self._emit("MISTRAL_DESCRIPTION_REJECTED", reason=verdict.reason)
            self._emit("MISTRAL_DESCRIPTION_FALLBACK", reason=verdict.reason)
            return fallback(rec)
        self._emit("MISTRAL_DESCRIPTION_ACCEPTED", model=self.model)
        return str(generated).strip()
