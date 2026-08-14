from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path


class UnsafeArchiveError(ValueError):
    pass


def extract_product_bundle(zip_path: Path, stage_dir: Path) -> Path:
    zip_path = Path(zip_path)
    stage_dir = Path(stage_dir)
    stage_dir.mkdir(parents=True, exist_ok=True)
    root = stage_dir.resolve()
    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            candidate = (stage_dir / info.filename).resolve()
            try:
                candidate.relative_to(root)
            except ValueError as exc:
                raise UnsafeArchiveError(info.filename) from exc
            if not info.filename.replace("\\", "/").startswith("ProductIntelligence/"):
                raise UnsafeArchiveError(info.filename)
        zf.extractall(stage_dir)
    product_root = stage_dir / "ProductIntelligence"
    if not (product_root / "ProductIntelligence.exe").is_file():
        raise UnsafeArchiveError("missing ProductIntelligence.exe")
    if not (product_root / "ProductIntelligenceUpdater.exe").is_file():
        raise UnsafeArchiveError("missing ProductIntelligenceUpdater.exe")
    return product_root


def wait_for_pid(pid: int, *, timeout: float = 60.0) -> None:
    if pid <= 0:
        return
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            os.kill(pid, 0)
        except OSError:
            return
        time.sleep(0.25)
    raise TimeoutError(f"parent process {pid} did not exit")


def _copy_tree(source: Path, target: Path, *, retries: int = 20) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for path in source.rglob("*"):
        rel = path.relative_to(source)
        dest = target / rel
        if path.is_dir():
            dest.mkdir(parents=True, exist_ok=True)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        last_error = None
        for _ in range(retries):
            try:
                tmp = dest.with_name(dest.name + ".update_tmp")
                shutil.copy2(path, tmp)
                os.replace(tmp, dest)
                last_error = None
                break
            except OSError as exc:
                last_error = exc
                time.sleep(0.25)
        if last_error is not None:
            raise last_error


def apply_update(zip_path: Path, target_dir: Path, restart_exe: Path, parent_pid: int) -> None:
    target_dir = Path(target_dir).resolve()
    restart_exe = Path(restart_exe).resolve()
    wait_for_pid(int(parent_pid))
    with tempfile.TemporaryDirectory(prefix="product-intelligence-stage-") as temp:
        product_root = extract_product_bundle(Path(zip_path), Path(temp))
        _copy_tree(product_root, target_dir)
    subprocess.Popen([str(restart_exe)], cwd=str(target_dir), close_fds=True)
    try:
        Path(zip_path).unlink(missing_ok=True)
    except OSError:
        pass


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--restart", required=True)
    parser.add_argument("--pid", required=True, type=int)
    args = parser.parse_args(argv)
    apply_update(Path(args.zip), Path(args.target), Path(args.restart), args.pid)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
