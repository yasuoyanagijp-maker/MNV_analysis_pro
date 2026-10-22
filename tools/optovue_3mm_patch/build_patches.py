#!/usr/bin/env python3
"""Build Optovue 3mm overlay patches for the shipped desktop apps.

Mac Apple Silicon and Mac Intel share one payload: v1.2.4 keeps Python
sources under Contents/Resources, so the same files apply to both binaries.
Windows v1.2.3 also needs src/utils/local_http.py, because the updated
BackendClient imports it and that module is not in the v1.2.3 zip.
"""

from __future__ import annotations

import argparse
import hashlib
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL_DIR = Path(__file__).resolve().parent

# git diff --name-only v1.2.4-mac...HEAD -- src resources
MAC_FILES = (
    "resources/reference_metrics/complexity_ref_optovue_3mm.json",
    "resources/reference_metrics/mnv_classification_ref_optovue_3mm.json",
    "src/api/main.py",
    "src/api/schemas.py",
    "src/core/mnv_pipeline.py",
    "src/core/pattern_metrics.py",
    "src/flet_ui/components/shared.py",
    "src/flet_ui/pages/dashboard.py",
    "src/flet_ui/pages/mnv_wizard.py",
    "src/flet_ui/pages/results_screen.py",
    "src/utils/metadata_export.py",
    "src/utils/mnv_size_class.py",
    "src/utils/second_reader.py",
)

# Present on Mac v1.2.4, absent on Windows v1.2.3. Required by shared.py.
WIN_EXTRA = ("src/utils/local_http.py",)

PACKAGES = (
    {
        "zip_name": "ARIAKE_OCTA_optovue_3mm_patch_mac_apple_silicon.zip",
        "folder": "ARIAKE_OCTA_optovue_3mm_patch_mac_apple_silicon",
        "platform": "mac",
        "label": "Mac Apple Silicon（M1/M2/M3/M4）",
        "base": "v1.2.4 の ARIAKE_OCTA_mac.zip をインストールしたアプリ",
        "files": MAC_FILES,
    },
    {
        "zip_name": "ARIAKE_OCTA_optovue_3mm_patch_mac_intel.zip",
        "folder": "ARIAKE_OCTA_optovue_3mm_patch_mac_intel",
        "platform": "mac",
        "label": "Mac Intel",
        "base": "v1.2.4 の ARIAKE_OCTA_macOS_Intel_v1.2.4.zip をインストールしたアプリ",
        "files": MAC_FILES,
    },
    {
        "zip_name": "ARIAKE_OCTA_optovue_3mm_patch_windows.zip",
        "folder": "ARIAKE_OCTA_optovue_3mm_patch_windows",
        "platform": "win",
        "label": "Windows",
        "base": "v1.2.3 の ARIAKE_OCTA.zip（ARIAKE_OCTA.exe と _internal）",
        "files": MAC_FILES + WIN_EXTRA,
    },
)


def _zip_info(name: str, data: bytes, executable: bool) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=time.localtime()[:6])
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = (0o755 if executable else 0o644) << 16
    if any(ord(ch) > 127 for ch in name):
        info.flag_bits |= 0x800
    return info


