# 操作ビデオ（公開配布用）

解析画面の操作を示す短いクリップです（日本語字幕・音声なし）。患者データや症例画像のリポジトリ格納はしません。

| ファイル | 内容 | 目安 |
|----------|------|------|
| [ARIAKE_OCTA_howto.mp4](ARIAKE_OCTA_howto.mp4) | 第1グレーダー（Confirm Selection → ROI → 解析 → 結果保存） | 約1分10秒 |
| [ARIAKE_OCTA_grader2_folder.mp4](ARIAKE_OCTA_grader2_folder.mp4) | 第2リーダー（ローカル自動スキャン・フォルダ指定） | 約12秒 |

公開配布リポジトリでは同じパス（`documentation/videos/`）に同期されます。`.github/scripts/sync-distribution.sh` がこの 2 本だけをコピーし、`rsync --delete` で消えないよう保護します。
