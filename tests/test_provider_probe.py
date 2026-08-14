import requests

from product_intelligence import provider_probe as probes


class FakeOCR:
    def __init__(self, result="STECH OCR TEST", error=None):
        self.result = result
        self.error = error

    def extract(self, image_bytes, *, language="eng", timeout=20):
        assert image_bytes
        if self.error:
            raise self.error
        return self.result


class FakeMistral:
    def __init__(self, result="STECH_OK", error=None):
        self.result = result
        self.error = error

    def generate(self, payload, *, model, timeout):
        assert model
        assert payload
        if self.error:
            raise self.error
        return self.result


def test_ocr_probe_requires_saved_key(monkeypatch):
    monkeypatch.setattr(probes, "load_value", lambda _name: None)
    result = probes.probe_ocr_space(client=FakeOCR())
    assert result.status == "SIN CONFIGURAR"


def test_ocr_probe_success_and_empty_rejection(monkeypatch):
    monkeypatch.setattr(probes, "load_value", lambda _name: "SECRET_SENTINEL")
    ok = probes.probe_ocr_space(client=FakeOCR())
    rejected = probes.probe_ocr_space(client=FakeOCR(result=""))
    assert ok.status == "CONECTADO"
    assert rejected.status == "RECHAZADO"
    assert "SECRET_SENTINEL" not in ok.detail
    assert "SECRET_SENTINEL" not in rejected.detail


def test_ocr_probe_classifies_http_and_network(monkeypatch):
    monkeypatch.setattr(probes, "load_value", lambda _name: "SECRET_SENTINEL")
    http = probes.probe_ocr_space(client=FakeOCR(error=requests.HTTPError("401 SECRET_SENTINEL")))
    network = probes.probe_ocr_space(client=FakeOCR(error=requests.Timeout("SECRET_SENTINEL")))
    assert http.status == "RECHAZADO"
    assert network.status == "ERROR DE RED"
    assert "SECRET_SENTINEL" not in http.detail + network.detail


def test_mistral_probe_requires_saved_key_and_handles_results(monkeypatch):
    monkeypatch.setattr(probes, "load_value", lambda _name: None)
    assert probes.probe_mistral(client=FakeMistral()).status == "SIN CONFIGURAR"

    monkeypatch.setattr(probes, "load_value", lambda _name: "SECRET_SENTINEL")
    ok = probes.probe_mistral(client=FakeMistral())
    empty = probes.probe_mistral(client=FakeMistral(result=""))
    http = probes.probe_mistral(client=FakeMistral(error=requests.HTTPError("401 SECRET_SENTINEL")))
    network = probes.probe_mistral(client=FakeMistral(error=requests.ConnectionError("SECRET_SENTINEL")))
    assert ok.status == "CONECTADO"
    assert empty.status == "RECHAZADO"
    assert http.status == "RECHAZADO"
    assert network.status == "ERROR DE RED"
    assert all("SECRET_SENTINEL" not in row.detail for row in (ok, empty, http, network))
