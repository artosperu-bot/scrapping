from product_intelligence.social_video_downloader import _progress_payload, social_video_progress_text


def test_progress_payload_omits_unknown_values_instead_of_inventing_them():
    payload = _progress_payload({"status": "downloading", "downloaded_bytes": 1048576})
    assert payload == {"status": "downloading", "downloaded_bytes": 1048576}
    assert "total_bytes" not in payload
    assert "speed" not in payload
    assert "eta" not in payload


def test_progress_payload_preserves_real_speed_eta_and_estimated_total():
    payload = _progress_payload({
        "status": "downloading",
        "downloaded_bytes": 5_000_000,
        "total_bytes_estimate": 20_000_000,
        "speed": 2_000_000,
        "eta": 7,
    })
    assert payload["total_bytes"] == 20_000_000
    assert payload["speed"] == 2_000_000
    assert payload["eta"] == 7


def test_social_progress_text_uses_real_fields_and_phases():
    text = social_video_progress_text({
        "phase": "DOWNLOAD",
        "status": "downloading",
        "downloaded_bytes": 5 * 1024 * 1024,
        "total_bytes": 20 * 1024 * 1024,
        "speed": 2 * 1024 * 1024,
        "eta": 7,
    })
    assert "5.0 MB / 20.0 MB" in text
    assert "2.0 MB/s" in text
    assert "ETA 7s" in text
    assert social_video_progress_text({"phase": "POSTPROCESS"}) == "Procesando audio/video y remux MP4…"
    assert social_video_progress_text({"phase": "VERIFY"}) == "Verificando MP4…"
