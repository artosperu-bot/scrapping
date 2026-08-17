# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

root = Path(SPECPATH)
datas=[]; binaries=[]; hiddenimports=[
    'product_intelligence.isolated_desktop',
    'product_intelligence.pdf_desktop',
    'product_intelligence.pdf_review',
    'product_intelligence.pdf_review_batch',
    'product_intelligence.pdf_review_shell',
    'product_intelligence.provider_desktop',
    'product_intelligence.provider_runtime',
    'product_intelligence.provider_diagnostics_ui',
    'product_intelligence.ocr_space_client',
    'product_intelligence.local_ocr',
    'product_intelligence.mistral_client',
    'product_intelligence.description_narrator',
    'product_intelligence.progress_animation',
    'product_intelligence.update_service',
    'product_intelligence.version',
    'product_intelligence.social_video_downloader',
]

try:
    d,b,h=collect_all('playwright')
    datas += d; binaries += b; hiddenimports += h
except Exception:
    pass

try:
    d,b,h=collect_all('yt_dlp')
    datas += d; binaries += b; hiddenimports += h
except Exception:
    pass

try:
    d,b,h=collect_all('imageio_ffmpeg')
    datas += d; binaries += b; hiddenimports += h
except Exception:
    pass

try:
    d,b,h=collect_all('rapidocr')
    datas += d; binaries += b; hiddenimports += h
except Exception:
    pass

try:
    d,b,h=collect_all('onnxruntime')
    datas += d; binaries += b; hiddenimports += h
except Exception:
    pass

browser_dir=root/'vendor'/'ms-playwright'
if browser_dir.exists():
    datas.append((str(browser_dir),'vendor/ms-playwright'))

media_assets=root/'src'/'product_intelligence'/'assets'
if media_assets.exists():
    datas.append((str(media_assets),'product_intelligence/assets'))

progress_assets=root/'src'/'product_intelligence'/'assets'/'progress'
for progress_name in ('processing.gif', 'completed.gif'):
    progress_file=progress_assets/progress_name
    if not progress_file.is_file():
        raise FileNotFoundError(f"Missing required progress asset: {progress_file}")
    datas.append((str(progress_file),'product_intelligence/assets/progress'))

# PaddleOCR is intentionally excluded from the desktop profile. The packaged local
# OCR fallback is RapidOCR + ONNX Runtime; numpy/OpenCV dependencies must remain
# available because the CPU OCR runtime uses them internally.
common_excludes=[
    'pytest',
    'paddleocr','paddlepaddle','paddle',
    'docling',
    'fastapi','uvicorn','multipart','python_multipart','typer','click',
]

a = Analysis(
    ['run_desktop.py'],
    pathex=[str(root/'src')],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=common_excludes, noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True,
    name='ProductIntelligence', debug=False, bootloader_ignore_signals=False,
    strip=False, upx=True, console=False, disable_windowed_traceback=False,
    argv_emulation=False, target_arch=None, codesign_identity=None, entitlements_file=None,
)

updater_analysis = Analysis(
    ['run_updater.py'], pathex=[str(root/'src')], binaries=[], datas=[],
    hiddenimports=['product_intelligence.updater'], hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=common_excludes, noarchive=False,
)
updater_pyz = PYZ(updater_analysis.pure)
updater_exe = EXE(
    updater_pyz, updater_analysis.scripts, updater_analysis.binaries, updater_analysis.datas, [],
    exclude_binaries=False,
    name='ProductIntelligenceUpdater', debug=False, bootloader_ignore_signals=False,
    strip=False, upx=True, console=False, disable_windowed_traceback=False,
    argv_emulation=False, target_arch=None, codesign_identity=None, entitlements_file=None,
)

coll = COLLECT(
    exe, updater_exe, a.binaries, a.datas,
    strip=False, upx=True, upx_exclude=[], name='ProductIntelligence'
)
