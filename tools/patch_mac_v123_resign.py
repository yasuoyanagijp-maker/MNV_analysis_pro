#!/usr/bin/env python3
"""Patch already-installed v1.2.3-mac apps: strip pip metadata, ad-hoc re-sign.

For 前原型 only (launch SIGKILL / codesign fails on *.dist-info).
Does NOT fix 瀧澤/木住野 login Connection Error (spawn + Hardened Runtime) —
those need a v1.2.4 zip (arm64 or Intel).

Usage:
  python3 tools/patch_mac_v123_resign.py
  python3 tools/patch_mac_v123_resign.py /Applications/ARIAKE_OCTA.app
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

DEFAULT_APP = Path("/Applications/ARIAKE_OCTA.app")
METADATA_SUFFIXES = (".dist-info", ".egg-info")
STRIP_SUBDIRS = ("Contents/Frameworks", "Contents/Resources")


def _run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    print(f"  $ {' '.join(cmd)}", flush=True)
    return subprocess.run(cmd, check=check, text=True, capture_output=True)


def _basename_poison(path: Path) -> bool:
    name = path.name
    if name.startswith("._"):
        return True
    return any(name.endswith(s) for s in METADATA_SUFFIXES)


def strip_pip_metadata(app: Path) -> int:
    """Remove *.dist-info / *.egg-info under Frameworks and Resources (maxdepth 1)."""
    removed = 0
    for sub in STRIP_SUBDIRS:
        root = app / sub
        if not root.is_dir():
            continue
        for entry in list(root.iterdir()):
            if _basename_poison(entry):
                print(f"  削除: {entry.relative_to(app)}", flush=True)
                if entry.is_symlink() or entry.is_file():
                    entry.unlink()
                else:
                    shutil.rmtree(entry)
                removed += 1
    for dot in app.rglob("._*"):
        if dot.is_file():
            dot.unlink(missing_ok=True)
            removed += 1
    if shutil.which("dot_clean"):
        subprocess.run(["dot_clean", "-m", str(app)], check=False, capture_output=True)
    left = [
        p
        for sub in STRIP_SUBDIRS
        for p in (app / sub).glob("*")
        if (app / sub).is_dir() and _basename_poison(p)
    ]
    if left:
        print("[エラー] pip メタデータが残っています:", file=sys.stderr, flush=True)
        for p in left:
            print(f"  {p.relative_to(app)}", file=sys.stderr, flush=True)
        sys.exit(1)
    print(f"  OK: {removed} 件削除、Frameworks/Resources にメタデータ 0 件", flush=True)
    return removed


def codesign_verify_verbose(app: Path) -> str:
    proc = subprocess.run(
        ["codesign", "--verify", "--deep", "--strict", "--verbose=2", str(app)],
        text=True,
        capture_output=True,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    return out.strip()


def main() -> int:
    if sys.platform != "darwin":
        print("[エラー] macOS 専用です。", file=sys.stderr)
        return 1

    parser = argparse.ArgumentParser(description="v1.2.3 Mac 再署名パッチ（前原型のみ）")
    parser.add_argument(
        "app",
        nargs="?",
        default=str(DEFAULT_APP),
        help=f"対象 .app（既定: {DEFAULT_APP}）",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="完了後に open しない",
    )
    args = parser.parse_args()
    app = Path(args.app).expanduser().resolve()

    print("")
    print("╔══════════════════════════════════════════════╗")
    print("║  ARIAKE OCTA — v1.2.3 Mac 再署名パッチ       ║")
    print("╚══════════════════════════════════════════════╝")
    print("")
    print("対象:", app)
    print("")
    print("[注意] 前原型（起動 SIGKILL / dist-info）専用です。")
    print("       ログイン後 Connection Error（瀧澤型・Intel 木住野型）には")
    print("       効きません → v1.2.4 ZIP（arm64 または Intel）が必要です。")
    print("")

    if not app.is_dir() or app.suffix != ".app":
        print(f"[エラー] .app が見つかりません: {app}", file=sys.stderr)
        print("  例: python3 tools/patch_mac_v123_resign.py /Applications/ARIAKE_OCTA.app")
        return 1

    for tool in ("xattr", "codesign"):
        if not shutil.which(tool):
            print(f"[エラー] {tool} が見つかりません。Xcode コマンドラインツールを入れてください。", file=sys.stderr)
            return 1

    print("[1/4] pip メタデータ（*.dist-info 等）を除去...")
    strip_pip_metadata(app)

    print("[2/4] 隔離属性をクリア (xattr -cr)...")
    proc = _run(["xattr", "-cr", str(app)], check=False)
    if proc.returncode != 0:
        print("[エラー] xattr に失敗しました。", file=sys.stderr)
        if proc.stderr:
            print(proc.stderr, file=sys.stderr)
        if proc.stdout:
            print(proc.stdout, file=sys.stderr)
        return 1

    print("[3/4] アドホック再署名（Hardened Runtime なし）...")
    proc = subprocess.run(
        ["codesign", "--force", "--deep", "--sign", "-", str(app)],
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        print("[エラー] codesign に失敗しました。", file=sys.stderr)
        if proc.stderr:
            print(proc.stderr, file=sys.stderr)
        if proc.stdout:
            print(proc.stdout, file=sys.stderr)
        print("", file=sys.stderr)
        print("失敗箇所の詳細 (codesign --verify --verbose=2):", file=sys.stderr)
        detail = codesign_verify_verbose(app)
        if detail:
            print(detail, file=sys.stderr)
        else:
            print("  （詳細を取得できませんでした）", file=sys.stderr)
        print("", file=sys.stderr)
        print("このパッチで直らない場合は v1.2.4-mac（または Intel v1.2.4）ZIP をご利用ください。", file=sys.stderr)
        return 1

    print("[4/4] 署名を検証 (codesign --verify --deep --strict)...")
    proc = subprocess.run(
        ["codesign", "--verify", "--deep", "--strict", str(app)],
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        print("[エラー] 署名検証に失敗しました。", file=sys.stderr)
        detail = codesign_verify_verbose(app)
        if detail:
            print(detail, file=sys.stderr)
        return 1

    print("")
    print("✅ 再署名が完了しました。")
    if args.no_open:
        print("Applications フォルダから ARIAKE_OCTA を起動してください。")
    else:
        print("アプリを起動します...")
        subprocess.run(["open", str(app)], check=False)
    print("")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
