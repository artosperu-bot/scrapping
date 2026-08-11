from __future__ import annotations

from pathlib import Path

from PIL import Image

from product_intelligence.capabilities import capability_status, is_available
from product_intelligence.ocr_adapter import OCRUnavailable, extract_text
from product_intelligence.vision_adapter import analyze_image


def test_capability_registry_is_safe_without_heavy_extras():
    status = capability_status()
    assert status["vision"] in {"AVAILABLE", "UNAVAILABLE"}
    assert status["ocr"] in {"AVAILABLE", "UNAVAILABLE"}
    assert status["browser"] in {"AVAILABLE", "UNAVAILABLE"}


def test_vision_adapter_has_pillow_fallback(tmp_path: Path):
    path = tmp_path / "sample.png"
    Image.new("RGB", (640, 480), "white").save(path)
    result = analyze_image(path, advanced=False)
    assert result.width == 640
    assert result.height == 480
    assert result.backend == "pillow"


def test_ocr_fails_cleanly_when_optional_profile_is_missing(tmp_path: Path):
    if is_available("ocr"):
        return
    path = tmp_path / "sample.png"
    Image.new("RGB", (20, 20), "white").save(path)
    try:
        extract_text(path)
    except OCRUnavailable:
        pass
    else:
        raise AssertionError("OCR should fail explicitly when optional dependencies are absent")
