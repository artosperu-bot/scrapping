from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess

from product_intelligence.social_video_downloader import resolve_ffmpeg_exe
from product_intelligence.video_page_discovery import _extract_candidates_from_html


OUT = Path(os.environ.get("SOCIAL_VIDEO_SMOKE_OUT", "social_video_smoke_output")).resolve()


def _run(command: list[str]) -> None:
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()[-2500:]
        raise SystemExit(f"SMOKE_FAIL ffmpeg_exit={completed.returncode} detail={detail}")


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True, exist_ok=True)

    ffmpeg = resolve_ffmpeg_exe()
    if not ffmpeg or not Path(ffmpeg).is_file() or Path(ffmpeg).stat().st_size <= 0:
        raise SystemExit("SMOKE_FAIL ffmpeg_not_resolved")
    print(f"SOCIAL_VIDEO_FFMPEG={ffmpeg}")
    _run([ffmpeg, "-version"])

    video = OUT / "video-only.mp4"
    audio = OUT / "audio-only.m4a"
    merged = OUT / "merged.mp4"

    _run([
        ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=black:s=320x180:d=1:r=25",
        "-an", "-c:v", "mpeg4", "-q:v", "8", str(video),
    ])
    _run([
        ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=880:duration=1",
        "-vn", "-c:a", "aac", "-b:a", "64k", str(audio),
    ])
    _run([
        ffmpeg, "-y", "-i", str(video), "-i", str(audio),
        "-c", "copy", "-shortest", str(merged),
    ])
    if not merged.is_file() or merged.stat().st_size <= 0:
        raise SystemExit("SMOKE_FAIL ffmpeg_merge_missing")

    html = """
    <html><head><meta property="og:video" content="https://cdn.example.com/master.m3u8"></head>
    <body>
      <video controls src="/media/product-demo.mp4"></video>
      <iframe title="Product demo" src="https://www.youtube.com/embed/YE7VzlLtp-4"></iframe>
    </body></html>
    """
    candidates = _extract_candidates_from_html("https://shop.example.com/product/123", html)
    urls = {row.url for row in candidates}
    required = {
        "https://cdn.example.com/master.m3u8",
        "https://shop.example.com/media/product-demo.mp4",
        "https://www.youtube.com/embed/YE7VzlLtp-4",
    }
    if not required.issubset(urls):
        raise SystemExit(f"SMOKE_FAIL discovery_missing={sorted(required - urls)}")

    report = {
        "status": "PASS",
        "ffmpeg": ffmpeg,
        "ffmpeg_merge_bytes": merged.stat().st_size,
        "page_candidates": [
            {
                "url": row.url,
                "provider": row.provider,
                "source_kind": row.source_kind,
                "score": row.score,
            }
            for row in candidates[:8]
        ],
    }
    Path("social_video_smoke_result.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("SOCIAL_VIDEO_SMOKE=" + json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
