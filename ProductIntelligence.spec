# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

root = Path(SPECPATH)
datas=[]; binaries=[]; hiddenimports=[]
for pkg in ['playwright','extruct','openpyxl','pydantic','bs4','lxml','fitz']:
    try:
        d,b,h=collect_all(pkg)
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
    excludes=['pytest','paddleocr','paddlepaddle','docling'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True,
    name='ProductIntelligence', debug=False, bootloader_ignore_signals=False,
    strip=False, upx=True, console=False, disable_windowed_traceback=False,
    argv_emulation=False, target_arch=None, codesign_identity=None, entitlements_file=None,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=True, upx_exclude=[], name='ProductIntelligence')
