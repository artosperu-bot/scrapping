import product_intelligence.marketplace_resolution as marketplace_resolution
from product_intelligence.marketplace_resolution import FOUND_DERIVED, resolve_marketplace_field
from product_intelligence.models import Evidence, ProductIdentity, ProductRecord
from product_intelligence.provider_runtime import provider_run_scope
from product_intelligence.semantic_guard import FieldContract


class FakeNarrator:
    def __init__(self, text):
        self.text = text
        self.payload = None
        self.calls = 0

    def generate(self, payload, *, model, timeout):
        self.calls += 1
        self.payload = payload
        return self.text


def _record():
    return ProductRecord(
        identity=ProductIdentity(
            brand="JBL",
            model="Quantum 350 Wireless",
            product_name="JBL Quantum 350 Wireless",
            mpn="JBLQ350WLBLKAM",
            match_level="EXACT",
            confidence=.99,
        ),
        evidence=[
            Evidence(
                attribute="Driver size",
                raw_value="40 mm",
                normalized_value="40 mm",
                source_url="https://example.invalid/q350",
                source_type="manufacturer_html",
                match_level="EXACT",
                confidence=.98,
            ),
            Evidence(
                attribute="Wireless connection",
                raw_value="2.4 GHz",
                normalized_value="2.4 GHz",
                source_url="https://example.invalid/q350",
                source_type="manufacturer_html",
                match_level="EXACT",
                confidence=.98,
            ),
        ],
        sources=["https://example.invalid/q350"],
    )


def _resolve_description(rec):
    return resolve_marketplace_field(
        rec,
        header="Descripción",
        description="Descripción comercial del producto",
        canonical="description",
        contract=FieldContract(semantic="description", context="product", value_type="text", confidence=.99),
        options=[],
        external_id="53",
    )


def test_excel_description_resolver_accepts_only_grounded_mistral(monkeypatch):
    client = FakeNarrator(
        "JBL Quantum 350 Wireless con driver de 40 mm y conexión inalámbrica de 2.4 GHz."
    )
    monkeypatch.setattr(marketplace_resolution, "mistral_narrator_client", lambda: client)
    events = []

    with provider_run_scope(
        {
            "ocr_space_enabled": False,
            "mistral_enabled": True,
            "mistral_model": "mistral-small-latest",
            "request_timeout": 20,
        },
        lambda event, data: events.append((event, data)),
    ):
        result = _resolve_description(_record())

    names = [event for event, _data in events]
    assert client.calls == 1
    assert result.status == FOUND_DERIVED
    assert result.value == client.text
    assert result.reason == "FOUND_DERIVED:mistral_grounded_description"
    assert "MISTRAL_DESCRIPTION_REQUESTED" in names
    assert "MISTRAL_DESCRIPTION_ACCEPTED" in names


def test_excel_description_resolver_rejects_invented_mistral_and_falls_back(monkeypatch):
    client = FakeNarrator(
        "JBL Quantum 350 Wireless con driver de 50 mm y conexión inalámbrica de 2.4 GHz."
    )
    monkeypatch.setattr(marketplace_resolution, "mistral_narrator_client", lambda: client)
    events = []

    with provider_run_scope(
        {
            "ocr_space_enabled": False,
            "mistral_enabled": True,
            "mistral_model": "mistral-small-latest",
            "request_timeout": 20,
        },
        lambda event, data: events.append((event, data)),
    ):
        result = _resolve_description(_record())

    names = [event for event, _data in events]
    assert client.calls == 1
    assert result.status == FOUND_DERIVED
    assert "50 mm" not in str(result.value)
    assert "40 mm" in str(result.value)
    assert result.reason != "FOUND_DERIVED:mistral_grounded_description"
    assert "MISTRAL_DESCRIPTION_REJECTED" in names
    assert "MISTRAL_DESCRIPTION_FALLBACK" in names
