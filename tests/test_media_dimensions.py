from io import BytesIO
from pathlib import Path

from PIL import Image

from product_intelligence.media_downloader import download_media_item
from product_intelligence.models import ProductIdentity


class _Response:
    def __init__(self, payload: bytes, content_type="image/png"):
        self._payload = payload
        self.headers = {"content-type": content_type}

    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size=65536):
        yield self._payload


class _Session:
    def __init__(self, payload: bytes):
        self.payload = payload

    def get(self, *args, **kwargs):
        return _Response(self.payload)


def _png(width: int, height: int) -> bytes:
    buf = BytesIO()
    Image.new("RGB", (width, height)).save(buf, format="PNG")
    return buf.getvalue()


def _download(tmp_path: Path, width: int, height: int):
    identity = ProductIdentity(mpn="ABC123")
    return download_media_item(
        {"url": "https://cdn.example/image.png", "media_type": "image"},
        identity,
        tmp_path,
        session=_Session(_png(width, height)),
    )


def test_rejects_image_when_width_is_below_300(tmp_path):
    row = _download(tmp_path, 299, 800)
    assert row["downloaded"] is False
    assert row["reason"] == "image_too_small"
    assert row["width"] == 299


def test_rejects_image_when_height_is_below_300(tmp_path):
    row = _download(tmp_path, 800, 299)
    assert row["downloaded"] is False
    assert row["reason"] == "image_too_small"
    assert row["height"] == 299


def test_rejects_image_when_pixel_area_is_below_120000(tmp_path):
    row = _download(tmp_path, 300, 300)
    assert row["downloaded"] is False
    assert row["reason"] == "image_too_small"
    assert row["pixel_area"] == 90000


def test_accepts_large_image_and_records_dimensions(tmp_path):
    row = _download(tmp_path, 800, 800)
    assert row["downloaded"] is True
    assert row["width"] == 800
    assert row["height"] == 800
    assert row["pixel_area"] == 640000
    assert Path(row["local_path"]).exists()
