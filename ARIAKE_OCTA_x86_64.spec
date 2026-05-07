# -*- mode: python ; coding: utf-8 -*-
# ARIAKE_OCTA_x86_64.spec — Intel Mac 用
# Intel Mac でビルド時に使用。x86_64 ネイティブ用。
import os
import sys
from PyInstaller.utils.hooks import collect_all, copy_metadata

block_cipher = None
project_root = os.getcwd()

# venv（Python 3.9）の Pillow 内にある libtiff を使用する
venv_site_packages = os.path.join(project_root, '.venv/lib/python3.9/site-packages')
libtiff_path = os.path.join(venv_site_packages, 'PIL', '.dylibs', 'libtiff.6.dylib')

datas = [
    (os.path.join(project_root, 'src'), 'src'),
    (os.path.join(project_root, 'resources'), 'resources'),
    (os.path.join(project_root, 'main_app.py'), '.'),
]

# Streamlit関連のメタデータとフロントエンドを追加
# No copy_metadata for streamlit

# ── FORCED PLAIN-FILE COLLECTION ──────────────────────────────────────
if os.path.exists(os.path.join(venv_site_packages, 'tifffile')):
    datas.append((os.path.join(venv_site_packages, 'tifffile'), 'tifffile'))

binaries = []
if os.path.exists(libtiff_path):
    binaries.extend([
        (libtiff_path, '.'),
        (libtiff_path, 'Contents/Frameworks'),
    ])

hiddenimports = [
    'uvicorn.logging', 'uvicorn.loops', 'uvicorn.loops.auto', 'uvicorn.protocols.http.auto', 'uvicorn.protocols.websockets.auto', 'uvicorn.lifespan.on', 'uvicorn.lifespan.off', 'scipy.spatial.transform._rotation_groups',
    'scipy.special.cython_special',
    'sklearn.utils._cython_blas',
    'PIL._tkinter_finder',
    'tifffile',
    'imagecodecs',
]

for pkg in ['flet', 'fastapi', 'uvicorn', 'multipart', 'cv2', 'skimage', 'networkx', 'shapely', 'imageio', 'imagecodecs']:
    tmp_ret = collect_all(pkg)
    datas += tmp_ret[0]
    binaries += tmp_ret[1]
    hiddenimports += tmp_ret[2]

excludes = []

a = Analysis(
    [os.path.join(project_root, 'wrapper.py')],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=True,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher, level=0)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ARIAKE_OCTA',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch='x86_64',  # Intel Mac
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='ARIAKE_OCTA',
)

app = BUNDLE(
    coll,
    name='ARIAKE_OCTA.app',
    icon=None,
    bundle_identifier='com.ariake.octa',
)
