from __future__ import annotations

import json
import os
from pathlib import Path
import shutil

from product_intelligence.social_video_downloader import download_social_video, resolve_ffmpeg_exe


# Active public YouTube fixture from yt-dlp's own YoutubeIE tests. The time range
# keeps this smoke focused on the exact video+audio/FFmpeg path reported by users.
URL = os.environ.get(
    "SOCIAL_VIDEO_SMOKE_URL",
    "https://www.youtube.com/watch?v=YE7VzlLtp-4&t=1s&end=9",
)
OUT = Path(os.environ.get("SOCIAL_VIDEO_SMOKE_OUT", "social_video_smoke_output")).resolve()


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True, exist_ok=True)

    ffmpeg = resolve_ffmpeg_exe()
    if not ffmpeg or not Path(ffmpeg).is_file():
        raise SystemExit("SMOKE_FAIL ffmpeg_not_resolved")
    print(f"SOCIAL_VIDEO_FFMPEG={ffmpeg}")

    result = download_social_video(URL, OUT, quality="480p")
    path = result.local_path
    if path.suffix.lower() != ".mp4":
        raise SystemExit(f"SMOKE_FAIL extension={path.suffix}")
    if not path.is_file() or path.stat().st_size <= 0:
        raise SystemExit("SMOKE_FAIL missing_or_empty_output")

    report = {
        "status": "PASS",
        "provider": result.provider,
        "title": result.title,
        "source_url": result.source_url,
        "output_name": path.name,
        "bytes": path.stat().st_size,
        "quality": result.quality,
        "ffmpeg": ffmpeg,
    }
    Path("social_video_smoke_result.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("SOCIAL_VIDEO_SMOKE=" + json.dumps(report, ensure_ascii=False))

    # Prove a real file existed without redistributing the downloaded media as a CI artifact.
    path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
