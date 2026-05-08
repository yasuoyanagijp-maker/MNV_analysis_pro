# -*- mode: python ; coding: utf-8 -*-
import sys
import PIL
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

# ── 設定 ────────────────────────────────────────────────────────
# デバッグ時は True にすると、EXE 実行時に背後で黒いコンソールが開きます
DEBUG_MODE = False

block_cipher = None

# ── libtiff.dll の自動探索ロジック ──────────────────────────────
def collect_libtiff():
    """PIL や imagecodecs 内の libtiff 関連バイナリを収集する"""
    pil_dir = Path(PIL.__file__).parent
    # Pillow の DLL 探索
    dlls = list(pil_dir.glob("libtiff*.dll"))
    
    # imagecodecs の探索 (Pillow にない場合)
    if not dlls:
        try:
            import imagecodecs
            ic_dir = Path(imagecodecs.__file__).parent
            dlls = list(ic_dir.glob("*.dll")) + list(ic_dir.glob("_tiff.pyd"))
        except ImportError:
            pass

    if not dlls:
        print("Note: Specialized libtiff.dll not found. Relying on standard package collection.")
        return []
    
    return [(str(f), ".") for f in dlls]

# ── 資産収集 ────────────────────────────────────────────────────
datas = [
    ("main_app.py", "."),
    ("src", "src"),
    ("resources", "resources"),
]
binaries = collect_libtiff()
hiddenimports = [
    'uvicorn.logging', 'uvicorn.loops', 'uvicorn.loops.auto', 'uvicorn.protocols.http.auto', 
    'uvicorn.protocols.websockets.auto', 'uvicorn.lifespan.on', 'uvicorn.lifespan.off'
]

# collect_all を使用して主要パッケージを統合
to_collect = [
    "flet",
    "fastapi",
    "uvicorn",
    "multipart",
    "cv2",
    "skimage",
    "PIL",
    "imagecodecs",
    "tifffile",
    "shapely",
    "networkx",
    "imageio",
]

for pkg in to_collect:
    tmp_datas, tmp_binaries, tmp_hiddenimports = collect_all(pkg)
    datas += tmp_datas
    binaries += tmp_binaries
    hiddenimports += tmp_hiddenimports

# ── Analysis ─────────────────────────────────────────────────────
a = Analysis(
    ['wrapper_win.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['torch', 'torchvision', 'torchaudio'], # PyTorch を明示的に除外
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=True, # パス解決の安定化
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='retinal-analysis-pro',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=DEBUG_MODE, # ここを DEBUG_MODE で切り替え
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='retinal-analysis-pro',
)
