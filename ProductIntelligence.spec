# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

root = Path(SPECPATH)
datas=[]; binaries=[]; hiddenimports=[]

# Playwright ships runtime resources that PyInstaller does not always discover
# automatically. Keep collect_all only for this capability; normal libraries
# rely on PyInstaller's standard hooks/import graph.
try:
    d,b,h=collect_all('playwright')
    datas += d; binaries += b; hiddenimports += h
except Exception:
    pass

browser_dir=root/'vendor'/'ms-playwright'
if browser_dir.exists():
    datas.append((str(browser_dir),'vendor/ms-playwright'))

a = Analysis(
    ['run_desktop.py'],
    pathex=[str(root/'src')],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # development
        'pytest',
        # optional OCR / vision
        'paddleocr','paddlepaddle','paddle','cv2','numpy',
        # optional document intelligence
        'docling',
        # API/CLI surfaces are not part of the desktop executable
        'fastapi','uvicorn','multipart','python_multipart','typer','click',
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True,
    name='ProductIntelligence', debug=False, bootloader_ignore_signals=False,
    strip=False, upx=True, console=False, disable_windowed_traceback=False,
    argv_emulation=False, target_arch=None, codesign_identity=None, entitlements_file=None,
)
coll = COLLECT(
    exe, a.binaries, a.datas,
    strip=False, upx=True, upx_exclude=[],
    name='ProductIntelligence'
)
