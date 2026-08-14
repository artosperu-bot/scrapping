from dataclasses import dataclass

from product_intelligence.execution_context import ExecutionSnapshot
from product_intelligence.provider_settings import ProviderSettings
from product_intelligence.description_narrator import (
    DescriptionNarrator,
    DescriptionGuard,
    build_safe_facts,
)
from product_intelligence.ocr_adapter import OCRProvider, extract_with_provider


@dataclass
class Identity:
    brand: str = "JBL"
    model: str = "Quantum 350 Wireless"
    mpn: str = "JBLQ350WLBLK"
    product_name: str = "JBL Quantum 350 Wireless"


@dataclass
class Evidence:
    attribute: str
    raw_value: str
    normalized_value: str | None = None
    confidence: float = 0.95
    rejected: bool = False


@dataclass
class Record:
    identity: Identity
    evidence: list


class FakeOCR(OCRProvider):
    def __init__(self, text="scanned text", fail=False):
        self.text = text
        self.fail = fail
        self.calls = 0

    def extract(self, image_bytes: bytes, *, language: str, timeout: int) -> str:
        self.calls += 1
        if self.fail:
            raise RuntimeError("provider down")
        return self.text


class FakeNarrator:
    def __init__(self, text=None, fail=False):
        self.text = text
        self.fail = fail
        self.payload = None

    def generate(self, payload, *, model, timeout):
        self.payload = payload
        if self.fail:
            raise RuntimeError("provider down")
        return self.text


def _record():
    return Record(
        identity=Identity(),
        evidence=[
            Evidence("Driver", "40 mm"),
            Evidence("Connectivity", "2.4 GHz wireless"),
            Evidence("Price", "S/ 499"),
            Evidence("Stock", "12"),
            Evidence("Seller", "STECH"),
            Evidence("Raw OCR", "Titanium aerospace 99 mm", rejected=True),
        ],
    )


def test_settings_json_contains_no_secret(tmp_path):
    path = tmp_path / "settings.json"
    settings = ProviderSettings(path)
    settings.set("ocr_space_enabled", True)
    settings.set("mistral_enabled", True)
    settings.save()
    text = path.read_text(encoding="utf-8").lower()
    assert "api_key" not in text
    assert "secret" not in text
    assert "token" not in text


def test_execution_snapshot_freezes_provider_settings():
    snapshot = ExecutionSnapshot.create(
        "EXCEL",
        "out",
        [],
        options={
            "ocr_space_enabled": True,
            "mistral_enabled": False,
            "mistral_model": "mistral-small-latest",
            "request_timeout": 20,
        },
    )
    assert snapshot.option("ocr_space_enabled") is True
    assert snapshot.option("mistral_enabled") is False
    assert snapshot.option("mistral_model") == "mistral-small-latest"
    assert snapshot.option("request_timeout") == 20


def test_ocr_provider_failure_is_non_fatal():
    provider = FakeOCR(fail=True)
    assert extract_with_provider(b"png", provider, language="en", timeout=5) == ""
    assert provider.calls == 1


def test_safe_facts_exclude_price_stock_seller_and_rejected_evidence():
    facts = build_safe_facts(_record())
    joined = " ".join(facts).lower()
    assert "40 mm" in joined
    assert "2.4 ghz" in joined
    assert "499" not in joined
    assert "stock" not in joined
    assert "stech" not in joined
    assert "titanium" not in joined


def test_guard_accepts_grounded_description_and_rejects_new_number():
    facts = build_safe_facts(_record())
    guard = DescriptionGuard()
    grounded = "JBL Quantum 350 Wireless con driver de 40 mm y conexión inalámbrica de 2.4 GHz."
    invented = "JBL Quantum 350 Wireless con driver de 50 mm y conexión inalámbrica de 2.4 GHz."
    assert guard.validate(grounded, _record(), facts).accepted is True
    assert guard.validate(invented, _record(), facts).accepted is False


def test_guard_rejects_price_stock_seller_and_identity_change():
    facts = build_safe_facts(_record())
    guard = DescriptionGuard()
    for text in [
        "JBL Quantum 350 Wireless cuesta S/ 499.",
        "JBL Quantum 350 Wireless tiene stock 12.",
        "Vendido por STECH: JBL Quantum 350 Wireless.",
        "Sony Quantum 350 Wireless con driver de 40 mm.",
    ]:
        assert guard.validate(text, _record(), facts).accepted is False


def test_narrator_disabled_or_failure_uses_fallback():
    fallback = lambda rec: "Descripción determinista"
    disabled = DescriptionNarrator(client=FakeNarrator("unused"), enabled=False)
    failed = DescriptionNarrator(client=FakeNarrator(fail=True), enabled=True)
    assert disabled.describe(_record(), fallback=fallback) == "Descripción determinista"
    assert failed.describe(_record(), fallback=fallback) == "Descripción determinista"


def test_narrator_payload_uses_only_safe_facts():
    client = FakeNarrator("JBL Quantum 350 Wireless con driver de 40 mm y conexión inalámbrica de 2.4 GHz.")
    narrator = DescriptionNarrator(client=client, enabled=True)
    result = narrator.describe(_record(), fallback=lambda rec: "fallback")
    payload = str(client.payload).lower()
    assert result != "fallback"
    assert "40 mm" in payload
    assert "2.4 ghz" in payload
    assert "499" not in payload
    assert "titanium" not in payload
