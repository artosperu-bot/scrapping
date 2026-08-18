from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Any
from urllib.parse import urlparse
import shutil
import sys


class VideoDownloadError(RuntimeError):
    pass


class VideoSelectionRequired(VideoDownloadError):
    def __init__(self, candidates):
        self.candidates = tuple(candidates or ())
        super().__init__(f"VIDEO_SELECTION_REQUIRED: {len(self.candidates)} candidatos de video")


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
    return f"bv*{bound}[ext=mp4]+ba[ext=m4a]/b{bound}[ext=mp4]/bv*{bound}+ba/b{bound}"


def resolve_ffmpeg_exe() -> str | None:
    system = shutil.which("ffmpeg")
    if system:
        try:
            candidate = Path(system)
            if candidate.is_file() and candidate.stat().st_size > 0:
                return str(candidate)
        except OSError:
            pass
    try:
        import imageio_ffmpeg
        candidate = Path(imageio_ffmpeg.get_ffmpeg_exe())
        if candidate.is_file() and candidate.stat().st_size > 0:
            return str(candidate)
    except Exception:
        pass
    return None


def _runtime_roots() -> list[Path]:
    roots: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        roots.append(Path(meipass))
    if getattr(sys, "frozen", False):
        try:
            roots.append(Path(sys.executable).resolve().parent)
        except Exception:
            pass
    try:
        roots.append(Path(__file__).resolve().parents[2])
    except Exception:
        pass
    unique: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root)
        if key not in seen:
            seen.add(key)
            unique.append(root)
    return unique


def resolve_js_runtime() -> str | None:
    """Resolve the bundled Deno runtime first, then a system Deno installation."""
    names = ("deno.exe", "deno")
    for root in _runtime_roots():
        for name in names:
            candidate = root / "vendor" / "deno" / name
            try:
                if candidate.is_file() and candidate.stat().st_size > 0:
                    return str(candidate)
            except OSError:
                continue
    system = shutil.which("deno")
    if system:
        try:
            candidate = Path(system)
            if candidate.is_file() and candidate.stat().st_size > 0:
                return str(candidate)
        except OSError:
            pass
    return None


def _validate_url(url: str) -> str:
    value = str(url or "").strip()
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise VideoDownloadError("URL_INVALIDA: usa una URL http:// o https:// válida")
    return value


def _normalize_error(exc: Exception) -> VideoDownloadError:
    text = str(exc or "").strip()
    lowered = text.lower()
    if any(token in lowered for token in ("drm", "encrypted media", "protected content")):
        code = "DRM_PROTECTED"
    elif any(token in lowered for token in ("login", "sign in", "private video", "private content", "cookies")):
        code = "LOGIN_OR_PRIVATE_REQUIRED"
    elif any(token in lowered for token in (
        "unsupported url",
        "no suitable extractor",
        "unsupported site",
        "no video formats found",
        "no playable media",
    )):
        code = "UNSUPPORTED_URL"
    elif any(token in lowered for token in ("geo", "not available in your country", "region")):
        code = "GEO_BLOCKED"
    elif any(token in lowered for token in ("429", "rate limit", "too many requests")):
        code = "RATE_LIMITED"
    elif any(token in lowered for token in (
        "no supported javascript runtime",
        "javascript runtime",
        "js runtime",
        "ejs challenge",
        "yt-dlp-ejs",
    )):
        code = "JS_RUNTIME_UNAVAILABLE"
    elif "ffmpeg" in lowered:
        code = "FFMPEG_UNAVAILABLE"
    else:
        code = "DOWNLOAD_FAILED"
    return VideoDownloadError(f"{code}: {text or exc.__class__.__name__}")


def _error_code(exc: Exception) -> str:
    text = str(exc or "")
    return text.split(":", 1)[0].strip().upper()


def _known_platform_url(url: str) -> bool:
    host = (urlparse(str(url or "")).hostname or "").lower()
    known = (
        "youtube.com",
        "youtube-nocookie.com",
        "youtu.be",
        "vimeo.com",
        "tiktok.com",
        "dailymotion.com",
        "dai.ly",
        "facebook.com",
        "fb.watch",
        "instagram.com",
        "twitch.tv",
    )
    return any(host == domain or host.endswith(f".{domain}") for domain in known)


