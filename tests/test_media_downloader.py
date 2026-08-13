from io import BytesIO
from pathlib import Path

from PIL import Image

from product_intelligence.media_downloader import (
    download_media_item,
    safe_product_key,
    write_media_metadata,
)
from product_intelligence.models import ProductIdentity


class FakeResponse:
    def __init__(self, body: bytes, content_type: str, status_code: int = 200):
        self._body = body
        self.headers = {"content-type": content_type}
        self.status_code = status_code
        self.ok = 200 <= status_code < 400

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError(f"http {self.status_code}")

    def iter_content(self, chunk_size=65536):
        yield self._body


class FakeSession:
    def __init__(self, response: FakeResponse):
        self.response = response

    def get(self, *args, **kwargs):
        return self.response


def _large_jpeg() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (800, 800)).save(buf, format="JPEG")
    return buf.getvalue()


def test_safe_product_key_prefers_mpn_and_sanitizes():
    identity = ProductIdentity(mpn="JBL Q350/WL:BLKAM", model="Quantum 350")
    assert safe_product_key(identity) == "JBL_Q350_WL_BLKAM"


def test_download_image_routes_to_fotos_and_hashes(tmp_path: Path):
    identity = ProductIdentity(mpn="JBLQ350WLBLKAM", model="Quantum 350")
    item = {"url": "https://cdn.example.com/product", "media_type": "image", "source": "jsonld:Product.image", "confidence": 0.95}
    payload = _large_jpeg()
    result = download_media_item(
        item,
        identity,
        tmp_path,
        session=FakeSession(FakeResponse(payload, "image/jpeg")),
    )
    assert result["downloaded"] is True
    assert result["local_path"].replace("\\", "/").endswith("multimedia/fotos/JBLQ350WLBLKAM/01.jpg")
    assert result["sha256"]
    assert result["width"] == 800 and result["height"] == 800
    assert Path(result["local_path"]).read_bytes() == payload


def test_download_direct_video_routes_to_videos(tmp_path: Path):
    identity = ProductIdentity(mpn="ABC123")
    item = {"url": "https://cdn.example.com/demo.mp4", "media_type": "video", "provider": None}
    result = download_media_item(
        item,
        identity,
        tmp_path,
        session=FakeSession(FakeResponse(b"video-bytes", "video/mp4")),
    )
    assert result["downloaded"] is True
    assert result["local_path"].replace("\\", "/").endswith("multimedia/videos/ABC123/01.mp4")


def test_hosted_video_is_metadata_only(tmp_path: Path):
    identity = ProductIdentity(mpn="ABC123")
    item = {"url": "https://www.youtube.com/embed/demo", "media_type": "video", "provider": "youtube"}
    result = download_media_item(item, identity, tmp_path, session=FakeSession(FakeResponse(b"html", "text/html")))
    assert result["downloaded"] is False
    assert result["metadata_only"] is True
    assert result["reason"] == "hosted_video"


def test_non_media_response_is_rejected(tmp_path: Path):
    identity = ProductIdentity(mpn="ABC123")
    item = {"url": "https://example.com/not-image", "media_type": "image"}
    result = download_media_item(item, identity, tmp_path, session=FakeSession(FakeResponse(b"<html/>", "text/html")))
    assert result["downloaded"] is False
    assert result["reason"] == "unexpected_content_type"


def test_write_metadata_deduplicates_by_sha(tmp_path: Path):
    identity = ProductIdentity(mpn="ABC123")
    results = [
        {"media_type": "image", "sha256": "same", "url": "https://a/1.jpg", "downloaded": True},
        {"media_type": "image", "sha256": "same", "url": "https://b/duplicate.jpg", "downloaded": True},
        {"media_type": "video", "url": "https://youtube.com/x", "provider": "youtube", "downloaded": False, "metadata_only": True},
    ]
    write_media_metadata(tmp_path, identity, results)
    image_meta = tmp_path / "multimedia" / "fotos" / "ABC123" / "metadata.json"
    video_meta = tmp_path / "multimedia" / "videos" / "ABC123" / "metadata.json"
    assert image_meta.exists() and video_meta.exists()
    assert image_meta.read_text(encoding="utf-8").count('"sha256": "same"') == 1
