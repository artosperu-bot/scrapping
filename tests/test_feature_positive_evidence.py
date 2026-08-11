from product_intelligence.field_derivations import derive_features
from product_intelligence.models import Evidence, ProductIdentity, ProductRecord


OPTIONS = ["Cuenta con micrófono", "Cancelación de ruido activa"]


def _record(*evidence):
    return ProductRecord(
        identity=ProductIdentity(product_name="Test Headphones", mpn="TEST123"),
        evidence=list(evidence),
    )


def _ev(attribute, value):
    return Evidence(
        attribute=attribute,
        raw_value=value,
        normalized_value=value,
        source_type="secondary_html",
        source_url="https://example.com/product",
        match_level="EXACT",
        confidence=0.95,
    )


def test_anc_no_is_not_mapped_as_active_noise_cancellation():
    rec = _record(_ev("Active Noise Cancellation", "No"), _ev("Microphone", "Yes (on Cable)"))
    result = derive_features(rec, OPTIONS)
    assert result.value == "Cuenta con micrófono"
    assert "Cancelación de ruido activa" not in result.value


def test_anc_yes_is_mapped():
    rec = _record(_ev("Active Noise Cancellation", "Yes"))
    result = derive_features(rec, OPTIONS)
    assert result.value == "Cancelación de ruido activa"


def test_generic_review_label_does_not_prove_anc():
    rec = _record(_ev("name", "Active Noise Cancellation"))
    result = derive_features(rec, OPTIONS)
    assert result.value is None
