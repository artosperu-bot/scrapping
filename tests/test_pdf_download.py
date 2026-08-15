import pytest

from product_intelligence.pdf_download import download_pdf


def test_rejects_html_response_even_when_url_looks_like_pdf(monkeypatch, tmp_path):
    class Response:
        status_code = 200
        url = "https://example.com/manual.pdf"
        headers = {"content-type": "text/html"}
        content = b"<html>blocked</html>"
        def raise_for_status(self):
            return None

    monkeypatch.setattr("product_intelligence.pdf_download.requests.get", lambda *a, **k: Response())
    with pytest.raises(ValueError, match="NOT_PDF"):
        download_pdf("https://example.com/manual.pdf", tmp_path, timeout=1)


def test_accepts_pdf_signature(monkeypatch, tmp_path):
    class Response:
        status_code = 200
        url = "https://cdn.example.com/file"
        headers = {"content-type": "application/octet-stream"}
        content = b"%PDF-1.7\nmock"
        def raise_for_status(self):
            return None

    monkeypatch.setattr("product_intelligence.pdf_download.requests.get", lambda *a, **k: Response())
    result = download_pdf("https://cdn.example.com/file", tmp_path, timeout=1)
    assert result.path.read_bytes().startswith(b"%PDF-")
    assert result.size_bytes == len(b"%PDF-1.7\nmock")
    assert len(result.sha256) == 64
