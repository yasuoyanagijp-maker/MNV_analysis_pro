# dmgbuild_settings.py — ARIAKE OCTA DMG レイアウト設定
# 使用方法: dmgbuild -s dmgbuild_settings.py "ARIAKE OCTA" dist/ARIAKE_OCTA.dmg

import os
from pathlib import Path

DIST_DIR = Path(__file__).parent / "dist"
APP_PATH = str(DIST_DIR / "ARIAKE_OCTA.app")

# ── DMG 基本設定 ──────────────────────────────────────────────────────────────
application = APP_PATH
appname = "ARIAKE OCTA"
format = "UDZO"          # 圧縮フォーマット（配布用）
compression_level = 9
size = None              # 自動計算

# ── ウィンドウレイアウト ──────────────────────────────────────────────────────
window_rect = ((200, 120), (600, 400))
icon_size = 128
text_size = 14

# ── アイコン配置 ──────────────────────────────────────────────────────────────
contents = [
    ("ARIAKE OCTA.app", (160, 200), "file", APP_PATH),
    ("Applications",    (420, 200), "link", "/Applications"),
]

# ── 背景画像（オプション: assets/dmg_background.png を用意した場合に有効化） ──
# background = str(Path(__file__).parent / "assets" / "dmg_background.png")

# ── ライセンス（オプション） ─────────────────────────────────────────────────
# license = {"default-language": "ja", "licenses": {"ja": "LICENSE"}}
