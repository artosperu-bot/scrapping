from types import SimpleNamespace

from product_intelligence import local_ocr


def test_rapidocr_text_uses_output_txts_and_caches_engine():
    local_ocr.reset_local_ocr_for_tests()
    created = []

    class Engine:
        def __call__(self, image):
            assert image == b"PNG"
            return SimpleNamespace(txts=("Model X", "Battery: 5000 mAh"))

    def factory():
        created.append(1)
        return Engine()

    assert local_ocr.rapidocr_text(b"PNG", engine_factory=factory) == "Model X\nBattery: 5000 mAh"
    assert local_ocr.rapidocr_text(b"PNG", engine_factory=factory) == "Model X\nBattery: 5000 mAh"
    assert len(created) == 1


def test_rapidocr_text_is_fail_open_when_runtime_unavailable():
    local_ocr.reset_local_ocr_for_tests()

    def broken():
        raise ImportError("rapidocr unavailable")

    assert local_ocr.rapidocr_text(b"PNG", engine_factory=broken) == ""
