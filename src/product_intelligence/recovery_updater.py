from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

import requests


LATEST_RELEASE_API = "https://api.github.com/repos/artosperu-bot/scrapping/releases/latest"
ZIP_ASSET = "ProductIntelligence-Windows.zip"
SHA_ASSET = "ProductIntelligence-Windows.sha256"
APP_EXE = "ProductIntelligence.exe"
UPDATER_EXE = "ProductIntelligenceUpdater.exe"


def _find_running_app() -> tuple[Path | None, int | None]:
    if os.name != "nt":
        return None, None
    script = (
        "$p=Get-Process ProductIntelligence -ErrorAction SilentlyContinue | Select-Object -First 1 Id,Path; "
        "if($p){$p | ConvertTo-Json -Compress}"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        raw = (result.stdout or "").strip()
        if not raw:
            return None, None
        payload = json.loads(raw)
        path = payload.get("Path")
        pid = payload.get("Id")
        if path and pid:
            return Path(path), int(pid)
    except Exception:
        pass
    return None, None


def discover_target_dir(executable_path: Path, cwd: Path) -> tuple[Path | None, int | None]:
    executable_path = Path(executable_path).resolve()
    cwd = Path(cwd).resolve()
    running_path, running_pid = _find_running_app()

    candidates = [executable_path.parent, cwd]
    seen: set[Path] = set()
    for candidate in candidates:
        candidate = candidate.resolve()
        if candidate in seen:
            continue
        seen.add(candidate)
        app = candidate / APP_EXE
        if app.is_file():
            if running_path and running_path.resolve() == app.resolve():
                return candidate, running_pid
            return candidate, None

    if running_path and running_path.is_file():
        return running_path.resolve().parent, running_pid
    return None, None


def parse_sha256(text: str) -> str:
    match = re.search(r"\b([0-9a-fA-F]{64})\b", text or "")
    if not match:
        raise ValueError("Invalid SHA256 file")
    return match.group(1).lower()


def select_release_assets(payload: dict) -> tuple[str, str, str]:
    version = str(payload.get("tag_name") or "").strip()
    if version.lower().startswith("v"):
        version = version[1:]
    assets = {item.get("name"): item.get("browser_download_url") for item in payload.get("assets", [])}
    zip_url = assets.get(ZIP_ASSET)
    sha_url = assets.get(SHA_ASSET)
    if not version or not zip_url or not sha_url:
        raise ValueError("Required release assets are missing")
    return version, str(zip_url), str(sha_url)


def verify_sha256(path: Path, expected: str) -> None:
    digest = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest().lower() != expected.lower():
        raise ValueError("SHA256 verification failed")


def safe_extract_bundle(zip_path: Path, stage_dir: Path) -> Path:
    zip_path = Path(zip_path)
    stage_dir = Path(stage_dir)
    stage_dir.mkdir(parents=True, exist_ok=True)
    stage_root = stage_dir.resolve()
    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            normalized = info.filename.replace("\\", "/")
            candidate = (stage_dir / normalized).resolve()
            try:
                candidate.relative_to(stage_root)
            except ValueError as exc:
                raise ValueError(f"unsafe archive entry: {info.filename}") from exc
            if not normalized.startswith("ProductIntelligence/"):
                raise ValueError(f"unsafe archive root: {info.filename}")
        zf.extractall(stage_dir)
    product_root = stage_dir / "ProductIntelligence"
    if not (product_root / APP_EXE).is_file() or not (product_root / UPDATER_EXE).is_file():
        raise ValueError("unsafe archive: expected executables are missing")
    return product_root


def _copy_tree(source: Path, target: Path, *, retries: int = 30) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for path in source.rglob("*"):
        rel = path.relative_to(source)
        dest = target / rel
        if path.is_dir():
            dest.mkdir(parents=True, exist_ok=True)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        last_error: OSError | None = None
        for _ in range(retries):
            try:
                temp_dest = dest.with_name(dest.name + ".recovery_tmp")
                shutil.copy2(path, temp_dest)
                os.replace(temp_dest, dest)
                last_error = None
                break
            except OSError as exc:
                last_error = exc
                time.sleep(0.25)
        if last_error is not None:
            raise last_error


def _wait_for_pid_exit(pid: int, timeout: float = 120.0) -> None:
    if pid <= 0 or os.name != "nt":
        return
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=False,
        )
        output = (result.stdout or "").lower()
        if str(pid) not in output or APP_EXE.lower() not in output:
            return
        time.sleep(0.5)
    raise TimeoutError("ProductIntelligence did not close in time")


def _download(session, url: str, destination: Path) -> None:
    response = session.get(url, stream=True, timeout=(15, 180))
    response.raise_for_status()
    with destination.open("wb") as fh:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if chunk:
                fh.write(chunk)


def recover(target_dir: Path, *, session=requests) -> str:
    target_dir = Path(target_dir).resolve()
    if not (target_dir / APP_EXE).is_file():
        raise ValueError("ProductIntelligence.exe was not found in the target folder")

    latest = session.get(LATEST_RELEASE_API, timeout=30)
    latest.raise_for_status()
    version, zip_url, sha_url = select_release_assets(latest.json())

    with tempfile.TemporaryDirectory(prefix="product-intelligence-recovery-") as temp:
        temp_dir = Path(temp)
        archive = temp_dir / ZIP_ASSET
        sha_path = temp_dir / SHA_ASSET
        _download(session, zip_url, archive)
        _download(session, sha_url, sha_path)
        expected = parse_sha256(sha_path.read_text(encoding="utf-8", errors="replace"))
        verify_sha256(archive, expected)
        product_root = safe_extract_bundle(archive, temp_dir / "stage")
        _copy_tree(product_root, target_dir)

    subprocess.Popen([str(target_dir / APP_EXE)], cwd=str(target_dir), close_fds=True)
    return version


def _message(kind: str, title: str, text: str) -> None:
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        if kind == "error":
            messagebox.showerror(title, text, parent=root)
        else:
            messagebox.showinfo(title, text, parent=root)
        root.destroy()
    except Exception:
        pass


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        assert LATEST_RELEASE_API.startswith("https://api.github.com/")
        assert ZIP_ASSET.endswith(".zip") and SHA_ASSET.endswith(".sha256")
        return 0

    executable_path = Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve()
    target_dir, running_pid = discover_target_dir(executable_path, Path.cwd())
    if target_dir is None:
        _message(
            "error",
            "ProductIntelligence Recovery",
            "No pude localizar tu instalación de ProductIntelligence.\n\n"
            "Coloca ProductIntelligenceRecoveryUpdater.exe en la misma carpeta donde está "
            "ProductIntelligence.exe y ejecútalo nuevamente.",
        )
        return 2

    try:
        if running_pid:
            _message(
                "info",
                "ProductIntelligence Recovery",
                "Cierra ProductIntelligence para continuar con la recuperación.\n\n"
                "El actualizador esperará hasta que la aplicación se cierre.",
            )
            _wait_for_pid_exit(running_pid)
        version = recover(target_dir)
    except Exception as exc:
        _message("error", "ProductIntelligence Recovery", f"No se pudo completar la actualización.\n\n{exc}")
        return 1

    _message(
        "info",
        "ProductIntelligence Recovery",
        f"Actualización completada correctamente a v{version}.\n\nProductIntelligence se abrirá automáticamente.",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
