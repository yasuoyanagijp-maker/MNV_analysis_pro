# -*- mode: python ; coding: utf-8 -*-
# 注意: build_mac.sh は ARIAKE_OCTA_arm64.spec / ARIAKE_OCTA_x86_64.spec を自動選択します。
# 直接 pyinstaller を呼ぶ場合は、本ファイルの代わりにアーキテクチャ別 spec を使用してください。
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
# tifffileをデータとしてコピー（解凍エラー回避のため）
if os.path.exists(os.path.join(venv_site_packages, 'tifffile')):
    datas.append((os.path.join(venv_site_packages, 'tifffile'), 'tifffile'))

# 【修正ポイント1】不足しているバイナリを明示的に追加
# 実際に libtiff が存在する場合のみバイナリとして追加する
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

# 一般的なパッケージの収集（imagecodecs/tifffile は LZW 圧縮 TIFF 用に必須）
for pkg in ['flet', 'fastapi', 'uvicorn', 'multipart', 'cv2', 'skimage', 'networkx', 'shapely', 'imageio', 'imagecodecs']:
    tmp_ret = collect_all(pkg)
    datas += tmp_ret[0]
    binaries += tmp_ret[1]
    hiddenimports += tmp_ret[2]

# 【修正ポイント2】極端な排除（Exclusion）を解除
# これにより必要な依存関係がビルドに含まれるようになります
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
    noarchive=True, # 解凍エラー(Error -5)を防ぐための重要設定
)

# 【修正ポイント3】TIFFの外科的削除を停止
# ファイル欠落エラー（xattr: No such file）の直接的な原因を無効化します
def filter_tiff(toc_list):
    # ロジックは残しますが、適用はしません
    return [item for item in toc_list if 'tiff' not in str(item[0]).lower()]

# 以下のフィルタリングをコメントアウト
# a.pure = filter_tiff(a.pure)
# a.scripts = filter_tiff(a.scripts)
# a.binaries = filter_tiff(a.binaries)
# a.zipfiles = filter_tiff(a.zipfiles)

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
    # Apple Silicon (arm64) 環境に合わせる
    target_arch='arm64',
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