def _readme(pkg: dict) -> str:
    if pkg["platform"] == "mac":
        how = (
            "1. ARIAKE OCTA を終了する。\n"
            "2. このフォルダの「パッチ適用.command」を右クリック →「開く」。\n"
            "   初回はダブルクリックだと macOS に止められることがあります。\n"
            "3. 通常は /Applications/ARIAKE_OCTA.app に適用されます。\n"
            "   別の場所にある場合は、このフォルダでターミナルを開き、次を実行します。\n"
            "   bash パッチ適用.command /Applications/ARIAKE_OCTA.app\n"
            "4. 終わるとアドホック再署名してアプリが開きます。\n"
            "   shapely/.dylibs で codesign が止まった場合も、この command が\n"
            "   フォルダ名を署名できる形にしてから署名します。\n"
            "   ターミナルで codesign --deep だけを繰り返さないでください。\n"
        )
    else:
        how = (
            "1. ARIAKE OCTA を終了する。\n"
            "2. 「パッチ適用.bat」をダブルクリックする。\n"
            "3. ARIAKE_OCTA.exe があるフォルダを入力する。\n"
            "   例: C:\\Users\\name\\Desktop\\ARIAKE_OCTA\n"
            "   または、コマンドプロンプトで\n"
            "   パッチ適用.bat \"C:\\path\\ARIAKE_OCTA\"\n"
            "4. 終わったら ARIAKE_OCTA.exe を起動する。\n"
        )
    lines = [
        "ARIAKE OCTA — Optovue 3mm パッチ",
        "",
        f"対象: {pkg['label']}",
        f"ベース: {pkg['base']}",
        "",
        "起動ウィザードの 3 mm が次の2つになります。画素のスケールはどちらも 3.0 mm です。",
        "  3 mm (Optovue)  … Optovue 3mm の Complexity と形態分類",
        "  3 mm (Zeiss HD) … 従来の CIRRUS HD 3×3",
        "数値欄の 3.0 と、手入力の 3 mm は Zeiss HD のままです。",
        "画面上部の Image Scale (mm) の数値一覧には、3 mm (Optovue) は出ません。",
        "4.5 mm と 6 mm は変わりません。",
        "",
        "Optovue 3mm の Complexity では Trunk 項は 50 のままです。",
        "Seafan と Medusa は、画像から出る Trunk の形で判定します。",
        "Caliber Uniformity、病態分類、Caliber U2 は Zeiss HD 3mm の基準のままです。",
        "",
        "適用手順",
        how.rstrip(),
        "",
        "この ZIP は解析エンジン一式の入れ替えではありません。",
        "入っている Python と参照 JSON だけを、インストール済みアプリへ上書きします。",
        "",
    ]
    return "\n".join(lines) + "\n"


def _manifest(files: tuple[str, ...]) -> str:
    rows = ["ファイル\tsha256"]
    for rel in files:
        digest = hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()
        rows.append(f"{rel}\t{digest}")
    return "\n".join(rows) + "\n"


def build(out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    mac_cmd = (TOOL_DIR / "apply_mac.command").read_bytes().replace(b"\r\n", b"\n")
    mac_sign = (TOOL_DIR.parent / "mac_adhoc_codesign.sh").read_bytes().replace(b"\r\n", b"\n")
    win_ps1 = (TOOL_DIR / "apply_windows.ps1").read_bytes()
    if not win_ps1.startswith(b"\xef\xbb\xbf"):
        win_ps1 = b"\xef\xbb\xbf" + win_ps1.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    win_bat = (TOOL_DIR / "apply_windows.bat").read_bytes().replace(b"\n", b"\r\n")
    for pkg in PACKAGES:
        dest = out_dir / pkg["zip_name"]
        if dest.exists():
            dest.unlink()
        folder = pkg["folder"]
        with zipfile.ZipFile(dest, "w") as zf:
            readme = _readme(pkg).encode("utf-8-sig")
            manifest = _manifest(pkg["files"]).encode("utf-8")
            entries: list[tuple[str, bytes, bool]] = [
                (f"{folder}/パッチの説明.txt", readme, False),
                (f"{folder}/ファイル一覧.txt", manifest, False),
            ]
            if pkg["platform"] == "mac":
                entries.append((f"{folder}/パッチ適用.command", mac_cmd, True))
                entries.append((f"{folder}/mac_adhoc_codesign.sh", mac_sign, True))
            else:
                entries.append((f"{folder}/パッチ適用.bat", win_bat, False))
                entries.append((f"{folder}/apply_windows.ps1", win_ps1, False))
            for rel in pkg["files"]:
                data = (ROOT / rel).read_bytes()
                entries.append((f"{folder}/payload/{rel}", data, False))
            for name, data, exe in entries:
                zf.writestr(_zip_info(name, data, exe), data)
        written.append(dest)
        print(f"wrote {dest} ({dest.stat().st_size} bytes)")
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Optovue 3mm desktop patches")
    parser.add_argument("--out", type=Path, default=ROOT / "dist" / "patches")
    args = parser.parse_args()
    build(args.out.resolve())


if __name__ == "__main__":
    main()
