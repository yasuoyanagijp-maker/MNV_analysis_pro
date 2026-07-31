# -*- mode: python ; coding: utf-8 -*-
# One-file console EXE for compute_caliber_u2_from_csv (Mac / Windows).
import os
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parents[1]
entry = str(ROOT / "tools" / "caliber_u2" / "compute_caliber_u2_from_csv.py")
ref_json = str(ROOT / "resources" / "reference_metrics" / "caliber_u2_device_ref.json")

a = Analysis(
    [entry],
    pathex=[str(ROOT), str(ROOT / "src")],
    binaries=[],
    datas=[(ref_json, "resources/reference_metrics")],
    hiddenimports=["src.core.caliber_u2"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="compute_caliber_u2_from_csv",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
