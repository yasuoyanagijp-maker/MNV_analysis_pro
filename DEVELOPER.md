# ARIAKE OCTA — 開発者向けガイド

エンドユーザ向けの操作は **[USER_MANUAL.md](USER_MANUAL.md)** を参照してください。本書は**実装・デバッグ・拡張**のためのメモです。

---

## 1. 技術スタックと制約

| 項目 | 内容 |
|------|------|
| Python | **3.9 互換**を維持（型ヒント・ジェネリクス等に注意） |
| UI | **Flet 0.28.3**（Web ブラウザ / ネイティブの両方を想定） |
| API | **FastAPI** + **httpx**（フロントは `BackendClient` 経由） |
| 主要エントリ | `main_app.py`（Flet）、`src/api/main.py`（API）、`run_flet.sh`（一体起動） |

---

## 2. リポジトリのざっくり地図

```
main_app.py          # Flet アプリ: ルーティング、AppContext、FilePicker
pages/               # 各画面: login, dashboard, results_screen, roi_selection, mnv_wizard, …
components/shared.py # テーマ色、AppContext、BackendClient、共有 UI
src/api/             # FastAPI: エンドポイント、スキーマ
src/core/            # MNV/VD パイプライン呼び出し
src/ariake_octa/     # 解析コア（画像処理多数）
utils/               # 付属ユーティリティ（例: report_generator）
uploads/             # 実行時アップロード先（.gitignore 想定）
```

`scratch/` は実験用。本番同梱の前提で書かない。

---

## 3. 起動と環境変数

| 変数 | 既定 | 意味 |
|------|------|------|
| `FLET_USE_WEB` | `1` | `1` = ブラウザ（`AppView.WEB_BROWSER`）。`0` や `native` 等 = ネイティブウィンドウ（`FLET_APP`） |
| `FLET_PORT` | `8550` | Flet のポート（`main_app` と `run_flet.sh` の両方で使用） |
| `FLET_SERVER_IP` | `127.0.0.1`（`run_flet.sh` 既定） | Web 時の uvicorn バインド。`0.0.0.0` だと Flet が `http://0.0.0.0:…` を開き**ブラウザで白紙のまま**になることがある。LAN 向けに `0.0.0.0` を付ける場合は、同一マシンでは `http://127.0.0.1:FLET_PORT` を手動で開く。 |
| `DEV_MODE` | 未設定 | `1` のとき**ログイン無効**・テスト用セッション注入。**本番禁止** |
| `DEV_MODE` 以外 | — | バックエンド URL 等を変える場合は `components/shared.py` の `BackendClient` を確認 |

`run_flet.sh` は `FLET_USE_WEB` を `export` し、**`flet run --web` と素の `flet run` を切替**する。`python main_app.py` 直叩きの場合も `_flet_use_web()` が同じ変数を読む。

---

## 4. アーキテクチャ（Flet 側）

### 4.1 ルーティング

- `page.on_route_change` で `page.route` を解釈し、`get_*_view(ctx)` を差し替える。
- ルート例: `/login`, `/`, `/results`, `/roi`, `/mnv`（`main_app.py` を真実の情報源にする）。

### 4.2 `AppContext`（`components/shared.py`）

- `page`, `client`（`BackendClient`）、各種 `ft.Ref`、**FilePicker 3 種**、後から注入される `process_target_path` を保持。

### 4.3 セッション

- 解析対象パス: `page.session`（例: `target_path`）、結果: `last_result` / `batch_results` 等。  
- **リロードで消える**前提。永続化が必要なら API か `client_storage` を検討（[§6](#6-ui-開発上のガードレール)）。

### 4.4 FilePicker と `page.web`

- **Web** では Flet の **`get_directory_path` は事実上使えない**（公式制限）。`pages/dashboard.py` は `getattr(page, "web", False)` により、Web 時は**サーバ側 `list_dir` ベースのエクスプローラ**等へ分岐。
- **ネイティブ**（`FLET_USE_WEB=0`）では OS ダイアログが使える想定。

### 4.5 ナビゲーション

- 標準 `NavigationRail` 等は **Python 3.9 環境で問題が出たため**、**カスタムサイドバー**に置き換え済み。新 UI でも同方針を踏襲する。

---

## 5. バックエンド（API）

- 実装: `src/api/main.py`。解析は `src/core` / `src/ariake_octa` に委譲。
- フロントの呼び出し: `BackendClient`（`httpx`、既定 `http://127.0.0.1:8000`）。
- 新エンドポイント追加時: **スキーマ**（`src/api/schemas.py`）と **Client メソッド**の両方を更新すると安全。

---

## 6. UI 開発上のガードレール

以下は既存方針の要約（ブラック画面・原因不明障害の防止）。

### 6.1 レイアウト

- 新規ページの最上位は、可能な限り **`ft.Column(expand=True)` 等、親から高さが取れる構造**にする。Flet/Flutter では**高さ 0 になり真っ黒**になる事象に注意。

### 6.2 例外

- 例外を飲み込まず、ログとユーザー向けメッセージ（または既存のエラーダイアログ）に繋ぐ。`main_app` では `route_change` 周りの失敗を捕捉している。

### 6.3 セッション整合性

- `session` のキー名や意味を変える前に、**全ルート**での利用箇所を棚卸しする。

### 6.4 新しい画面の追加手順（目安）

1. `pages/<name>.py` に `async def get_<name>_view(ctx: AppContext)` を定義。  
2. `main_app.py` の `route_change` に `elif` を追加。  
3. 必要ならサイドバーに遷移ボタンを追加。  
4. Web/ネイティブ両方で**最小操作**（パス通過・戻る）を確認。

---

## 7. デバッグ

- ターミナルに **`print(..., flush=True)`** や Flet/バックエンドのログを残す。Web の FilePicker は **`Picker attached` ログだけでは不十分**な場合があり、`page.web` の分岐を常に意識する。
- バックエンド単体: `python src/api/main.py`、フロント単体: `flet run` または `python main_app.py`。
- **画像パスに日本語やスペースが含まれる**と `cv2.imread` が `None` を返すことがある。`src/utils/cv2_path.py` の `imread_bgr` / `imread_grayscale`（`read_bytes` + `imdecode`、必要時 **Pillow**）を使う。ROI 画面では `Path.is_file()` の**事前**チェックをしない（`d967a9d` で入れた条件が原因で、以前と比べ失敗しやすくなっていた例がある）。OneDrive オンラインのみは引き続き注意。

---

## 8. セキュリティ

- **`DEV_MODE=1` は研究・本番では使わない**（ログイン無効化とモック注入）。手順書に載せる場合は「開発専用」と明記済み（USER_MANUAL）。

---

## 9. 参考リンク

- [Flet FilePicker ドキュメント](https://flet.dev/docs/services/filepicker/)（Web 制限の記述あり）
- 利用者向け: **[USER_MANUAL.md](USER_MANUAL.md)**

---

*本書はリポジトリ内の慣行を反映したもので、大規模リファクタの際は更新してください。*

ローカルに **`DEVELOPMENT_RULES.md`**（UI ガードレールのみの旧メモ）がある場合、**§6 と重複する内容は本書を正**とし、整理・削除してかまいません。
