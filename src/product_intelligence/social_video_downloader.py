from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Any
from urllib.parse import urlparse
import shutil


class VideoDownloadError(RuntimeError):
    pass


@dataclass(frozen=True)
class VideoDownloadResult:
    title: str
    provider: str
    source_url: str
    local_path: Path
    duration: float | None = None
    quality: str = "best"


def build_format_selector(quality: str) -> str:
    value = str(quality or "best").strip().lower()
    ceiling = None
    if value not in {"best", "mejor calidad", "mejor"}:
        for candidate in (1080, 720, 480):
            if str(candidate) in value:
                ceiling = candidate
                break
        if ceiling is None:
            raise VideoDownloadError(f"QUALITY_UNSUPPORTED: {quality}")

    bound = f"[height<={ceiling}]" if ceiling else ""
    return (
        f"bv*{bound}[ext=mp4]+ba[ext=m4a]/"
        f"b{bound}[ext=mp4]/"
        f"bv*{bound}+ba/"
        f"b{bound}"
    )


def resolve_ffmpeg_exe() -> str | None:
    try:
        import imageio_ffmpeg

        candidate = Path(imageio_ffmpeg.get_ffmpeg_exe())
        if candidate.is_file() and candidate.stat().st_size > 0:
            return str(candidate)
    except Exception:
        pass
    return shutil.which("ffmpeg")


def _validate_url(url: str) -> str:
    value = str(url or "").strip()
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise VideoDownloadError("URL_INVALIDA: usa una URL http:// o https:// válida")
    return value


def _normalize_error(exc: Exception) -> VideoDownloadError:
    text = str(exc or "").strip()
    lowered = text.lower()
    if any(token in lowered for token in ("login", "sign in", "private video", "private content", "cookies")):
        code = "LOGIN_OR_PRIVATE_REQUIRED"
    elif any(token in lowered for token in ("unsupported url", "no suitable extractor", "unsupported site")):
        code = "UNSUPPORTED_URL"
    elif any(token in lowered for token in ("geo", "not available in your country", "region")):
        code = "GEO_BLOCKED"
    elif any(token in lowered for token in ("429", "rate limit", "too many requests")):
        code = "RATE_LIMITED"
    elif "ffmpeg" in lowered:
        code = "FFMPEG_UNAVAILABLE"
    else:
        code = "DOWNLOAD_FAILED"
    return VideoDownloadError(f"{code}: {text or exc.__class__.__name__}")


def _candidate_paths(info: dict[str, Any], ydl: Any, output_dir: Path) -> list[Path]:
    rows: list[Path] = []
    for item in info.get("requested_downloads") or []:
        raw = item.get("filepath") or item.get("filename")
        if raw:
            rows.append(Path(raw))
    for key in ("filepath", "_filename", "filename"):
        raw = info.get(key)
        if raw:
            rows.append(Path(raw))
    try:
        prepared = ydl.prepare_filename(info)
        if prepared:
            rows.append(Path(prepared))
    except Exception:
        pass

    expanded: list[Path] = []
    seen: set[str] = set()
    for path in rows:
        variants = [path, path.with_suffix(".mp4")]
        for variant in variants:
            key = str(variant.resolve()) if variant.is_absolute() else str(variant)
            if key not in seen:
                seen.add(key)
                expanded.append(variant)

    video_id = str(info.get("id") or "").strip()
    if video_id:
        expanded.extend(output_dir.glob(f"*[{video_id}].mp4"))
        expanded.extend(output_dir.glob(f"*{video_id}*.mp4"))
    return expanded


def _verified_mp4(info: dict[str, Any], ydl: Any, output_dir: Path) -> Path:
    for path in _candidate_paths(info, ydl, output_dir):
        try:
            if path.suffix.lower() == ".mp4" and path.is_file() and path.stat().st_size > 0:
                return path.resolve()
        except OSError:
            continue
    raise VideoDownloadError("OUTPUT_MP4_NOT_FOUND: la descarga no produjo un MP4 válido")


def _progress_payload(event: dict[str, Any]) -> dict[str, Any]:
    """Keep only progress values yt-dlp actually supplied; never synthesize metrics."""
    payload: dict[str, Any] = {}
    status = event.get("status")
    if status is not None:
        payload["status"] = status
    for key in ("downloaded_bytes", "speed", "eta", "filename"):
        value = event.get(key)
        if value is not None:
            payload[key] = value
    total = event.get("total_bytes")
    if total is None:
        total = event.get("total_bytes_estimate")
    if total is not None:
        payload["total_bytes"] = total
    return payload


def download_social_video(
    url: str,
    output_dir: str | Path,
    *,
    quality: str = "best",
    on_progress: Callable[[dict[str, Any]], None] | None = None,
) -> VideoDownloadResult:
    source_url = _validate_url(url)
    destination = Path(output_dir).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    selector = build_format_selector(quality)
    ffmpeg_exe = resolve_ffmpeg_exe()

    def emit(**payload):
        if on_progress:
            on_progress(payload)

    emit(phase="PREPARE")
    try:
        import yt_dlp

        def progress_hook(event: dict[str, Any]):
            if on_progress:
                payload = _progress_payload(event)
                payload["phase"] = "DOWNLOAD"
                on_progress(payload)

        options: dict[str, Any] = {
            "format": selector,
            "outtmpl": str(destination / "%(title).180B [%(id)s].%(ext)s"),
            "noplaylist": True,
            "merge_output_format": "mp4",
            "postprocessors": [{"key": "FFmpegVideoConvertor", "preferedformat": "mp4"}],
            "progress_hooks": [progress_hook],
            "quiet": True,
            "no_warnings": True,
            "restrictfilenames": False,
        }
        if ffmpeg_exe:
            options["ffmpeg_location"] = str(Path(ffmpeg_exe).parent)

        emit(phase="RESOLVE")
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(source_url, download=True)
            if not isinstance(info, dict):
                raise VideoDownloadError("DOWNLOAD_FAILED: respuesta de metadata inválida")
            emit(phase="POSTPROCESS")
            emit(phase="VERIFY")
            local_path = _verified_mp4(info, ydl, destination)

        size = None
        try:
            size = local_path.stat().st_size
        except OSError:
            pass
        complete = {"phase": "COMPLETE", "local_path": str(local_path)}
        if size is not None:
            complete["size_bytes"] = size
        emit(**complete)

        return VideoDownloadResult(
            title=str(info.get("title") or local_path.stem),
            provider=str(info.get("extractor_key") or info.get("extractor") or "yt-dlp"),
            source_url=str(info.get("webpage_url") or source_url),
            local_path=local_path,
            duration=float(info["duration"]) if info.get("duration") is not None else None,
            quality=str(quality or "best"),
        )
    except VideoDownloadError:
        raise
    except Exception as exc:
        raise _normalize_error(exc) from exc