def _should_discover_page(source_url: str, error: VideoDownloadError) -> bool:
    code = _error_code(error)
    if code == "UNSUPPORTED_URL":
        return True
    if code in {"DOWNLOAD_FAILED", "OUTPUT_MP4_NOT_FOUND"}:
        return not _known_platform_url(source_url)
    return False


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
        for variant in (path, path.with_suffix(".mp4")):
            key = str(variant.resolve()) if path.is_absolute() else str(variant)
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


def social_video_progress_text(progress: dict[str, Any]) -> str:
    phase = str(progress.get("phase") or "").upper()
    if phase == "PREPARE":
        return "Preparando descarga…"
    if phase == "RESOLVE":
        return "Resolviendo URL…"
    if phase == "DISCOVER_PAGE":
        return "Analizando la página para encontrar el video…"
    if phase == "RETRY_CANDIDATE":
        return "Video encontrado; preparando descarga…"
    if phase == "POSTPROCESS":
        return "Procesando audio/video y remux MP4…"
    if phase == "VERIFY":
        return "Verificando MP4…"
    if phase == "COMPLETE":
        path = str(progress.get("local_path") or "").strip()
        size = progress.get("size_bytes")
        suffix = f" · {float(size) / (1024 * 1024):.1f} MB" if size is not None else ""
        return f"MP4 guardado{': ' + Path(path).name if path else ''}{suffix}"

    downloaded = progress.get("downloaded_bytes")
    total = progress.get("total_bytes")
    speed = progress.get("speed")
    eta = progress.get("eta")
    parts = ["Descargando video…"]
    if downloaded is not None and total is not None and float(total) > 0:
        parts.append(f"{float(downloaded) / (1024 * 1024):.1f} MB / {float(total) / (1024 * 1024):.1f} MB")
    elif downloaded is not None:
        parts.append(f"{float(downloaded) / (1024 * 1024):.1f} MB")
    if speed is not None:
        parts.append(f"{float(speed) / (1024 * 1024):.1f} MB/s")
    if eta is not None:
        parts.append(f"ETA {int(eta)}s")
    return " · ".join(parts)


def _download_with_yt_dlp(
    source_url: str,
    destination: Path,
    *,
    quality: str,
    on_progress: Callable[[dict[str, Any]], None] | None,
) -> VideoDownloadResult:
    selector = build_format_selector(quality)
    ffmpeg_exe = resolve_ffmpeg_exe()
    js_runtime = resolve_js_runtime()

    def emit(**payload):
        if on_progress:
            on_progress(payload)

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
            "retries": 3,
            "fragment_retries": 3,
        }
        if ffmpeg_exe:
            # imageio-ffmpeg uses versioned executable names. Passing only its
            # parent directory makes yt-dlp search for a nonexistent ffmpeg.exe.
            options["ffmpeg_location"] = str(ffmpeg_exe)
        if js_runtime:
            # yt-dlp's Python API expects the JS runtime executable under the
            # `path` key. The packaged app bundles Deno so YouTube EJS
            # challenges do not depend on software installed on the user's PC.
            options["js_runtimes"] = {"deno": {"path": str(js_runtime)}}

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


def _needs_selection(candidates) -> bool:
    if len(candidates) < 2:
        return False
    first, second = candidates[0], candidates[1]
    first_score = float(getattr(first, "score", 0.0) or 0.0)
    second_score = float(getattr(second, "score", 0.0) or 0.0)
    return first_score >= 90.0 and second_score >= 90.0 and (first_score - second_score) <= 8.0


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

    def emit(**payload):
        if on_progress:
            on_progress(payload)

    emit(phase="PREPARE")
    try:
        return _download_with_yt_dlp(
            source_url,
            destination,
            quality=quality,
            on_progress=on_progress,
        )
    except VideoDownloadError as direct_error:
        if not _should_discover_page(source_url, direct_error):
            raise

        emit(phase="DISCOVER_PAGE")
        try:
            from .video_page_discovery import discover_video_candidates

            candidates = discover_video_candidates(source_url, limit=8)
        except Exception:
            candidates = []
        if not candidates:
            raise direct_error
        if _needs_selection(candidates):
            raise VideoSelectionRequired(candidates)

        chosen = candidates[0]
        candidate_url = _validate_url(str(getattr(chosen, "url", "") or ""))
        emit(
            phase="RETRY_CANDIDATE",
            provider=str(getattr(chosen, "provider", "") or ""),
            source_kind=str(getattr(chosen, "source_kind", "") or ""),
            candidate_url=candidate_url,
        )
        return _download_with_yt_dlp(
            candidate_url,
            destination,
            quality=quality,
            on_progress=on_progress,
        )
